from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.control_plane.claim_guard import ClaimGuard
from imperaos.control_plane.pilot_metrics import build_pilot_metrics
from imperaos.control_plane.security_review import scan_no_secrets
from imperaos.control_plane.snapshot import build_control_plane_snapshot
from imperaos.runtime.config import RuntimeConfig

PILOT_PACK_VERSION = "control-plane.design-partner-pilot-pack/v1"


def generate_design_partner_pilot_pack(
    *,
    output_root: Path,
    config: RuntimeConfig,
    snapshot_path: Path | None = None,
    hat_a_closure_path: Path = Path("artifacts/enterprise-hat-a/enterprise_hat_a_closure.json"),
    install_rehearsal_path: Path = Path("artifacts/install-rehearsal/report.json"),
    external_agent_report_path: Path = Path(
        "artifacts/design-partner-pilot/external-agent-pilot-report.json"
    ),
    governance_admin_report_path: Path = Path(
        "artifacts/design-partner-pilot/governance-admin-report.json"
    ),
    evidence_corpus_report_path: Path = Path("artifacts/evidence-corpus/corpus_report.json"),
    security_review_root: Path = Path("artifacts/security-review"),
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    snapshot_payload = _snapshot_payload(
        config=config,
        snapshot_path=snapshot_path,
        output_path=output_root / "control-plane-snapshot.json",
    )
    claim_matrix = ClaimGuard(config=config).evaluate(evidence_root="artifacts")
    _write_json(output_root / "claim-guard-matrix.json", claim_matrix.model_dump(mode="json"))

    copied = {
        "enterprise-hat-a-closure.json": _copy(
            hat_a_closure_path,
            output_root / "enterprise-hat-a-closure.json",
        ),
        "install-rehearsal-report.json": _copy(
            install_rehearsal_path,
            output_root / "install-rehearsal-report.json",
        ),
        "external-agent-pilot-report.json": _copy(
            external_agent_report_path,
            output_root / "external-agent-pilot-report.json",
        ),
        "governance-admin-report.json": _copy(
            governance_admin_report_path,
            output_root / "governance-admin-report.json",
        ),
        "evidence-corpus-report.json": _copy(
            evidence_corpus_report_path,
            output_root / "evidence-corpus-report.json",
        ),
    }
    if security_review_root.exists():
        destination = output_root / "security-review"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(security_review_root, destination)
        copied["security-review"] = True
    _write_demo_runbook(output_root / "pilot-demo-runbook.md")

    metrics = build_pilot_metrics(
        output_path=output_root / "pilot_metrics.json",
        external_agent_report_path=output_root / "external-agent-pilot-report.json",
        governance_report_path=output_root / "governance-admin-report.json",
        evidence_corpus_report_path=output_root / "evidence-corpus-report.json",
        claim_guard_matrix_path=output_root / "claim-guard-matrix.json",
    )
    no_secret = scan_no_secrets(output_root)
    _write_json(output_root / "no-secret-scan.json", no_secret)

    blockers = _pack_blockers(copied=copied, no_secret=no_secret, claim_matrix=claim_matrix)
    warnings = _pack_warnings(snapshot_payload=snapshot_payload, metrics=metrics)
    status = "blocked" if blockers else "conditional" if warnings else "ready"
    manifest = {
        "version": PILOT_PACK_VERSION,
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "packId": f"design-partner-pilot-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "status": status,
        "commitSha": _git_commit(),
        "outputRoot": str(output_root),
        "requiredArtifacts": copied,
        "enterpriseHatA": _status_from_file(output_root / "enterprise-hat-a-closure.json"),
        "installRehearsal": _status_from_file(output_root / "install-rehearsal-report.json"),
        "externalAgentPilot": _status_from_file(output_root / "external-agent-pilot-report.json"),
        "governanceAdmin": _status_from_file(output_root / "governance-admin-report.json"),
        "securityReview": _status_from_file(
            output_root / "security-review" / "security_review_pack.json"
        ),
        "pilotMetrics": metrics,
        "claimGuard": claim_matrix.model_dump(mode="json"),
        "blockingReasons": blockers,
        "warnings": warnings,
    }
    _write_json(output_root / "manifest.json", manifest)
    (output_root / "PILOT_LAUNCH_REPORT.md").write_text(
        render_pilot_launch_report(manifest),
        encoding="utf-8",
    )
    return manifest


def render_pilot_launch_report(manifest: dict[str, Any]) -> str:
    lines = [
        "# Design Partner Pilot Launch Report",
        "",
        f"- Status: `{manifest['status']}`",
        f"- Commit: `{manifest['commitSha']}`",
        f"- Generated: `{manifest['generatedAtUtc']}`",
        "",
        "## Claims",
        "",
        "- Enterprise self-hosted Agent Control Plane can be ready only with signed closure.",
        "- Computer-use live remains blocked.",
        "- Public desktop installer remains blocked.",
        "",
        "## Required Artifacts",
        "",
    ]
    for name, present in manifest["requiredArtifacts"].items():
        lines.append(f"- {name}: {'present' if present else 'missing'}")
    lines.extend(["", "## Blocking Reasons", ""])
    blockers = manifest.get("blockingReasons") or []
    lines.extend(f"- {item}" for item in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    warnings = manifest.get("warnings") or []
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("- none")
    return "\n".join(lines) + "\n"


def _snapshot_payload(
    *,
    config: RuntimeConfig,
    snapshot_path: Path | None,
    output_path: Path,
) -> dict[str, Any]:
    if snapshot_path is not None and snapshot_path.exists():
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    else:
        snapshot = build_control_plane_snapshot(
            root_dir=output_path.parent / "state" / "control-plane",
            profile=config.profile_name,
            evidence_root="artifacts/evidence-corpus/valid",
            runtime_mode="cli",
            bridge_mode="cli",
            used_fixture=False,
        )
        payload = snapshot.model_dump(mode="json", by_alias=True)
    _write_json(output_path, payload)
    return payload


def _copy(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == destination.resolve():
        return True
    shutil.copy2(source, destination)
    return True


def _pack_blockers(
    *,
    copied: dict[str, bool],
    no_secret: dict[str, Any],
    claim_matrix: Any,
) -> list[str]:
    blockers = [f"MISSING_ARTIFACT:{name}" for name, present in copied.items() if not present]
    if no_secret["status"] != "pass":
        blockers.append("PILOT_PACK_SECRET_SCAN_FAILED")
    claims = {item.claim_id: item.status for item in claim_matrix.claims}
    if claims.get("enterprise-self-hosted-agent-control-plane") != "allowed":
        blockers.append("ENTERPRISE_HAT_A_NOT_READY")
    if claims.get("public-desktop-installer") != "blocked":
        blockers.append("PUBLIC_DESKTOP_FALSE_READY")
    for claim_id in (
        "live-macos-computer-use",
        "live-windows-computer-use",
        "live-linux-computer-use",
    ):
        if claims.get(claim_id) != "blocked":
            blockers.append(f"COMPUTER_USE_FALSE_READY:{claim_id}")
    return sorted(set(blockers))


def _pack_warnings(*, snapshot_payload: dict[str, Any], metrics: dict[str, Any]) -> list[str]:
    warnings = []
    design_partner = snapshot_payload.get("designPartnerRc")
    if isinstance(design_partner, dict) and design_partner.get("status") == "blocked":
        warnings.append("RC_SNAPSHOT_BLOCKED")
    if metrics.get("runCount") == 0:
        warnings.append("PILOT_METRICS_EMPTY")
    return warnings


def _status_from_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "invalid"}
    if isinstance(payload.get("data"), dict):
        payload = payload["data"]
    return {
        "status": payload.get("status") or payload.get("claimStatus") or "present",
        "path": str(path),
    }


def _write_demo_runbook(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Pilot Demo Runbook",
                "",
                "1. Review Enterprise Hat A closure and claim matrix.",
                "2. Run install rehearsal and inspect support bundle safety.",
                "3. Show external agent read-only, approval-gated, and denied flows.",
                "4. Review governance admin signed audit and rollback plan.",
                "5. Export security review summary and no-secret scan.",
                "",
            ]
        ),
        encoding="utf-8",
    )


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
