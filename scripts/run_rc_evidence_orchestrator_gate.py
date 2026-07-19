from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "release-gates" / "mainline-rc"


def _run(command: list[str], *, cwd: Path = REPO_ROOT) -> dict[str, object]:
    run_command = _resolve_command(command)
    try:
        result = subprocess.run(
            run_command,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
        )
    except FileNotFoundError as exc:
        return {
            "command": command,
            "returnCode": 127,
            "tail": [str(exc)],
            "status": "fail",
        }
    tail = result.stdout.splitlines()[-20:]
    return {
        "command": command,
        "returnCode": result.returncode,
        "tail": tail,
        "status": "pass" if result.returncode == 0 else "fail",
    }


def _resolve_command(command: list[str]) -> list[str]:
    executable = command[0]
    candidates = [executable]
    if os.name == "nt" and Path(executable).suffix == "":
        candidates = [f"{executable}.cmd", f"{executable}.exe", executable]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return [resolved, *command[1:]]
    return command


def _append(results: list[dict[str, object]], command: list[str], *, cwd: Path = REPO_ROOT) -> bool:
    result = _run(command, cwd=cwd)
    results.append(result)
    return result["returnCode"] == 0


def _command_status(results: list[dict[str, object]]) -> str:
    return "pass" if all(result["returnCode"] == 0 for result in results) else "fail"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the RC evidence orchestrator cross-platform release gate."
    )
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--target", default="mainline-rc")
    parser.add_argument("--mode", default="rc-focused")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--skip-ui", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = REPO_ROOT / output_root
    ledger_path = output_root / "gate_evidence_ledger.json"

    commands: list[list[str]] = [
        [
            "uv",
            "run",
            "--extra",
            "dev",
            "python",
            "-m",
            "pytest",
            "-q",
            "tests/test_release_gate_models.py",
            "tests/test_release_gate_plan.py",
            "tests/test_release_gate_runner.py",
            "tests/test_release_gate_verifier.py",
            "tests/test_release_gate_contracts.py",
            "tests/test_rc_freeze_backfill.py",
            "tests/test_release_gate_cli.py",
            "tests/test_rc_freeze_manifest.py",
            "tests/test_control_plane_snapshot_rc_gate_evidence.py",
        ],
        ["uv", "run", "python", "scripts/generate_release_gate_contract_schemas.py"],
        ["uv", "run", "python", "scripts/generate_control_plane_contract_schemas.py"],
        [
            "uv",
            "run",
            "imperaos",
            "release",
            "gates",
            "plan",
            "--target",
            args.target,
            "--profile",
            args.profile,
            "--mode",
            args.mode,
            "--output-root",
            str(output_root),
            "--json",
        ],
        [
            "uv",
            "run",
            "imperaos",
            "release",
            "gates",
            "run",
            "--target",
            args.target,
            "--profile",
            args.profile,
            "--mode",
            args.mode,
            "--output-root",
            str(output_root),
            "--json",
        ],
        [
            "uv",
            "run",
            "imperaos",
            "release",
            "gates",
            "verify",
            "--ledger",
            str(ledger_path),
            "--json",
        ],
        [
            "uv",
            "run",
            "imperaos",
            "release",
            "gates",
            "export",
            "--ledger",
            str(ledger_path),
            "--output-root",
            str(output_root),
            "--json",
        ],
        [
            "uv",
            "run",
            "imperaos",
            "control-plane",
            "release",
            "gates",
            "snapshot",
            "--profile",
            args.profile,
            "--evidence-root",
            str(output_root),
            "--json",
        ],
        ["git", "diff", "--check"],
    ]

    if not args.skip_ui:
        commands.extend(
            [
                [
                    "corepack",
                    "pnpm",
                    "--dir",
                    "apps/operator-panel",
                    "exec",
                    "vitest",
                    "run",
                    "src/rc-gate-evidence/RcGateEvidenceView.test.tsx",
                    "src/rc-gate-evidence/rcGateEvidenceMappers.test.ts",
                    "src/routeRegistry.test.ts",
                    "src/control-plane/controlPlaneSnapshot.test.ts",
                ],
                ["corepack", "pnpm", "--dir", "apps/operator-panel", "lint"],
                ["corepack", "pnpm", "--dir", "apps/operator-panel", "build"],
                [
                    "corepack",
                    "pnpm",
                    "--dir",
                    "apps/operator-panel",
                    "exec",
                    "playwright",
                    "test",
                    "e2e/rc-gate-evidence.spec.ts",
                    "--pass-with-no-tests",
                ],
            ]
        )

    results: list[dict[str, object]] = []
    for command in commands:
        passed = _append(results, command)
        if not passed:
            break

    payload = {
        "schemaVersion": "control-plane.rc-evidence-orchestrator-gate/v1",
        "status": _command_status(results),
        "profile": args.profile,
        "target": args.target,
        "mode": args.mode,
        "outputRoot": str(output_root),
        "ledgerPath": str(ledger_path),
        "makeRequired": False,
        "rawPersistence": False,
        "commands": results,
    }
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload["status"])
    if payload["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
