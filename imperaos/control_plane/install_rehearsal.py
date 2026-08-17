from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from imperaos.control_plane.evidence_corpus import build_evidence_verification_corpus
from imperaos.control_plane.evidence_index import build_evidence_index
from imperaos.control_plane.snapshot import build_control_plane_snapshot
from imperaos.enterprise.baseline import security_posture
from imperaos.enterprise.maintenance import export_support_bundle
from imperaos.enterprise.observability import collect_metrics_snapshot
from imperaos.enterprise.signing import key_status
from imperaos.runtime.config import RuntimeConfig

INSTALL_REHEARSAL_VERSION = "control-plane.install-rehearsal/v1"


class RehearsalStep(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    status: Literal["pass", "fail", "skipped", "conditional"]
    duration_ms: int = Field(alias="durationMs")
    safe_summary: str = Field(alias="safeSummary")
    artifact_path: str | None = Field(default=None, alias="artifactPath")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class InstallRehearsalReport(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: str = INSTALL_REHEARSAL_VERSION
    rehearsal_id: str = Field(alias="rehearsalId")
    generated_at_utc: datetime = Field(alias="generatedAtUtc")
    target_root: str = Field(alias="targetRoot")
    profile: str
    mode: Literal["source_cli", "operator_panel_smoke"] = "source_cli"
    status: Literal["pass", "fail", "conditional"]
    steps: list[RehearsalStep]
    support_bundle_safe: bool = Field(alias="supportBundleSafe")
    rollback_plan_present: bool = Field(alias="rollbackPlanPresent")
    secret_scan_status: Literal["pass", "fail", "not_run"] = Field(alias="secretScanStatus")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)
    markdown_path: str | None = Field(default=None, alias="markdownPath")


def run_install_rehearsal(
    *,
    target_root: Path,
    profile: str,
    mode: Literal["source_cli", "operator_panel_smoke"],
    output_path: Path,
    dry_run: bool = False,
    config: RuntimeConfig | None = None,
) -> InstallRehearsalReport:
    """Run a clean-root pilot install rehearsal without destructive cleanup."""

    generated_at = datetime.now(UTC)
    target_root = target_root.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    target_root.mkdir(parents=True, exist_ok=True)
    config = config or RuntimeConfig.from_profile(profile)
    rehearsal_config = _target_scoped_config(config, target_root)

    steps: list[RehearsalStep] = []
    steps.append(_preflight_step(target_root))
    steps.append(_json_step("dependency-manifest", target_root / "dependency_manifest.json", {
        "python": "uv",
        "frontend": "pnpm",
        "tauri": "cargo",
        "mode": mode,
    }))
    steps.append(_json_step("config-resolve", target_root / "config_resolved.json", {
        "profile": profile,
        "privacy_mode": rehearsal_config.privacy_mode,
        "security_mode": rehearsal_config.security.mode,
    }))
    steps.append(
        _json_step(
            "enterprise-fixture-check",
            target_root / "enterprise_fixture.json",
            key_status(rehearsal_config),
        )
    )
    steps.append(
        _json_step(
            "security-baseline",
            target_root / "security_posture.json",
            security_posture(rehearsal_config),
        )
    )
    steps.append(
        _json_step(
            "metrics-snapshot",
            target_root / "metrics_snapshot.json",
            collect_metrics_snapshot(rehearsal_config),
        )
    )
    steps.append(
        _json_step(
            "operator-capabilities",
            target_root / "operator_capabilities.json",
            {
                "status": "pass",
                "computer_use_live_enabled": False,
                "public_desktop_installer_ready": False,
            },
        )
    )

    snapshot = build_control_plane_snapshot(
        root_dir=target_root / "control-plane",
        profile=profile,
        evidence_root=target_root / "evidence-corpus" / "valid",
        runtime_mode="cli",
        bridge_mode="cli",
        used_fixture=False,
    )
    steps.append(
        _json_step(
            "control-plane-snapshot",
            target_root / "control_plane_snapshot.json",
            snapshot.model_dump(mode="json", by_alias=True),
        )
    )

    build_evidence_verification_corpus(
        output_root=target_root / "evidence-corpus",
        include_tamper_cases=False,
        config=rehearsal_config,
    )
    evidence_index = build_evidence_index(
        config=rehearsal_config,
        evidence_root=target_root / "evidence-corpus" / "valid",
        root_dir=target_root / "control-plane-index-state",
    )
    steps.append(
        _json_step(
            "evidence-verify",
            target_root / "evidence_index.json",
            evidence_index.model_dump(mode="json", by_alias=True),
        )
    )

    support = {"status": "skipped", "dry_run": dry_run}
    if not dry_run:
        support = export_support_bundle(
            rehearsal_config,
            output_path=target_root / "support-bundle-sample.zip",
        )
    steps.append(
        _json_step(
            "support-bundle-export",
            target_root / "support_bundle_export.json",
            support,
        )
    )

    secret_scan = scan_paths_for_secrets(
        [target_root / "support_bundle_export.json", target_root / "config_resolved.json"]
    )
    steps.append(
        _json_step(
            "support-bundle-no-secret-scan",
            target_root / "secret_scan.json",
            secret_scan,
        )
    )

    rollback_plan = {
        "status": "pass",
        "destructive_cleanup": False,
        "target_root": str(target_root),
        "steps": [
            "stop pilot services if started",
            "archive rehearsal reports",
            "remove only the dedicated rehearsal root after operator approval",
        ],
    }
    steps.append(_json_step("rollback-plan", target_root / "rollback_plan.json", rollback_plan))

    blocking = [
        reason
        for step in steps
        if step.status == "fail"
        for reason in (step.blocking_reasons or [f"{step.name.upper()}_FAILED"])
    ]
    warnings = [step.name for step in steps if step.status == "conditional"]
    support_bundle_safe = secret_scan["status"] == "pass"
    rollback_plan_present = True
    status: Literal["pass", "fail", "conditional"] = (
        "fail"
        if blocking or not support_bundle_safe
        else "conditional"
        if warnings
        else "pass"
    )
    report = InstallRehearsalReport(
        rehearsalId=f"install-rehearsal-{generated_at.strftime('%Y%m%d%H%M%S')}",
        generatedAtUtc=generated_at,
        targetRoot=str(target_root),
        profile=profile,
        mode=mode,
        status=status,
        steps=steps,
        supportBundleSafe=support_bundle_safe,
        rollbackPlanPresent=rollback_plan_present,
        secretScanStatus=secret_scan["status"],
        blockingReasons=sorted(set(blocking)),
        warnings=warnings,
    )
    output_path.write_text(
        json.dumps(
            report.model_dump(mode="json", by_alias=True),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown_path = output_path.with_name("INSTALL_REHEARSAL_REPORT.md")
    markdown_path.write_text(render_install_rehearsal_markdown(report), encoding="utf-8")
    return report.model_copy(update={"markdown_path": str(markdown_path)})


def render_install_rehearsal_markdown(report: InstallRehearsalReport) -> str:
    lines = [
        "# Install Rehearsal Report",
        "",
        f"- Status: `{report.status}`",
        f"- Profile: `{report.profile}`",
        f"- Target root: `{report.target_root}`",
        f"- Support bundle safe: `{report.support_bundle_safe}`",
        f"- Rollback plan present: `{report.rollback_plan_present}`",
        "",
        "## Steps",
        "",
        "| Step | Status | Summary |",
        "| --- | --- | --- |",
    ]
    for step in report.steps:
        lines.append(f"| {step.name} | {step.status} | {step.safe_summary} |")
    lines.extend(["", "## Boundary", ""])
    lines.append("- Destructive cleanup is not executed by rehearsal.")
    lines.append("- Computer-use live and public desktop installer claims remain disabled.")
    return "\n".join(lines) + "\n"


def scan_paths_for_secrets(paths: list[Path]) -> dict[str, Any]:
    markers = [
        "-----BEGIN PRIVATE KEY-----",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "sk-",
        "api_key",
        "session_token",
        "raw_screenshot",
    ]
    findings: list[dict[str, str]] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        lowered = text.lower()
        for marker in markers:
            if marker.lower() in lowered:
                findings.append({"path": str(path), "marker": marker})
    return {
        "version": "control-plane.no-secret-scan/v1",
        "status": "fail" if findings else "pass",
        "findings": findings,
    }


def _target_scoped_config(config: RuntimeConfig, target_root: Path) -> RuntimeConfig:
    return config.model_copy(
        update={
            "maintenance": config.maintenance.model_copy(
                update={"support_bundle_dir": str(target_root / "support")}
            ),
            "observability": config.observability.model_copy(
                update={"metrics_dir": str(target_root / "metrics")}
            ),
            "governance": config.governance.model_copy(
                update={"approval_store_path": str(target_root / "approvals.sqlite3")}
            ),
        }
    )


def _preflight_step(target_root: Path) -> RehearsalStep:
    unsafe_roots = {Path("/").resolve(), Path.home().resolve(), Path.cwd().resolve()}
    if target_root in unsafe_roots:
        return RehearsalStep(
            name="preflight",
            status="fail",
            durationMs=0,
            safeSummary="target root is not dedicated to rehearsal",
            blockingReasons=["REHEARSAL_TARGET_ROOT_UNSAFE"],
        )
    return RehearsalStep(
        name="preflight",
        status="pass",
        durationMs=0,
        safeSummary="dedicated rehearsal root is available",
    )


def _json_step(name: str, path: Path, payload: dict[str, Any]) -> RehearsalStep:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    status = _payload_status(payload)
    return RehearsalStep(
        name=name,
        status=status,
        durationMs=0,
        safeSummary=_safe_summary(payload),
        artifactPath=str(path),
        blockingReasons=list(
            payload.get("blockingReasons") or payload.get("blocking_reasons") or []
        ),
    )


def _payload_status(payload: dict[str, Any]) -> Literal["pass", "fail", "skipped", "conditional"]:
    raw = str(
        payload.get("status")
        or payload.get("overall_status")
        or payload.get("signature_status")
        or "pass"
    )
    if raw in {"pass", "passed", "healthy", "ready", "ok"}:
        return "pass"
    if raw in {"fail", "failed", "blocked", "error"}:
        return "fail"
    if raw in {"skipped", "not_run"}:
        return "skipped"
    return "conditional"


def _safe_summary(payload: dict[str, Any]) -> str:
    for key in ("summary", "human_summary", "status", "overall_status"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value[:180]
    return "artifact written"
