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
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "assistant-real-runtime"


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


def _extract_json(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


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
        )
    except FileNotFoundError as exc:
        return {
            "name": name,
            "command": command,
            "required": required,
            "returnCode": 127,
            "status": "fail",
            "reasonCode": "EXECUTABLE_MISSING",
            "durationMs": int((time.monotonic() - started) * 1000),
            "tail": [str(exc)],
        }
    parsed_json = _extract_json(result.stdout)
    status = "pass" if result.returncode == 0 else "fail"
    reason = "OK" if result.returncode == 0 else "COMMAND_FAILED"
    if name == "assistant_doctor" and result.returncode == 3:
        status = "conditional"
        reason = "ASSISTANT_SETUP_REQUIRED_DIAGNOSTIC"
    payload = {
        "name": name,
        "command": command,
        "required": required,
        "returnCode": result.returncode,
        "status": status,
        "reasonCode": reason,
        "durationMs": int((time.monotonic() - started) * 1000),
        "tail": result.stdout.splitlines()[-25:],
    }
    if parsed_json is not None:
        payload["json"] = parsed_json
    return payload


def build_command_plan(profile: str) -> list[dict[str, Any]]:
    return [
        {
            "name": "assistant_models",
            "command": [
                "uv",
                "run",
                "python",
                "-m",
                "imperaos",
                "assistant",
                "models",
                "--profile",
                profile,
                "--json",
            ],
            "required": True,
        },
        {
            "name": "assistant_doctor",
            "command": [
                "uv",
                "run",
                "python",
                "-m",
                "imperaos",
                "assistant",
                "doctor",
                "--profile",
                profile,
                "--json",
            ],
            "required": True,
        },
        {
            "name": "assistant_cli_tests",
            "command": [
                "uv",
                "run",
                "--extra",
                "dev",
                "python",
                "-m",
                "pytest",
                "-q",
                "tests/test_assistant_cli.py",
            ],
            "required": True,
        },
        {
            "name": "assistant_frontend_tests",
            "command": [
                "corepack",
                "pnpm",
                "--dir",
                "apps/operator-panel",
                "exec",
                "vitest",
                "run",
                "src/assistant",
                "src/components/assistant",
            ],
            "required": True,
        },
        {
            "name": "tauri_assistant_bridge_tests",
            "command": [
                "cargo",
                "test",
                "-q",
                "--manifest-path",
                "apps/operator-panel/src-tauri/Cargo.toml",
                "--target-dir",
                "apps/operator-panel/src-tauri/target-codex-test",
                "assistant",
            ],
            "required": True,
        },
    ]


def _no_ship_from_results(results: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    doctor = next((item for item in results if item["name"] == "assistant_doctor"), None)
    doctor_json = doctor.get("json") if isinstance(doctor, dict) else None
    if isinstance(doctor_json, dict) and doctor_json.get("previewFallbackAllowed") is True:
        blockers.append("ASSISTANT_PREVIEW_IN_PRODUCT_MODE")
    for result in results:
        if result["required"] and result["status"] == "fail":
            blockers.append(f"ASSISTANT_GATE_CHECK_FAILED:{result['name']}")
    return blockers


def run_assistant_gate(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    profile: str = "enterprise",
    skip_commands: bool = False,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    if not skip_commands:
        for item in build_command_plan(profile):
            result = _run(item["command"], name=item["name"], required=item["required"])
            results.append(result)
            if result["required"] and result["status"] != "pass":
                break
    blockers = _no_ship_from_results(results)
    conditional_notes = [
        f"{result['name']}:{result['reasonCode']}"
        for result in results
        if result.get("status") == "conditional"
    ]
    status = "fail" if blockers else "conditional" if conditional_notes else "pass"
    report = {
        "schemaVersion": "assistant.real-runtime-gate/v1",
        "generatedAtUtc": _now(),
        "profile": profile,
        "status": status,
        "productReadiness": {
            "assistant": "fail" if blockers else "conditional" if conditional_notes else "pass"
        },
        "checks": results,
        "conditionalNotes": conditional_notes,
        "noShipBlockers": blockers,
        "artifacts": [
            "artifacts/assistant-real-runtime/assistant_real_runtime_gate.json",
            "artifacts/assistant-real-runtime/assistant_real_runtime_gate.md",
        ],
    }
    (output_root / "assistant_real_runtime_gate.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_root / "assistant_real_runtime_gate.md").write_text(
        render_markdown(report),
        encoding="utf-8",
    )
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Assistant Real Runtime Gate",
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
    if report.get("conditionalNotes"):
        lines.extend(["", "## Conditional Notes"])
        lines.extend(f"- `{item}`" for item in report["conditionalNotes"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run assistant real runtime product gate.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--skip-commands", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = run_assistant_gate(
        output_root=args.output_root,
        profile=args.profile,
        skip_commands=args.skip_commands,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"status={report['status']} output={args.output_root}")
    return 0 if report["status"] == "pass" else 3 if report["status"] == "conditional" else 1


if __name__ == "__main__":
    raise SystemExit(main())
