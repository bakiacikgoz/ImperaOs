from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from imperaos.control_plane.claim_guard import ClaimGuard
from imperaos.control_plane.field_evidence import STRICT_BLOCKED_CLAIMS
from imperaos.memory.models import StrictModel
from imperaos.runtime.config import RuntimeConfig

ReleaseTrainStatus = Literal["pass", "conditional", "blocked"]


class ReleaseTrainStackItem(StrictModel):
    name: str
    branch: str
    pr_number: int | None = Field(default=None, alias="prNumber")
    base_branch: str | None = Field(default=None, alias="baseBranch")
    head_sha: str | None = Field(default=None, alias="headSha")
    status: Literal["pending", "open", "merged", "unknown"] = "unknown"
    role: Literal[
        "workspace_memory_authority",
        "semantic_memory",
        "memory_policy",
        "governed_workflow",
        "field_evidence",
        "handoff_ops",
    ]


class ReleaseTrainGateRef(StrictModel):
    gate_id: str = Field(alias="gateId")
    command: str
    status: Literal["pass", "conditional", "blocked", "missing"] = "missing"
    artifact_path: str | None = Field(default=None, alias="artifactPath")
    required: bool = True


class ArtifactRootRef(StrictModel):
    artifact_id: str = Field(alias="artifactId")
    path: str
    exists: bool
    required: bool = True
    sha256: str | None = None


class ClaimBoundarySummary(StrictModel):
    public_desktop: str = Field(default="unknown", alias="publicDesktop")
    live_computer_use: str = Field(default="unknown", alias="liveComputerUse")
    approval_free_irreversible_mutation: str = Field(
        default="blocked",
        alias="approvalFreeIrreversibleMutation",
    )
    blocked_claims: list[str] = Field(default_factory=list, alias="blockedClaims")
    conditional_claims: list[str] = Field(default_factory=list, alias="conditionalClaims")
    deferred_claims: list[str] = Field(default_factory=list, alias="deferredClaims")
    unsupported_claim_allowed: bool = Field(default=False, alias="unsupportedClaimAllowed")


class ReleaseTrainManifest(StrictModel):
    schema_version: Literal["control-plane.release-train-manifest/v1"] = Field(
        default="control-plane.release-train-manifest/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    profile: str
    mode: Literal["local", "ci", "mainline_post_merge"] = "local"
    base_branch: str | None = Field(default=None, alias="baseBranch")
    head_branch: str | None = Field(default=None, alias="headBranch")
    head_sha: str | None = Field(default=None, alias="headSha")
    worktree_dirty: bool = Field(default=False, alias="worktreeDirty")
    stack: list[ReleaseTrainStackItem] = Field(default_factory=list)
    required_gates: list[ReleaseTrainGateRef] = Field(
        default_factory=list,
        alias="requiredGates",
    )
    artifact_roots: list[ArtifactRootRef] = Field(default_factory=list, alias="artifactRoots")
    claim_boundaries: ClaimBoundarySummary = Field(alias="claimBoundaries")
    expected_conditionals: list[str] = Field(default_factory=list, alias="expectedConditionals")


class ReleaseTrainVerificationReport(StrictModel):
    schema_version: Literal["control-plane.release-train-verification/v1"] = Field(
        default="control-plane.release-train-verification/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: ReleaseTrainStatus
    manifest_path: str | None = Field(default=None, alias="manifestPath")
    head_branch: str | None = Field(default=None, alias="headBranch")
    head_sha: str | None = Field(default=None, alias="headSha")
    gate_statuses: dict[str, str] = Field(default_factory=dict, alias="gateStatuses")
    missing_artifacts: list[str] = Field(default_factory=list, alias="missingArtifacts")
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


DEFAULT_STACK = (
    ReleaseTrainStackItem(
        name="Agent memory policy enforcement",
        branch="codex/agent-memory-policy-enforcement-v1",
        prNumber=10,
        role="memory_policy",
        status="open",
    ),
    ReleaseTrainStackItem(
        name="Governed pilot workflow release closure",
        branch="codex/governed-pilot-workflow-release-closure-v1",
        prNumber=13,
        role="governed_workflow",
        status="open",
    ),
    ReleaseTrainStackItem(
        name="Design partner field evidence closure",
        branch="codex/design-partner-target-evidence-attestation-closure-v1",
        prNumber=14,
        role="field_evidence",
        status="open",
    ),
    ReleaseTrainStackItem(
        name="Design partner RC handoff ops readiness",
        branch="codex/design-partner-rc-handoff-ops-readiness-v1",
        prNumber=None,
        role="handoff_ops",
        status="pending",
    ),
)


def build_release_train_manifest(
    *,
    profile: str,
    mode: Literal["local", "ci", "mainline_post_merge"] = "local",
    artifact_root: Path = Path("artifacts"),
    stack_items: tuple[ReleaseTrainStackItem, ...] = (),
    now: datetime | None = None,
) -> ReleaseTrainManifest:
    artifact_root = Path(artifact_root)
    claims = ClaimGuard(config=RuntimeConfig.from_profile(profile)).evaluate(
        evidence_root=artifact_root
    )
    manifest = ReleaseTrainManifest(
        generatedAtUtc=now or datetime.now(UTC),
        profile=profile,
        mode=mode,
        baseBranch="codex/design-partner-target-evidence-attestation-closure-v1",
        headBranch=_git(["branch", "--show-current"]),
        headSha=_git(["rev-parse", "HEAD"]),
        worktreeDirty=bool(_git(["status", "--porcelain"])),
        stack=list(stack_items or DEFAULT_STACK),
        requiredGates=_default_gates(artifact_root),
        artifactRoots=_artifact_roots(artifact_root),
        claimBoundaries=_claim_boundary_summary(claims.model_dump(mode="json")),
        expectedConditionals=[
            "provider-governance",
            "evidence-index",
            "enterprise-hat-a",
            "design-partner-beta",
        ],
    )
    return manifest


def verify_release_train(
    manifest: ReleaseTrainManifest,
    *,
    strict: bool = False,
    manifest_path: Path | None = None,
) -> ReleaseTrainVerificationReport:
    blockers: list[str] = []
    warnings: list[str] = []
    missing_artifacts = [
        item.artifact_id for item in manifest.artifact_roots if item.required and not item.exists
    ]
    for artifact_id in missing_artifacts:
        warnings.append(f"ARTIFACT_ROOT_MISSING:{artifact_id}")
    gate_statuses = {gate.gate_id: gate.status for gate in manifest.required_gates}
    for gate in manifest.required_gates:
        if gate.required and gate.status in {"blocked"}:
            blockers.append(f"REQUIRED_GATE_BLOCKED:{gate.gate_id}")
        elif gate.required and gate.status == "missing":
            warnings.append(f"REQUIRED_GATE_MISSING:{gate.gate_id}")
    if manifest.claim_boundaries.unsupported_claim_allowed:
        blockers.append("UNSUPPORTED_CLAIM_ALLOWED")
    if manifest.worktree_dirty:
        (blockers if strict else warnings).append("WORKTREE_DIRTY")
    status: ReleaseTrainStatus
    if blockers:
        status = "blocked"
    elif warnings:
        status = "conditional"
    else:
        status = "pass"
    return ReleaseTrainVerificationReport(
        status=status,
        manifestPath=str(manifest_path) if manifest_path else None,
        headBranch=manifest.head_branch,
        headSha=manifest.head_sha,
        gateStatuses=gate_statuses,
        missingArtifacts=missing_artifacts,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
    )


def write_release_train_manifest(
    *,
    manifest: ReleaseTrainManifest,
    output_path: Path,
) -> Path:
    _write_json(output_path, manifest.model_dump(mode="json", by_alias=True))
    return output_path


def write_release_train_verification(
    *,
    report: ReleaseTrainVerificationReport,
    output_path: Path,
) -> Path:
    _write_json(output_path, report.model_dump(mode="json", by_alias=True))
    return output_path


def load_release_train_manifest(path: Path) -> ReleaseTrainManifest:
    return ReleaseTrainManifest.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _default_gates(artifact_root: Path) -> list[ReleaseTrainGateRef]:
    return [
        ReleaseTrainGateRef(
            gateId="design-partner-field-evidence-gate",
            command="make design-partner-field-evidence-gate",
            status=_status_from_file(
                artifact_root / "design-partner-field-evidence" / "gate_result.json"
            ),
            artifactPath=str(artifact_root / "design-partner-field-evidence" / "gate_result.json"),
        ),
        ReleaseTrainGateRef(
            gateId="governed-pilot-workflow-gate",
            command="make governed-pilot-workflow-gate",
            status=_status_from_file(
                artifact_root / "governed-pilot-workflow" / "gate_result.json"
            ),
            artifactPath=str(artifact_root / "governed-pilot-workflow" / "gate_result.json"),
        ),
        ReleaseTrainGateRef(
            gateId="design-partner-rc-audit-gate",
            command="make design-partner-rc-audit-gate",
            status=_status_from_file(artifact_root / "design-partner-rc" / "rc_audit_gate.json"),
            artifactPath=str(artifact_root / "design-partner-rc" / "rc_audit_gate.json"),
        ),
    ]


def _artifact_roots(artifact_root: Path) -> list[ArtifactRootRef]:
    roots = [
        ("field-evidence", artifact_root / "design-partner-field-evidence", True),
        ("governed-pilot-workflow", artifact_root / "governed-pilot-workflow", True),
        ("design-partner-rc", artifact_root / "design-partner-rc", True),
        ("support-bundle", artifact_root / "support_bundle_manifest.json", True),
        ("security-posture", artifact_root / "security_posture.json", True),
    ]
    return [
        ArtifactRootRef(
            artifactId=artifact_id,
            path=str(path),
            exists=path.exists(),
            required=required,
        )
        for artifact_id, path, required in roots
    ]


def _claim_boundary_summary(claims: dict[str, object]) -> ClaimBoundarySummary:
    statuses = {
        str(item.get("claim_id")): str(item.get("status"))
        for item in claims.get("claims", [])
        if isinstance(item, dict)
    }
    blocked = sorted(claim for claim, status in statuses.items() if status == "blocked")
    conditional = sorted(claim for claim, status in statuses.items() if status == "conditional")
    deferred = sorted(claim for claim, status in statuses.items() if status == "deferred")
    live_statuses = [
        statuses.get("live-macos-computer-use", "unknown"),
        statuses.get("live-windows-computer-use", "unknown"),
        statuses.get("live-linux-computer-use", "unknown"),
    ]
    return ClaimBoundarySummary(
        publicDesktop=statuses.get("public-desktop-installer", "unknown"),
        liveComputerUse="blocked"
        if all(status in {"blocked", "deferred"} for status in live_statuses)
        else "allowed",
        approvalFreeIrreversibleMutation="blocked",
        blockedClaims=blocked,
        conditionalClaims=conditional,
        deferredClaims=deferred,
        unsupportedClaimAllowed=any(
            statuses.get(claim) not in {"blocked", "deferred"} for claim in STRICT_BLOCKED_CLAIMS
        ),
    )


def _status_from_file(path: Path) -> Literal["pass", "conditional", "blocked", "missing"]:
    if not path.exists():
        return "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "blocked"
    status = str(payload.get("status") or payload.get("auditStatus") or "missing").lower()
    if status in {"pass", "ready"}:
        return "pass"
    if status in {"conditional"}:
        return "conditional"
    if status in {"blocked", "fail", "failed"}:
        return "blocked"
    return "missing"


def _git(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(["git", *args], text=True).strip()
    except Exception:
        return None


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
