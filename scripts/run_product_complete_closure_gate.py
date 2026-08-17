from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.release.product_complete import build_product_complete_no_ship_register

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "product-complete-closure"
COMMAND_TIMEOUT_SECONDS = 1800

READINESS_CHECKS = {
    "assistant": "assistant_real_runtime_gate",
    "operatorPanel": "operator_panel_static",
    "enterpriseWorkspace": "enterprise_workspace_onboarding_gate",
    "governedWorkflow": "governed_agent_workflow_product_gate",
    "installerFirstRun": "first_run_readiness_gate",
    "evidence": "evidence_release_closure_gate",
}
REQUIRED_READINESS = frozenset(READINESS_CHECKS)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _resolve(command: list[str]) -> list[str]:
    executable = command[0]
    candidates = [executable]
    if os.name == "nt" and Path(executable).suffix == "":
        candidates = [f"{executable}.cmd", f"{executable}.exe", executable]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return [resolved, *command[1:]]
    return command


def _run(command: list[str], *, name: str, required: bool = True) -> dict[str, Any]:
    started = time.monotonic()
    env = {**os.environ, "COREPACK_ENABLE_AUTO_PIN": "0"}
    try:
        result = subprocess.run(
            _resolve(command),
            cwd=REPO_ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        return {
            "name": name,
            "command": command,
            "required": required,
            "returnCode": 127,
            "status": "fail",
            "reasonCode": "EXECUTABLE_MISSING",
            "tail": [str(exc)],
        }
    except subprocess.TimeoutExpired as exc:
        captured = exc.output or ""
        if isinstance(captured, bytes):
            captured = captured.decode("utf-8", errors="replace")
        return {
            "name": name,
            "command": command,
            "required": required,
            "returnCode": 124,
            "status": "fail",
            "reasonCode": "COMMAND_TIMEOUT",
            "durationMs": int((time.monotonic() - started) * 1000),
            "tail": str(captured).splitlines()[-30:],
        }
    status = "pass" if result.returncode == 0 else "fail"
    reason = "OK" if result.returncode == 0 else "COMMAND_FAILED"
    if name == "macos_local_trial_gate" and result.returncode == 3:
        status = "conditional"
        reason = "MACOS_LOCAL_TRIAL_CONDITIONAL"
    return {
        "name": name,
        "command": command,
        "required": required,
        "returnCode": result.returncode,
        "status": status,
        "reasonCode": reason,
        "durationMs": int((time.monotonic() - started) * 1000),
        "tail": result.stdout.splitlines()[-30:],
    }


def _git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def build_command_plan(
    profile: str, output_root: Path, *, include_local_trial: bool = False
) -> list[dict[str, Any]]:
    plan = [
        {
            "name": "scope_gate",
            "readiness": None,
            "command": [
                "uv",
                "run",
                "python",
                "scripts/run_product_complete_scope_gate.py",
                "--output-root",
                str(output_root / "scope"),
                "--json",
            ],
            "required": True,
        },
        {
            "name": "assistant_real_runtime_gate",
            "readiness": "assistant",
            "command": [
                "uv",
                "run",
                "python",
                "scripts/run_assistant_real_runtime_gate.py",
                "--profile",
                profile,
                "--json",
            ],
            "required": True,
        },
        {
            "name": "operator_panel_static",
            "readiness": "operatorPanel",
            "command": [
                "corepack",
                "pnpm",
                "--dir",
                "apps/operator-panel",
                "exec",
                "tsx",
                "scripts/assert-no-inert-primary-actions.ts",
            ],
            "required": True,
        },
        {
            "name": "first_run_readiness_gate",
            "readiness": "installerFirstRun",
            "command": [
                "uv",
                "run",
                "python",
                "scripts/run_first_run_readiness_gate.py",
                "--profile",
                profile,
                "--json",
            ],
            "required": True,
        },
        {
            "name": "enterprise_workspace_onboarding_gate",
            "readiness": "enterpriseWorkspace",
            "command": [
                "uv",
                "run",
                "python",
                "scripts/run_enterprise_workspace_onboarding_gate.py",
                "--profile",
                profile,
                "--skip-ui",
                "--json",
            ],
            "required": True,
        },
        {
            "name": "governed_agent_workflow_product_gate",
            "readiness": "governedWorkflow",
            "command": [
                "uv",
                "run",
                "python",
                "scripts/run_governed_agent_workflow_product_gate.py",
                "--profile",
                profile,
                "--json",
            ],
            "required": True,
        },
        {
            "name": "evidence_release_closure_gate",
            "readiness": "evidence",
            "command": [
                "uv",
                "run",
                "python",
                "scripts/run_enterprise_workspace_release_closure_gate.py",
                "--profile",
                profile,
                "--pytest-mode",
                "targeted",
                "--json",
            ],
            "required": True,
        },
        {
            "name": "git_diff_check",
            "readiness": None,
            "command": ["git", "diff", "--check"],
            "required": True,
        },
    ]
    if include_local_trial:
        plan.append(
            {
                "name": "macos_local_trial_gate",
                "readiness": "macosLocalTrial",
                "command": [
                    "uv",
                    "run",
                    "python",
                    "scripts/run_macos_local_trial_gate.py",
                    "--profile",
                    profile,
                    "--output-root",
                    str(output_root / "macos-local-trial"),
                    "--json",
                ],
                "required": True,
            }
        )
    return plan


def _empty_readiness() -> dict[str, str]:
    return {
        "assistant": "not_run",
        "operatorPanel": "not_run",
        "enterpriseWorkspace": "not_run",
        "governedWorkflow": "not_run",
        "installerFirstRun": "not_run",
        "evidence": "not_run",
        "macosLocalTrial": "not_run",
    }


def _readiness_evidence(
    readiness: dict[str, str], checks: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    by_name = {str(check["name"]): check for check in checks}
    evidence: dict[str, dict[str, Any]] = {}
    for readiness_key, check_name in READINESS_CHECKS.items():
        check = by_name.get(check_name)
        evidence[readiness_key] = {
            "checkName": check_name,
            "status": readiness[readiness_key],
            "artifactRef": check.get("artifactRef") if check else None,
        }
    return evidence


def run_product_complete_closure_gate(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    profile: str = "enterprise",
    skip_commands: bool = False,
    include_local_trial: bool = False,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []
    readiness = _empty_readiness()
    if not skip_commands:
        for item in build_command_plan(
            profile, output_root, include_local_trial=include_local_trial
        ):
            result = _run(item["command"], name=item["name"], required=item["required"])
            checks.append(result)
            readiness_key = item.get("readiness")
            if readiness_key and result["status"] == "fail":
                readiness[str(readiness_key)] = "fail"
            elif readiness_key and result["status"] == "conditional":
                readiness[str(readiness_key)] = "conditional"
            elif readiness_key and result["status"] == "pass":
                readiness[str(readiness_key)] = "pass"
            if result["required"] and result["status"] == "fail":
                break
    no_ship_register = build_product_complete_no_ship_register()
    blockers = [
        f"PRODUCT_COMPLETE_CHECK_FAILED:{check['name']}"
        for check in checks
        if check["required"] and check["status"] == "fail"
    ]
    blockers.extend(
        f"PRODUCT_COMPLETE_REQUIRED_CHECK_NOT_RUN:{key}"
        for key in sorted(REQUIRED_READINESS)
        if readiness[key] == "not_run"
    )
    blockers.extend(item.reason_code for item in no_ship_register.items if item.status == "open")
    status = "pass" if not blockers else "fail"
    report = {
        "schemaVersion": "product-complete.closure/v1",
        "generatedAtUtc": _now(),
        "profile": profile,
        "status": status,
        "branch": _git(["branch", "--show-current"]),
        "headSha": _git(["rev-parse", "HEAD"]),
        "checks": checks,
        "noShipBlockers": blockers,
        "conditionalNotes": _conditional_notes(checks),
        "artifacts": {
            "json": "artifacts/product-complete-closure/product_complete_closure_report.json",
            "markdown": "artifacts/product-complete-closure/product_complete_closure_report.md",
            "prBody": "artifacts/product-complete-closure/product_complete_pr_body.md",
            "noShipRegister": "artifacts/product-complete-closure/no_ship_register.json",
        },
        "ci": {},
        "rawLeakScan": {},
        "productReadiness": readiness,
        "readinessEvidence": _readiness_evidence(readiness, checks),
    }
    _write_outputs(output_root, report, no_ship_register.model_dump(mode="json", by_alias=True))
    return report


def _write_outputs(
    output_root: Path,
    report: dict[str, Any],
    no_ship_register: dict[str, Any],
) -> None:
    (output_root / "product_complete_closure_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_root / "product_complete_closure_report.md").write_text(
        render_markdown(report),
        encoding="utf-8",
    )
    (output_root / "product_complete_pr_body.md").write_text(
        render_pr_body(report),
        encoding="utf-8",
    )
    (output_root / "no_ship_register.json").write_text(
        json.dumps(no_ship_register, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _conditional_notes(checks: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    for check in checks:
        if check["name"] != "macos_local_trial_gate":
            continue
        if check["status"] == "pass":
            notes.append("macOS local trial gate passed.")
        elif check["status"] == "conditional":
            notes.append("macOS local trial has setup-required notes.")
        elif check["status"] == "fail":
            notes.append("macOS local trial is blocked.")
    return notes


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Product-Complete Closure Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Branch: `{report['branch']}`",
        f"- Head SHA: `{report['headSha']}`",
        "",
        "## Product Readiness",
    ]
    for key, value in report["productReadiness"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Checks"])
    for check in report["checks"]:
        lines.append(f"- `{check['status']}` `{check['name']}` `{check['reasonCode']}`")
    if report["conditionalNotes"]:
        lines.extend(["", "## Conditional Notes"])
        lines.extend(f"- {item}" for item in report["conditionalNotes"])
    if report["noShipBlockers"]:
        lines.extend(["", "## No-Ship Blockers"])
        lines.extend(f"- `{item}`" for item in report["noShipBlockers"])
    return "\n".join(lines) + "\n"


def render_pr_body(report: dict[str, Any]) -> str:
    return (
        "## Summary\n"
        "- Product-complete closure gate for ImperaOS.\n"
        "- Scope: self-hosted single-organization enterprise Agent Control Plane.\n\n"
        "## Validation\n"
        f"- Closure gate: `{report['status']}`\n"
        f"- Head SHA: `{report['headSha']}`\n"
        f"- No-ship blockers: `{len(report['noShipBlockers'])}`\n\n"
        "## Remaining External Requirements\n"
        "- Public signed desktop release still requires real certificate/notarization evidence.\n"
        "- Public cloud multi-tenant SaaS remains out of scope.\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run product-complete closure gate.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--skip-commands", action="store_true")
    parser.add_argument("--include-local-trial", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = run_product_complete_closure_gate(
        output_root=args.output_root,
        profile=args.profile,
        skip_commands=args.skip_commands,
        include_local_trial=args.include_local_trial,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"status={report['status']} output={args.output_root}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
