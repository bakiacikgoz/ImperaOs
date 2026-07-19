from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from imperaos import __version__
from imperaos.control_plane.evidence_pack import EvidencePackBuilder
from imperaos.control_plane.models import (
    EvidencePackItem,
    EvidencePackManifest,
    EvidenceSignatureSummary,
    EvidenceVerificationSummary,
    RedactionSummary,
)
from imperaos.control_plane.storage import file_sha256
from imperaos.enterprise.signing import build_integrity
from imperaos.runtime.config import RuntimeConfig

EVIDENCE_CORPUS_VERSION = "control-plane.evidence-corpus/v1"


class EvidenceCorpusCase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    case_id: str = Field(alias="caseId")
    description: str
    manifest_path: str = Field(alias="manifestPath")
    expected_status: str = Field(alias="expectedStatus")
    expected_reason: str | None = Field(default=None, alias="expectedReason")
    actual_status: str | None = Field(default=None, alias="actualStatus")
    passed: bool | None = None


class EvidenceCorpusManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: str = EVIDENCE_CORPUS_VERSION
    generated_at_utc: datetime = Field(alias="generatedAtUtc")
    corpus_root: str = Field(alias="corpusRoot")
    cases: list[EvidenceCorpusCase]


def build_evidence_verification_corpus(
    *,
    output_root: Path,
    include_tamper_cases: bool = True,
    config: RuntimeConfig | None = None,
    now: datetime | None = None,
) -> EvidenceCorpusManifest:
    """Build deterministic valid and negative evidence verification fixtures."""

    resolved_config = config or RuntimeConfig.from_profile("enterprise")
    generated_at = now or datetime.now(UTC)
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    cases: list[EvidenceCorpusCase] = []
    valid_manifest = _write_pack(
        output_root / "valid" / "control-plane" / "evidence" / "valid-pack",
        config=resolved_config,
        pack_id="evp-corpus-valid",
        run_id="corpus-valid-run",
        generated_at=generated_at,
    )
    cases.append(
        EvidenceCorpusCase(
            caseId="valid_signed_pack",
            description="Signed pack with required files, clean redaction, replay pass.",
            manifestPath=str(valid_manifest),
            expectedStatus="pass",
        )
    )

    if include_tamper_cases:
        cases.extend(
            [
                _tampered_case(output_root, valid_manifest),
                _missing_signature_case(output_root, valid_manifest),
                _stale_case(output_root, resolved_config),
                _expired_qualification_case(output_root, resolved_config),
                _wrong_commit_case(output_root, resolved_config),
                _raw_screenshot_case(output_root, resolved_config),
            ]
        )

    manifest = EvidenceCorpusManifest(
        generatedAtUtc=generated_at,
        corpusRoot=str(output_root),
        cases=cases,
    )
    _write_json(
        output_root / "corpus_manifest.json",
        manifest.model_dump(mode="json", by_alias=True),
    )
    return manifest


def verify_evidence_corpus(
    *,
    corpus_root: Path,
    config: RuntimeConfig | None = None,
    root_dir: Path | None = None,
) -> dict[str, Any]:
    resolved_config = config or RuntimeConfig.from_profile("enterprise")
    manifest_path = corpus_root / "corpus_manifest.json"
    manifest = EvidenceCorpusManifest.model_validate(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    builder = EvidencePackBuilder(
        config=resolved_config,
        root_dir=root_dir or corpus_root / "state" / "control-plane",
    )
    verified_cases: list[dict[str, Any]] = []
    for case in manifest.cases:
        result = builder.verify(manifest_path=case.manifest_path)
        expected_reason_ok = (
            case.expected_reason is None
            or case.expected_reason in result.blocking_reasons
        )
        passed = result.status == case.expected_status and expected_reason_ok
        verified = case.model_copy(
            update={
                "actual_status": result.status,
                "passed": passed,
            }
        )
        payload = verified.model_dump(mode="json", by_alias=True)
        payload["blockingReasons"] = result.blocking_reasons
        payload["warnings"] = result.warnings
        verified_cases.append(payload)
    report = {
        "version": "control-plane.evidence-corpus-verification/v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "status": "pass" if all(item["passed"] for item in verified_cases) else "fail",
        "corpusRoot": str(corpus_root),
        "cases": verified_cases,
    }
    _write_json(corpus_root / "corpus_verification_report.json", report)
    return report


def _tampered_case(output_root: Path, valid_manifest: Path) -> EvidenceCorpusCase:
    destination = output_root / "negative" / "tampered_manifest"
    shutil.copytree(valid_manifest.parent, destination)
    target = destination / "run_summary.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["status"] = "tampered"
    _write_json(target, payload)
    return EvidenceCorpusCase(
        caseId="tampered_manifest",
        description="Required artifact hash no longer matches the manifest.",
        manifestPath=str(destination / "manifest.json"),
        expectedStatus="fail",
        expectedReason="EVIDENCE_HASH_MISMATCH",
    )


def _missing_signature_case(output_root: Path, valid_manifest: Path) -> EvidenceCorpusCase:
    destination = output_root / "negative" / "missing_signature"
    shutil.copytree(valid_manifest.parent, destination)
    manifest_path = destination / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.pop("integrity", None)
    payload["signature"] = {"mode": "unsigned", "key_id": None, "algorithm": "ed25519"}
    _write_json(manifest_path, payload)
    return EvidenceCorpusCase(
        caseId="missing_signature",
        description="Manifest has no signed integrity envelope.",
        manifestPath=str(manifest_path),
        expectedStatus="fail",
        expectedReason="INTEGRITY_MISSING",
    )


def _stale_case(output_root: Path, config: RuntimeConfig) -> EvidenceCorpusCase:
    manifest = _write_pack(
        output_root / "negative" / "stale_timestamp",
        config=config,
        pack_id="evp-corpus-stale",
        run_id="corpus-stale-run",
        generated_at=datetime.now(UTC) - timedelta(days=45),
    )
    return EvidenceCorpusCase(
        caseId="stale_timestamp",
        description="Evidence generated outside the freshness window.",
        manifestPath=str(manifest),
        expectedStatus="fail",
        expectedReason="EVIDENCE_STALE",
    )


def _expired_qualification_case(output_root: Path, config: RuntimeConfig) -> EvidenceCorpusCase:
    manifest = _write_pack(
        output_root / "negative" / "expired_qualification",
        config=config,
        pack_id="evp-corpus-expired",
        run_id="corpus-expired-run",
        generated_at=datetime.now(UTC),
        qualification_status="expired",
    )
    return EvidenceCorpusCase(
        caseId="expired_qualification",
        description="Qualification status item is expired.",
        manifestPath=str(manifest),
        expectedStatus="fail",
        expectedReason="QUALIFICATION_EXPIRED",
    )


def _wrong_commit_case(output_root: Path, config: RuntimeConfig) -> EvidenceCorpusCase:
    manifest = _write_pack(
        output_root / "negative" / "wrong_commit",
        config=config,
        pack_id="evp-corpus-wrong-commit",
        run_id="corpus-wrong-commit-run",
        generated_at=datetime.now(UTC),
        git_commit="0000000",
    )
    return EvidenceCorpusCase(
        caseId="wrong_commit",
        description="Evidence references a different commit.",
        manifestPath=str(manifest),
        expectedStatus="fail",
        expectedReason="GIT_COMMIT_MISMATCH",
    )


def _raw_screenshot_case(output_root: Path, config: RuntimeConfig) -> EvidenceCorpusCase:
    manifest = _write_pack(
        output_root / "negative" / "raw_screenshot_violation",
        config=config,
        pack_id="evp-corpus-raw-screenshot",
        run_id="corpus-raw-screenshot-run",
        generated_at=datetime.now(UTC),
        raw_screenshots_persisted=1,
    )
    return EvidenceCorpusCase(
        caseId="raw_screenshot_violation",
        description="Raw screenshot persistence is present in evidence.",
        manifestPath=str(manifest),
        expectedStatus="fail",
        expectedReason="RAW_SCREENSHOT_PERSISTED",
    )


def _write_pack(
    destination: Path,
    *,
    config: RuntimeConfig,
    pack_id: str,
    run_id: str,
    generated_at: datetime,
    qualification_status: str = "pass",
    git_commit: str | None = None,
    raw_screenshots_persisted: int = 0,
) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    files: dict[str, Any] = {
        "run_summary.json": {"run_id": run_id, "agent_id": "corpus-agent", "status": "completed"},
        "agent_spec.json": {"agent_id": "corpus-agent", "runtime_kind": "external_stdio"},
        "policy_decisions.json": {"summary": {"allow": 1, "deny": 0, "require_approval": 0}},
        "approval_timeline.json": {"approval_ids": [], "status": "completed"},
        "audit_envelope.json": {"schema_version": "control-plane.audit/v1", "run_id": run_id},
        "replay_verification.json": {"status": "pass", "verified": True},
        "redaction_summary.json": {
            "raw_screenshots_persisted": raw_screenshots_persisted,
            "secrets_redacted": True,
            "pii_redaction_enabled": True,
        },
        "qualification_status.json": {"status": qualification_status},
        "support_bundle_manifest_reference.json": {"present": True, "path": "support/sample"},
    }
    items: list[EvidencePackItem] = []
    for relative_path, payload in files.items():
        path = destination / relative_path
        _write_json(path, payload)
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
        pack_id=pack_id,
        run_id=run_id,
        agent_id="corpus-agent",
        profile="enterprise",
        runtime_version=__version__,
        git_commit=git_commit or _git_commit(),
        generated_at=generated_at,
        items=items,
        redaction_summary=RedactionSummary(
            raw_screenshots_persisted=raw_screenshots_persisted,
            secrets_redacted=True,
            pii_redaction_enabled=True,
        ),
        verification=EvidenceVerificationSummary(
            hash_chain_verified=True,
            signature_verified=config.keys.provider in {"local_file", "managed_kms"},
            replay_verified=True,
        ),
        signature=EvidenceSignatureSummary(
            mode="ed25519_local_file" if config.keys.provider == "local_file" else "unsigned",
            key_id=config.keys.current_key_id,
            signature_ref="manifest.integrity.signature"
            if config.keys.provider in {"local_file", "managed_kms"}
            else None,
        ),
    )
    manifest_payload = manifest.model_dump(mode="json")
    manifest_payload["integrity"] = build_integrity(
        payload=manifest_payload,
        config=config,
        purpose="control-plane-evidence-corpus",
    )
    manifest_path = destination / "manifest.json"
    _write_json(manifest_path, manifest_payload)
    return manifest_path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"
