from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.control_plane.models import (
    TargetEvidenceBundle,
    TargetEvidenceClaimBoundary,
    TargetEvidenceItem,
    TargetEvidenceSession,
    TargetEvidenceVerificationResult,
)
from imperaos.control_plane.provider_conformance import run_provider_native_gate
from imperaos.control_plane.provider_runtime_workflows import (
    ProviderWorkflowProofRequest,
    run_provider_workflow_proof,
)
from imperaos.control_plane.storage import canonical_json_hash, file_sha256
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT

REQUIRED_BLOCKED_CLAIMS = (
    "public-desktop-installer",
    "live-macos-computer-use",
    "live-windows-computer-use",
    "live-linux-computer-use",
)

DEFAULT_ALLOWED_CLAIMS = (
    "self-hosted-agent-control-plane",
    "operator-console-visibility",
    "provider-governed-read-only-workflow",
)


def prepare_target_evidence_session(
    *,
    profile: str,
    mode: str,
    environment_label: str,
    output_root: str | Path,
    operator_id: str | None = None,
    allowed_claims: list[str] | tuple[str, ...] | None = None,
    blocked_claims: list[str] | tuple[str, ...] | None = None,
    started_at_utc: datetime | None = None,
) -> TargetEvidenceSession:
    if mode not in {"rehearsal", "target"}:
        raise ValueError("mode must be rehearsal or target")
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    session_path = output / "session.json"
    if session_path.exists():
        return TargetEvidenceSession.model_validate_json(session_path.read_text(encoding="utf-8"))

    safe_label = _redacted_label(environment_label)
    blocked = tuple(sorted(set(blocked_claims or REQUIRED_BLOCKED_CLAIMS)))
    allowed = tuple(
        item
        for item in sorted(set(allowed_claims or DEFAULT_ALLOWED_CLAIMS))
        if item not in REQUIRED_BLOCKED_CLAIMS
    )
    seed = {
        "profile": profile,
        "mode": mode,
        "environmentLabel": safe_label,
        "blockedClaims": blocked,
    }
    session = TargetEvidenceSession(
        sessionId=f"target-evidence-{canonical_json_hash(seed, prefixed=False)[:16]}",
        profile=profile,
        environmentLabel=safe_label,
        mode=mode,
        startedAtUtc=started_at_utc or datetime.now(UTC),
        operatorIdHash=_hash_string(operator_id) if operator_id else None,
        allowedClaims=list(allowed),
        blockedClaims=list(blocked),
        rawPersistence=False,
    )
    _write_json(session_path, session.model_dump(mode="json", by_alias=True))
    return session


def collect_target_evidence_rehearsal(
    *,
    session: TargetEvidenceSession | str | Path,
    output_root: str | Path,
    state_root: str | Path = CONTROL_PLANE_STATE_ROOT,
    evidence_root: str | Path = "artifacts",
) -> TargetEvidenceBundle:
    _ = state_root
    _ = evidence_root
    session_model = _load_session(session)
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)

    claim_boundary = TargetEvidenceClaimBoundary(blockedClaims=list(REQUIRED_BLOCKED_CLAIMS))
    claim_boundary_path = output / "claim_boundary.json"
    _write_json(claim_boundary_path, claim_boundary.model_dump(mode="json", by_alias=True))

    provider_gate = run_provider_native_gate(
        profile=session_model.profile,
        output_dir=output / "provider-governance",
    )
    provider_gate_path = output / "provider-native-gate.json"
    _write_json(provider_gate_path, provider_gate)

    workflow = run_provider_workflow_proof(
        ProviderWorkflowProofRequest(
            workflow_kind="read_only_ops_triage",
            provider_kind="openai_responses",
            profile=session_model.profile,
            runtime_mode="dry_run",
            output_root=output / "provider-runtime" / "workflow-proof",
        )
    )

    session_path = output / "session.json"
    if not session_path.exists():
        _write_json(session_path, session_model.model_dump(mode="json", by_alias=True))

    items = [
        _item("session", "session_manifest", session_path),
        _item("claim-boundary", "claim_boundary", claim_boundary_path),
        _item("provider-native-gate", "provider_gate", provider_gate_path),
        _item("provider-workflow-proof", "workflow_proof", Path(workflow.artifact_path)),
    ]
    missing_items: list[str] = []
    warnings: list[str] = []
    blocking_reasons: list[str] = []
    if provider_gate.get("status") != "pass":
        blocking_reasons.append("PROVIDER_NATIVE_GATE_FAILED")
    if workflow.status != "pass":
        blocking_reasons.append("PROVIDER_WORKFLOW_PROOF_FAILED")
    if session_model.mode == "rehearsal":
        missing_items.append("real_target_environment_run")
        warnings.append("TARGET_ENVIRONMENT_REHEARSAL_ONLY")

    bundle = TargetEvidenceBundle(
        sessionId=session_model.session_id,
        status="blocked" if blocking_reasons else "conditional" if missing_items else "pass",
        items=items,
        missingItems=missing_items,
        blockingReasons=blocking_reasons,
        warnings=warnings,
        claimBoundary=claim_boundary,
        secretMaterialWritten=False,
        rawPromptPersisted=False,
        rawResponsePersisted=False,
        rawScreenshotPersisted=False,
    )
    _write_json(
        output / "target_evidence_bundle.json",
        bundle.model_dump(mode="json", by_alias=True),
    )
    return bundle


def verify_target_evidence_bundle(
    bundle: TargetEvidenceBundle | dict[str, Any] | str | Path,
) -> TargetEvidenceVerificationResult:
    model = _load_bundle(bundle)
    blocking = list(model.blocking_reasons)
    if model.secret_material_written:
        blocking.append("SECRET_MATERIAL_WRITTEN")
    if model.raw_prompt_persisted:
        blocking.append("RAW_PROMPT_PERSISTED")
    if model.raw_response_persisted:
        blocking.append("RAW_RESPONSE_PERSISTED")
    if model.raw_screenshot_persisted:
        blocking.append("RAW_SCREENSHOT_PERSISTED")

    boundary = model.claim_boundary
    boundary_checks = {
        "PUBLIC_DESKTOP_INSTALLER_BOUNDARY_OPEN": boundary.public_desktop_installer,
        "LIVE_MACOS_COMPUTER_USE_BOUNDARY_OPEN": boundary.live_macos_computer_use,
        "LIVE_WINDOWS_COMPUTER_USE_BOUNDARY_OPEN": boundary.live_windows_computer_use,
        "LIVE_LINUX_COMPUTER_USE_BOUNDARY_OPEN": boundary.live_linux_computer_use,
    }
    for reason, status in boundary_checks.items():
        if status != "blocked":
            blocking.append(reason)
    for claim in REQUIRED_BLOCKED_CLAIMS:
        if claim not in boundary.blocked_claims:
            blocking.append(f"MISSING_BLOCKED_CLAIM:{claim}")

    for item in model.items:
        path = Path(item.path)
        if path.exists():
            actual = f"sha256:{file_sha256(path)}"
            if actual != item.sha256:
                blocking.append(f"EVIDENCE_HASH_MISMATCH:{item.item_id}")
        elif item.required:
            blocking.append(f"EVIDENCE_ITEM_MISSING:{item.item_id}")

    return TargetEvidenceVerificationResult(
        status="blocked" if blocking else "pass",
        blockingReasons=sorted(set(blocking)),
        warnings=list(model.warnings),
    )


def _load_session(session: TargetEvidenceSession | str | Path) -> TargetEvidenceSession:
    if isinstance(session, TargetEvidenceSession):
        return session
    return TargetEvidenceSession.model_validate_json(Path(session).read_text(encoding="utf-8"))


def _load_bundle(
    bundle: TargetEvidenceBundle | dict[str, Any] | str | Path,
) -> TargetEvidenceBundle:
    if isinstance(bundle, TargetEvidenceBundle):
        return bundle
    if isinstance(bundle, dict):
        return TargetEvidenceBundle.model_validate(bundle)
    return TargetEvidenceBundle.model_validate_json(Path(bundle).read_text(encoding="utf-8"))


def _item(item_id: str, kind: str, path: Path) -> TargetEvidenceItem:
    return TargetEvidenceItem(
        itemId=item_id,
        kind=kind,
        path=str(path),
        sha256=f"sha256:{file_sha256(path)}",
        status="pass",
        required=True,
    )


def _hash_string(value: str) -> str:
    return canonical_json_hash({"value": value})


def _redacted_label(value: str) -> str:
    label = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", value.strip())[:80].strip("-")
    return label or "redacted-environment"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
