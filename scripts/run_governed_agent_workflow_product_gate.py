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

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "product-complete" / "governed-workflow"


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
    try:
        result = subprocess.run(
            _resolve(command),
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
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
    return {
        "name": name,
        "command": command,
        "required": required,
        "returnCode": result.returncode,
        "status": "pass" if result.returncode == 0 else "fail",
        "reasonCode": "OK" if result.returncode == 0 else "COMMAND_FAILED",
        "durationMs": int((time.monotonic() - started) * 1000),
        "tail": result.stdout.splitlines()[-25:],
    }


def build_command_plan(profile: str, output_root: Path) -> list[dict[str, Any]]:
    return [
        {
            "name": "enterprise_workspace_onboarding",
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
            "name": "governed_workflow_demo",
            "command": [
                "uv",
                "run",
                "python",
                "-m",
                "imperaos",
                "product",
                "demo",
                "run-governed-workflow",
                "--profile",
                profile,
                "--mode",
                "dry-run",
                "--output-root",
                str(output_root / "demo"),
                "--json",
            ],
            "required": True,
        },
        {
            "name": "memory_smoke",
            "command": [
                "uv",
                "run",
                "python",
                "-m",
                "imperaos",
                "product",
                "demo",
                "memory-smoke",
                "--profile",
                profile,
                "--workspace-id",
                "pilot-workspace",
                "--json",
            ],
            "required": True,
        },
        {
            "name": "external_gateway_smoke",
            "command": [
                "uv",
                "run",
                "python",
                "scripts/run_external_agent_gateway_smoke.py",
                "--profile",
                profile,
                "--output",
                str(
                    output_root
                    / "external_gateway"
                    / "external_gateway_smoke.json"
                ),
            ],
            "required": True,
        },
        {
            "name": "support_bundle_redaction",
            "command": [
                "uv",
                "run",
                "--extra",
                "dev",
                "python",
                "-m",
                "pytest",
                "-q",
                "tests/test_product_demo_cli.py",
                "tests/test_product_support_bundle_redaction.py",
            ],
            "required": True,
        },
    ]


def run_governed_workflow_gate(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    profile: str = "enterprise",
    skip_commands: bool = False,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []
    if not skip_commands:
        for item in build_command_plan(profile, output_root):
            result = _run(item["command"], name=item["name"], required=item["required"])
            checks.append(result)
            if result["required"] and result["returnCode"] != 0:
                break
    blockers = [
        f"GOVERNED_WORKFLOW_CHECK_FAILED:{check['name']}"
        for check in checks
        if check["required"] and check["returnCode"] != 0
    ]
    status = "pass" if not blockers else "fail"
    report = {
        "schemaVersion": "product-complete.governed-workflow-gate/v1",
        "generatedAtUtc": _now(),
        "profile": profile,
        "status": status,
        "productReadiness": {"governedWorkflow": "pass" if not blockers else "fail"},
        "checks": checks,
        "noShipBlockers": blockers,
        "artifacts": [
            "artifacts/product-complete/governed-workflow/governed_workflow_gate.json",
            "artifacts/product-complete/governed-workflow/governed_workflow_gate.md",
        ],
    }
    (output_root / "governed_workflow_gate.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_root / "governed_workflow_gate.md").write_text(
        render_markdown(report),
        encoding="utf-8",
    )
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Governed Agent Workflow Product Gate",
        "",
        f"- Status: `{report['status']}`",
        f"- Profile: `{report['profile']}`",
        "",
        "## Checks",
    ]
    for check in report["checks"]:
        lines.append(f"- `{check['status']}` `{check['name']}` `{check['reasonCode']}`")
    if report["noShipBlockers"]:
        lines.extend(["", "## No-Ship Blockers"])
        lines.extend(f"- `{item}`" for item in report["noShipBlockers"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run governed workflow product gate.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--skip-commands", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = run_governed_workflow_gate(
        output_root=args.output_root,
        profile=args.profile,
        skip_commands=args.skip_commands,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"status={report['status']} output={args.output_root}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
