from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from imperaos.control_plane.evidence_pack import EvidencePackBuilder
from imperaos.control_plane.models import (
    EvidenceIndexEntry,
    EvidenceIndexSnapshot,
    EvidencePackManifest,
    EvidenceVerificationHistoryItem,
)
from imperaos.control_plane.storage import ControlPlaneStore, file_sha256
from imperaos.runtime.config import RuntimeConfig
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT


def build_evidence_index(
    *,
    config: RuntimeConfig,
    evidence_root: str | Path = "artifacts",
    root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
) -> EvidenceIndexSnapshot:
    builder = EvidencePackBuilder(config=config, root_dir=root_dir)
    entries: list[EvidenceIndexEntry] = []
    history: list[EvidenceVerificationHistoryItem] = []
    blocking_reasons: list[str] = []
    warnings: list[str] = []

    manifest_paths = list(discover_evidence_manifests(evidence_root))
    if not manifest_paths:
        warnings.append("EVIDENCE_INDEX_EMPTY")

    for manifest_path in manifest_paths:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if payload.get("version") != "control-plane.evidence-pack/v1":
            warnings.append(f"EVIDENCE_MANIFEST_SKIPPED:{manifest_path}")
            continue
        manifest = EvidencePackManifest.model_validate(
            {key: value for key, value in payload.items() if key != "integrity"}
        )
        result = builder.verify(manifest_path=manifest_path)
        verified_at = datetime.now(UTC)
        evidence_id = manifest.pack_id
        entry = EvidenceIndexEntry(
            evidence_id=evidence_id,
            run_id=manifest.run_id,
            agent_id=manifest.agent_id,
            path=str(manifest_path.parent),
            manifest_hash=f"sha256:{file_sha256(manifest_path)}",
            signature_status=_signature_status(
                manifest=manifest,
                signature_verified=result.signature_verified,
            ),
            replay_status="verified" if result.replay_verified else "failed",
            verified_at_utc=verified_at,
            claim_status="ready" if result.status == "pass" else "blocked",
            redaction_status="clean" if manifest.redaction_summary.secrets_redacted else "failed",
            blocking_reasons=result.blocking_reasons,
        )
        entries.append(entry)
        history.append(
            EvidenceVerificationHistoryItem(
                history_id=f"{evidence_id}:{verified_at.strftime('%Y%m%d%H%M%S%f')}",
                evidence_id=evidence_id,
                status=result.status,
                verified_at_utc=verified_at,
                blocking_reasons=result.blocking_reasons,
                warnings=result.warnings,
            )
        )
        blocking_reasons.extend(result.blocking_reasons)
        warnings.extend(result.warnings)

    status = "blocked" if blocking_reasons else "conditional" if warnings else "pass"
    snapshot = EvidenceIndexSnapshot(
        status=status,
        entries=entries,
        verification_history=history,
        warnings=sorted(set(warnings)),
        blocking_reasons=sorted(set(blocking_reasons)),
    )
    _write_history(snapshot=snapshot, root_dir=root_dir)
    return snapshot


def discover_evidence_manifests(evidence_root: str | Path) -> list[Path]:
    root = Path(evidence_root)
    candidates = [
        root / "control-plane" / "evidence",
        root / "evidence",
        root,
    ]
    manifests: dict[str, Path] = {}
    for candidate in candidates:
        if not candidate.exists():
            continue
        for path in sorted(candidate.glob("**/manifest.json")):
            manifests[str(path.resolve())] = path
    return list(manifests.values())


def _signature_status(
    *,
    manifest: EvidencePackManifest,
    signature_verified: bool,
) -> str:
    if signature_verified:
        return "valid"
    if manifest.signature.mode == "unsigned":
        return "missing"
    return "invalid"


def _write_history(*, snapshot: EvidenceIndexSnapshot, root_dir: str | Path) -> None:
    store = ControlPlaneStore(root_dir)
    store.write_json_atomic(
        "evidence-index/history.json",
        snapshot.model_dump(mode="json", by_alias=True),
    )
