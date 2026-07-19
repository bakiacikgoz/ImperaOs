from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.control_plane.pilot_operations import (
    build_code_intelligence_summary,
    build_design_partner_beta_status,
    build_pilot_operations_status,
    generate_pilot_operations_artifacts,
)
from imperaos.control_plane.security_review import scan_no_secrets
from imperaos.control_plane.snapshot import build_control_plane_snapshot
from imperaos.runtime.config import RuntimeConfig

BETA_PACK_VERSION = "control-plane.design-partner-beta-pack/v1"


def generate_design_partner_beta_pack(
    *,
    output_root: Path,
    config: RuntimeConfig,
    evidence_root: Path = Path("artifacts"),
) -> dict[str, Any]:
    generated = datetime.now(UTC)
    output_root.mkdir(parents=True, exist_ok=True)
    generate_pilot_operations_artifacts(
        output_root=evidence_root / "pilot-ops",
        evidence_root=evidence_root,
    )
    copied = _copy_release_artifacts(evidence_root=evidence_root, output_root=output_root)
    pilot_manifest = _read_json(evidence_root / "design-partner-pilot" / "manifest.json")
    code_intelligence = build_code_intelligence_summary(evidence_root=evidence_root)
    pilot_operations = build_pilot_operations_status(evidence_root=evidence_root)
    beta_status = build_design_partner_beta_status(evidence_root=evidence_root)
    checks = _checks(
        copied=copied,
        pilot_manifest=pilot_manifest,
        code_intelligence=code_intelligence.model_dump(mode="json", by_alias=True),
        pilot_operations=pilot_operations.model_dump(mode="json", by_alias=True),
        ci_inventory=_read_json(evidence_root / "ci" / "node-action-inventory.json"),
        external_v1_1=_read_json(evidence_root / "external-agent-v1-1" / "results.json"),
    )
    blockers = sorted(
        {
            check["checkId"]
            for check in checks
            if check["status"] == "blocked" or check.get("blocking") is True
        }
    )
    warnings = sorted({check["checkId"] for check in checks if check["status"] == "conditional"})
    status = "blocked" if blockers else "conditional" if warnings else "ready"
    manifest = {
        "version": BETA_PACK_VERSION,
        "generatedAtUtc": generated.isoformat(),
        "packId": f"design-partner-beta-{generated.strftime('%Y%m%d%H%M%S')}",
        "status": status,
        "commitSha": _git_commit(),
        "outputRoot": str(output_root),
        "copiedArtifacts": copied,
        "checks": checks,
        "codeIntelligence": code_intelligence.model_dump(mode="json", by_alias=True),
        "pilotOperations": pilot_operations.model_dump(mode="json", by_alias=True),
        "designPartnerBeta": beta_status.model_dump(mode="json", by_alias=True),
        "blockers": blockers,
        "warnings": warnings,
    }
    _write_json(output_root / "manifest.json", manifest)
    snapshot = build_control_plane_snapshot(
        root_dir=output_root / "state" / "control-plane",
        profile=config.profile_name,
        evidence_root=evidence_root,
        runtime_mode="cli",
        bridge_mode="cli",
        used_fixture=False,
    )
    _write_json(
        output_root / "control-plane-snapshot.json",
        snapshot.model_dump(mode="json", by_alias=True),
    )
    no_secret = scan_no_secrets(output_root)
    manifest["noSecretScan"] = no_secret
    if no_secret.get("status") != "pass":
        manifest["status"] = "blocked"
        manifest["blockers"] = sorted(set([*manifest["blockers"], "BETA_PACK_SECRET_SCAN_FAILED"]))
    _write_json(output_root / "manifest.json", manifest)
    (output_root / "BETA_OPERATIONS_REPORT.md").write_text(
        render_beta_operations_report(manifest),
        encoding="utf-8",
    )
    return manifest


def render_beta_operations_report(manifest: dict[str, Any]) -> str:
    lines = [
        "# Design Partner Beta Operations Report",
        "",
        f"- Status: `{manifest['status']}`",
        f"- Commit: `{manifest['commitSha']}`",
        f"- Generated: `{manifest['generatedAtUtc']}`",
        f"- Output root: `{manifest['outputRoot']}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    for check in manifest["checks"]:
        lines.append(f"| {check['label']} | {check['status']} | {check['detail']} |")
    lines.extend(["", "## Blockers", ""])
    blockers = manifest.get("blockers") or []
    lines.extend(f"- {item}" for item in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    warnings = manifest.get("warnings") or []
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("- none")
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- Computer-use live remains blocked.",
            "- Public desktop installer remains blocked.",
            "- Fallow fix evidence is dry-run only.",
            "- Feedback bundle is local-only and redacted.",
            "",
        ]
    )
    return "\n".join(lines)


def _copy_release_artifacts(*, evidence_root: Path, output_root: Path) -> dict[str, bool]:
    items = {
        "design-partner-pilot": evidence_root / "design-partner-pilot",
        "code-intelligence/fallow": evidence_root / "code-intelligence" / "fallow",
        "external-agent-v1-1": evidence_root / "external-agent-v1-1",
        "pilot-ops": evidence_root / "pilot-ops",
        "ci": evidence_root / "ci",
        "security-review": evidence_root / "security-review",
    }
    copied: dict[str, bool] = {}
    for name, source in items.items():
        destination = output_root / name
        copied[name] = _copy_path(source, destination)
    return copied


def _copy_path(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    if source.is_dir():
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        return True
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def _checks(
    *,
    copied: dict[str, bool],
    pilot_manifest: dict[str, Any] | None,
    code_intelligence: dict[str, Any],
    pilot_operations: dict[str, Any],
    ci_inventory: dict[str, Any] | None,
    external_v1_1: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    return [
        _copied_check("pilot-pack", "Design partner pilot pack", copied["design-partner-pilot"]),
        _status_check(
            "code-intelligence",
            "Fallow code intelligence",
            code_intelligence.get("status"),
            blocking_statuses={"blocked"},
            detail=f"verdict={code_intelligence.get('verdict')}",
        ),
        _status_check(
            "external-agent-v1-1",
            "External Agent Gateway v1.1",
            external_v1_1.get("status") if external_v1_1 else None,
            pass_statuses={"pass"},
            detail=f"cases={len(external_v1_1.get('cases', [])) if external_v1_1 else 0}",
        ),
        _status_check(
            "pilot-operations",
            "Pilot operations loop",
            pilot_operations.get("status"),
            blocking_statuses={"blocked"},
            detail=f"feedback={pilot_operations.get('feedbackBundlePath')}",
        ),
        _status_check(
            "ci-node24-inventory",
            "CI Node action inventory",
            ci_inventory.get("status") if ci_inventory else None,
            pass_statuses={"pass"},
            detail=(
                "node20Warning="
                f"{ci_inventory.get('node20WarningPresent') if ci_inventory else 'missing'}"
            ),
        ),
        _safety_check(pilot_manifest),
        _copied_check("security-review", "Security review artifacts", copied["security-review"]),
    ]


def _copied_check(check_id: str, label: str, present: bool) -> dict[str, Any]:
    return {
        "checkId": check_id,
        "label": label,
        "status": "ready" if present else "blocked",
        "detail": "present" if present else "missing",
        "blocking": not present,
    }


def _status_check(
    check_id: str,
    label: str,
    raw_status: Any,
    *,
    pass_statuses: set[str] | None = None,
    blocking_statuses: set[str] | None = None,
    detail: str,
) -> dict[str, Any]:
    pass_values = pass_statuses or {"ready"}
    block_values = blocking_statuses or {"blocked", "fail", "failed", None}
    raw = str(raw_status) if raw_status is not None else None
    status = "ready" if raw in pass_values else "blocked" if raw in block_values else "conditional"
    return {
        "checkId": check_id,
        "label": label,
        "status": status,
        "detail": detail,
        "blocking": status == "blocked",
    }


def _safety_check(pilot_manifest: dict[str, Any] | None) -> dict[str, Any]:
    claims = pilot_manifest.get("claimGuard", {}).get("claims", []) if pilot_manifest else []
    by_id = {
        str(item.get("claim_id")): item
        for item in claims
        if isinstance(item, dict)
    }
    enterprise_ready = by_id.get("enterprise-self-hosted-agent-control-plane", {}).get(
        "status"
    ) == "allowed"
    public_blocked = by_id.get("public-desktop-installer", {}).get("status") == "blocked"
    computer_blocked = by_id.get("live-macos-computer-use", {}).get("status") == "blocked"
    passed = enterprise_ready and public_blocked and computer_blocked
    return {
        "checkId": "safety-claims",
        "label": "Safety claim guardrails",
        "status": "ready" if passed else "blocked",
        "detail": (
            f"enterprise={enterprise_ready}; publicDesktopBlocked={public_blocked}; "
            f"computerUseBlocked={computer_blocked}"
        ),
        "blocking": not passed,
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
