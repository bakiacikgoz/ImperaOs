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
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "first-run-readiness"


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
    parsed = _extract_json(result.stdout)
    status = "pass" if result.returncode == 0 else "fail"
    reason = "OK" if result.returncode == 0 else "COMMAND_FAILED"
    if name == "setup_first_run" and result.returncode == 3:
        status = "pass"
        reason = "FIRST_RUN_SETUP_REQUIRED_DIAGNOSTIC"
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
    if parsed is not None:
        payload["json"] = parsed
    return payload


def run_first_run_gate(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    profile: str = "enterprise",
    mode: str = "local-enterprise",
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    result = _run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "imperaos",
            "setup",
            "first-run",
            "--profile",
            profile,
            "--mode",
            mode,
            "--json",
        ],
        name="setup_first_run",
        required=True,
    )
    setup_json = result.get("json") if isinstance(result.get("json"), dict) else {}
    conditional_notes = [
        str(item)
        for item in setup_json.get("blockingReasons", [])
        if isinstance(item, str)
    ]
    blockers: list[str] = []
    if result["status"] != "pass":
        blockers.append("FIRST_RUN_DIAGNOSTIC_FAILED")
    if setup_json.get("status") == "blocked":
        blockers.extend(conditional_notes or ["FIRST_RUN_BLOCKED"])
    status = "pass" if not blockers else "fail"
    report = {
        "schemaVersion": "first-run.readiness-gate/v1",
        "generatedAtUtc": _now(),
        "profile": profile,
        "mode": mode,
        "status": status,
        "installerFirstRun": "pass" if not blockers else "fail",
        "checks": [result],
        "conditionalNotes": conditional_notes
        if setup_json.get("status") == "setup_required"
        else [],
        "blockingReasons": blockers,
        "artifacts": [
            "artifacts/first-run-readiness/first_run_readiness_gate.json",
            "artifacts/first-run-readiness/first_run_readiness_gate.md",
        ],
    }
    (output_root / "first_run_readiness_gate.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_root / "first_run_readiness_gate.md").write_text(
        render_markdown(report),
        encoding="utf-8",
    )
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# First-Run Readiness Gate",
        "",
        f"- Status: `{report['status']}`",
        f"- Profile: `{report['profile']}`",
        f"- Mode: `{report['mode']}`",
    ]
    if report["conditionalNotes"]:
        lines.extend(["", "## Conditional Notes"])
        lines.extend(f"- `{item}`" for item in report["conditionalNotes"])
    if report["blockingReasons"]:
        lines.extend(["", "## Blocking Reasons"])
        lines.extend(f"- `{item}`" for item in report["blockingReasons"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run first-run readiness gate.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--mode", default="local-enterprise")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = run_first_run_gate(
        output_root=args.output_root,
        profile=args.profile,
        mode=args.mode,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"status={report['status']} output={args.output_root}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
