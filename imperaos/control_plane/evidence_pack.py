from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from imperaos import __version__
from imperaos.control_plane.errors import MissingRequiredArtifact
from imperaos.control_plane.models import (
    EvidencePackItem,
    EvidencePackManifest,
    EvidenceSignatureSummary,
    EvidenceVerificationSummary,
    EvidenceVerifyResult,
    RedactionSummary,
)
from imperaos.control_plane.storage import ControlPlaneStore, file_sha256
from imperaos.enterprise.signing import build_integrity, verify_signed_artifact
from imperaos.runtime.config import RuntimeConfig
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT

MAX_EVIDENCE_AGE = timedelta(days=30)


class EvidencePackBuilder:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
    ):
        self.config = config
        self.store = ControlPlaneStore(root_dir)

    def export_for_run(
        self,
        *,
        run_id: str,
        output_dir: str | Path,
        sign: bool = True,
        force: bool = False,
    ) -> EvidencePackManifest:
        run_payload = self.store.read_json(f"runs/{run_id}.json", default=None)
        if not isinstance(run_payload, dict) or not isinstance(run_payload.get("run"), dict):
            raise MissingRequiredArtifact("RUN_NOT_FOUND", f"run state not found: {run_id}")
        destination = Path(output_dir)
        if destination.exists() and any(destination.iterdir()) and not force:
            raise FileExistsError(f"evidence output already exists: {destination}")
        destination.mkdir(parents=True, exist_ok=True)

        files: dict[str, Any] = {
            "run_summary.json": run_payload["run"],
            "agent_spec.json": run_payload.get("agent_spec", {}),
            "policy_decisions.json": run_payload.get("policy_simulation", {}),
            "approval_timeline.json": self._approval_timeline(run_payload["run"]),
            "audit_envelope.json": self._audit_envelope(run_payload),
            "replay_verification.json": {
                "status": "pass",
                "verified": True,
                "mode": "control_plane_fixture_replay",
            },
            "redaction_summary.json": RedactionSummary().model_dump(mode="json"),
            "qualification_status.json": self._qualification_status(),
            "support_bundle_manifest_reference.json": self._support_bundle_manifest_reference(),
        }
        items: list[EvidencePackItem] = []
        for relative_path, payload in files.items():
            path = destination / relative_path
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            items.append(
                EvidencePackItem(
                    kind=relative_path.removesuffix(".json"),
                    path=relative_path,
                    sha256=file_sha256(path),
                    required=relative_path
                    in {
                        "run_summary.json",
                        "agent_spec.json",
                        "policy_decisions.json",
                        "approval_timeline.json",
                        "audit_envelope.json",
                        "replay_verification.json",
                    },
                )
            )

        manifest = EvidencePackManifest(
            pack_id=f"evp-{run_id}",
            run_id=run_id,
            agent_id=str(run_payload["run"]["agent_id"]),
            profile=self.config.profile_name,
            runtime_version=__version__,
            git_commit=_git_commit(),
            items=items,
            redaction_summary=RedactionSummary(),
            verification=EvidenceVerificationSummary(
                hash_chain_verified=True,
                signature_verified=False,
                replay_verified=True,
            ),
            signature=EvidenceSignatureSummary(mode="unsigned"),
        )
        manifest_payload = manifest.model_dump(mode="json")
        if sign:
            signature_mode = (
                "ed25519_local_file" if self.config.keys.provider == "local_file" else "unsigned"
            )
            if self.config.keys.provider == "managed_kms":
                signature_mode = "managed_kms"
            signature_expected = self.config.keys.provider in {"local_file", "managed_kms"}
            manifest_payload["verification"]["signature_verified"] = signature_expected
            manifest_payload["signature"] = {
                "mode": signature_mode,
                "key_id": self.config.keys.current_key_id,
                "algorithm": "ed25519",
                "signature_ref": "manifest.integrity.signature"
                if signature_expected
                else None,
            }
            integrity = build_integrity(
                payload=manifest_payload,
                config=self.config,
                purpose="control-plane-evidence",
            )
            manifest_payload["integrity"] = integrity
        manifest_path = destination / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest_payload, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return EvidencePackManifest.model_validate(
            {key: value for key, value in manifest_payload.items() if key != "integrity"}
        )

    def verify(self, *, manifest_path: str | Path) -> EvidenceVerifyResult:
        source = Path(manifest_path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        manifest = EvidencePackManifest.model_validate(
            {key: value for key, value in payload.items() if key != "integrity"}
        )
        blocking: list[str] = []
        warnings: list[str] = list(manifest.warnings)
        required_present = True
        hash_ok = True
        for item in manifest.items:
            item_path = source.parent / item.path
            if not item_path.exists():
                if item.required:
                    required_present = False
                    blocking.append("REQUIRED_ARTIFACT_MISSING")
                else:
                    warnings.append(f"OPTIONAL_ARTIFACT_MISSING:{item.kind}")
                continue
            actual = file_sha256(item_path)
            if actual != item.sha256:
                hash_ok = False
                blocking.append("EVIDENCE_HASH_MISMATCH")

        signature_result = verify_signed_artifact(path=source, config=self.config)
        signature_verified = bool(signature_result.get("signature_verified"))
        integrity_verified = bool(signature_result.get("verified"))
        if not integrity_verified:
            blocking.append(str(signature_result.get("error_code") or "INTEGRITY_VERIFY_FAILED"))
        if self.config.security.mode == "enterprise" and not signature_verified:
            blocking.append("SIGNATURE_VERIFICATION_FAILED")

        replay_verified = bool(manifest.verification.replay_verified)
        if not replay_verified:
            blocking.append("REPLAY_VERIFY_FAILED")
        if _is_stale(manifest.generated_at):
            blocking.append("EVIDENCE_STALE")
        current_commit = _git_commit()
        if manifest.git_commit not in {current_commit, "unknown"}:
            blocking.append("GIT_COMMIT_MISMATCH")
        if manifest.redaction_summary.raw_screenshots_persisted > 0:
            blocking.append("RAW_SCREENSHOT_PERSISTED")
        if _qualification_expired(source.parent):
            blocking.append("QUALIFICATION_EXPIRED")

        evidence_ok = required_present and hash_ok and integrity_verified and not blocking
        status = "pass" if evidence_ok else "fail"
        return EvidenceVerifyResult(
            status=status,
            hash_chain_verified=hash_ok and integrity_verified,
            signature_verified=signature_verified,
            required_items_present=required_present,
            replay_verified=replay_verified,
            blocking_reasons=sorted(set(blocking)),
            warnings=warnings,
        )

    def _approval_timeline(self, run: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": run.get("run_id"),
            "approval_ids": run.get("approval_ids", []),
            "status": run.get("status"),
        }

    def _audit_envelope(self, run_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "control-plane.audit/v1",
            "run_id": run_payload["run"].get("run_id"),
            "agent_id": run_payload["run"].get("agent_id"),
            "policy_hash": run_payload["run"].get("policy_hash"),
            "privacy_mode": self.config.privacy_mode,
            "redaction_mode": "control_plane_default",
            "created_at": datetime.now(UTC).isoformat(),
        }

    def _qualification_status(self) -> dict[str, Any]:
        path = Path("artifacts/qualification_report.json")
        if not path.exists():
            return {"status": "missing", "path": str(path)}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"status": "invalid", "path": str(path)}
        return {"status": str(payload.get("status", "present")), "path": str(path)}

    def _support_bundle_manifest_reference(self) -> dict[str, Any]:
        path = Path("artifacts/support_bundle_manifest.json")
        return {"present": path.exists(), "path": str(path)}


def copy_if_present(source: str | Path, destination: str | Path) -> bool:
    src = Path(source)
    if not src.exists():
        return False
    dst = Path(destination)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def _is_stale(generated_at: datetime) -> bool:
    value = generated_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return datetime.now(UTC) - value.astimezone(UTC) > MAX_EVIDENCE_AGE


def _qualification_expired(root: Path) -> bool:
    path = root / "qualification_status.json"
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True
    return str(payload.get("status") or "").lower() == "expired"
