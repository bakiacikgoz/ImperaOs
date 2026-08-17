from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def _run(command: list[str]) -> dict[str, object]:
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
        return {"command": command, "returnCode": 127, "status": "fail", "tail": [str(exc)]}
    return {
        "command": command,
        "returnCode": result.returncode,
        "status": "pass" if result.returncode == 0 else "fail",
        "tail": result.stdout.splitlines()[-20:],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RC release decision dossier gate.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--artifact-root", default="artifacts")
    parser.add_argument("--output-root", default="artifacts/rc-release-decision")
    parser.add_argument("--skip-ui", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    dossier_path = output_root / "release_decision_dossier.json"
    commands: list[list[str]] = [
        ["uv", "run", "--extra", "dev", "ruff", "check", "."],
        [
            "uv",
            "run",
            "--extra",
            "dev",
            "python",
            "-m",
            "pytest",
            "-q",
            "tests/test_release_decision_models.py",
            "tests/test_rc_freeze_reconciliation.py",
            "tests/test_release_no_ship_register.py",
            "tests/test_release_human_signoff.py",
            "tests/test_release_decision_dossier.py",
            "tests/test_release_decision_cli.py",
            "tests/test_release_decision_contracts.py",
            "tests/test_control_plane_snapshot_rc_release_decision.py",
        ],
        ["uv", "run", "python", "scripts/generate_release_decision_contract_schemas.py"],
        ["uv", "run", "python", "scripts/generate_control_plane_contract_schemas.py"],
        ["git", "diff", "--exit-code", "contracts/release_decision"],
        [
            "uv",
            "run",
            "imperaos",
            "release",
            "decision",
            "build",
            "--profile",
            args.profile,
            "--artifact-root",
            args.artifact_root,
            "--output-root",
            args.output_root,
            "--json",
        ],
        [
            "uv",
            "run",
            "imperaos",
            "release",
            "decision",
            "verify",
            "--dossier",
            str(dossier_path),
            "--allow-conditional",
            "--json",
        ],
        [
            "uv",
            "run",
            "imperaos",
            "release",
            "decision",
            "signoff-template",
            "--dossier-sha256",
            "0" * 64,
            "--role",
            "release_owner",
            "--output",
            str(output_root / "signoff" / "release_owner.template.json"),
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
                    "src/release-decision/ReleaseDecisionView.test.tsx",
                    "src/release-decision/releaseDecisionMappers.test.ts",
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
                    "e2e/rc-release-decision.spec.ts",
                    "--pass-with-no-tests",
                ],
            ]
        )

    results: list[dict[str, object]] = []
    for command in commands:
        result = _run(command)
        results.append(result)
        if result["returnCode"] != 0:
            break
    status = "pass" if all(result["returnCode"] == 0 for result in results) else "fail"
    payload = {
        "schemaVersion": "release.rc-release-decision-gate/v1",
        "status": status,
        "profile": args.profile,
        "artifactRoot": args.artifact_root,
        "outputRoot": args.output_root,
        "makeRequired": False,
        "commands": results,
    }
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(status)
    if status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
