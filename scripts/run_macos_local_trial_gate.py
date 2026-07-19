from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "macos-local-trial"

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{8,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|private[_-]?key|password|secret|token)\s*[:=]\s*\S+"),
)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _redact(text: str) -> str:
    redacted = text.replace(str(REPO_ROOT), "<repo>").replace(str(Path.home()), "<home>")
    redacted = SECRET_PATTERNS[0].sub("sk-<redacted>", redacted)
    redacted = SECRET_PATTERNS[1].sub("<token-redacted>", redacted)
    redacted = SECRET_PATTERNS[2].sub("<jwt-redacted>", redacted)
    redacted = SECRET_PATTERNS[3].sub(lambda match: f"{match.group(1)}=<redacted>", redacted)
    return redacted


def _contains_secret_like(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


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


def _run_command(command: list[str]) -> tuple[int, str]:
    env = {**os.environ, "COREPACK_ENABLE_AUTO_PIN": "0"}
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
    return result.returncode, result.stdout


def build_command_plan(profile: str, *, full: bool = False) -> list[dict[str, Any]]:
    plan = [
        {
            "name": "imperaos_version",
            "command": ["uv", "run", "python", "-m", "imperaos", "--version"],
            "required": True,
        },
        {
            "name": "setup_first_run",
            "command": [
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
                "local-enterprise",
                "--json",
            ],
            "required": True,
        },
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
            "name": "computer_use_doctor",
            "command": [
                "uv",
                "run",
                "python",
                "-m",
                "imperaos",
                "computer-use",
                "doctor",
                "--json",
            ],
            "required": True,
        },
        {
            "name": "first_run_readiness_gate",
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
            "name": "assistant_real_runtime_gate",
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
            "name": "product_complete_scope_gate",
            "command": [
                "uv",
                "run",
                "python",
                "scripts/run_product_complete_scope_gate.py",
                "--json",
            ],
            "required": True,
        },
        {
            "name": "operator_panel_bridge_parity",
            "command": [
                "corepack",
                "pnpm",
                "--dir",
                "apps/operator-panel",
                "exec",
                "tsx",
                "scripts/assert-bridge-command-parity.ts",
            ],
            "required": True,
        },
        {
            "name": "tauri_launched_smoke_contract",
            "command": [
                "corepack",
                "pnpm",
                "--dir",
                "apps/operator-panel",
                "exec",
                "tsx",
                "scripts/tauri-launched-smoke.ts",
                "--skip-rust",
            ],
            "required": True,
        },
        {
            "name": "tauri_rust_tests",
            "command": [
                "cargo",
                "test",
                "-q",
                "--manifest-path",
                "apps/operator-panel/src-tauri/Cargo.toml",
                "--target-dir",
                "apps/operator-panel/src-tauri/target-macos-local-trial",
            ],
            "required": True,
        },
    ]
    if full:
        plan.extend(
            [
                {
                    "name": "ruff",
                    "command": ["uv", "run", "--extra", "dev", "ruff", "check", "."],
                    "required": True,
                },
                {
                    "name": "pytest",
                    "command": ["uv", "run", "--extra", "dev", "pytest", "-q"],
                    "required": True,
                },
                {
                    "name": "operator_panel_qa_frontend",
                    "command": ["corepack", "pnpm", "--dir", "apps/operator-panel", "qa:frontend"],
                    "required": True,
                },
            ]
        )
    return plan


def classify_check(
    name: str, return_code: int, parsed_json: dict[str, Any] | None
) -> tuple[Literal["pass", "conditional", "fail"], str]:
    if (
        name == "assistant_doctor"
        and return_code == 3
        and parsed_json
        and parsed_json.get("status") == "setup_required"
    ):
        return "conditional", "ASSISTANT_SETUP_REQUIRED"
    if name == "assistant_real_runtime_gate" and return_code == 3:
        return "conditional", "ASSISTANT_RUNTIME_CONDITIONAL"
    if name == "setup_first_run" and return_code == 3:
        return "conditional", "FIRST_RUN_SETUP_REQUIRED"
    if (
        name == "tauri_launched_smoke_contract"
        and parsed_json
        and parsed_json.get("status") == "conditional"
    ):
        return "conditional", "REAL_LAUNCHED_GUI_PROBE_NOT_EXECUTED"
    if name == "computer_use_doctor" and parsed_json:
        if _computer_use_public_live_claim_allowed(parsed_json):
            return "fail", "COMPUTER_USE_UNQUALIFIED_PUBLIC_LIVE_CLAIM"
        return "pass", "COMPUTER_USE_LIVE_CLAIM_BLOCKED_EXPECTED"
    if return_code == 0:
        return "pass", "OK"
    return "fail", "COMMAND_FAILED"


def _computer_use_public_live_claim_allowed(payload: dict[str, Any]) -> bool:
    if (
        payload.get("publicLiveClaimAllowed") is True
        or payload.get("public_live_claim_allowed") is True
    ):
        return True
    capability = payload.get("capabilityResolution")
    if isinstance(capability, dict) and capability.get("public_live_claim_allowed") is True:
        return True
    platforms = capability.get("platforms") if isinstance(capability, dict) else None
    if isinstance(platforms, dict):
        for value in platforms.values():
            if isinstance(value, dict) and (
                value.get("publicLiveClaimAllowed") is True
                or value.get("public_live_claim_allowed") is True
            ):
                return True
    return False


def _no_ship_boundaries() -> list[str]:
    return [
        "PUBLIC_DESKTOP_RELEASE_REQUIRES_SIGNING_AND_NOTARIZATION_EVIDENCE",
        "LIVE_COMPUTER_USE_REQUIRES_EXPLICIT_OPT_IN_PERMISSIONS_PROVIDER_AND_REPLAY_EVIDENCE",
        "LOCAL_TRIAL_DOES_NOT_CLAIM_PUBLIC_MULTI_TENANT_SAAS_READINESS",
    ]


def run_macos_local_trial_gate(
    *,
    profile: str = "enterprise",
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    full: bool = False,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []
    conditional_notes: list[str] = []
    blockers: list[str] = []
    secret_leak_findings: list[str] = []

    for item in build_command_plan(profile, full=full):
        started = time.monotonic()
        try:
            return_code, output = _run_command(item["command"])
        except FileNotFoundError as exc:
            return_code, output = 127, str(exc)
        parsed_json = _extract_json(output)
        status, reason = classify_check(item["name"], return_code, parsed_json)
        raw_tail = output.splitlines()[-25:]
        tail = [_redact(line) for line in raw_tail]
        if _contains_secret_like("\n".join(raw_tail)):
            secret_leak_findings.append(f"SECRET_LIKE_OUTPUT_REDACTED:{item['name']}")
        check = {
            "name": item["name"],
            "command": item["command"],
            "status": status,
            "reasonCode": reason,
            "returnCode": return_code,
            "required": item["required"],
            "durationMs": int((time.monotonic() - started) * 1000),
            "tail": tail,
        }
        if parsed_json is not None:
            check["json"] = parsed_json
        checks.append(check)
        if status == "conditional":
            conditional_notes.append(f"{item['name']}:{reason}")
        if item["required"] and status == "fail":
            blockers.append(f"MACOS_LOCAL_TRIAL_CHECK_FAILED:{item['name']}:{reason}")
            break

    for check in checks:
        payload = check.get("json")
        if isinstance(payload, dict) and payload.get("previewFallbackAllowed") is True:
            blockers.append("ASSISTANT_PREVIEW_FALLBACK_ALLOWED")

    no_ship_boundaries = _no_ship_boundaries()
    status: Literal["pass", "conditional", "blocked"]
    if blockers:
        status = "blocked"
    elif conditional_notes:
        status = "conditional"
    else:
        status = "pass"
    report = {
        "schemaVersion": "macos.local-trial-gate/v1",
        "generatedAtUtc": _now(),
        "status": status,
        "profile": profile,
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "checks": checks,
        "conditionalNotes": conditional_notes,
        "blockers": blockers,
        "noShipBoundaries": no_ship_boundaries,
        "secretLeakScan": {
            "status": "pass",
            "redactedFindings": secret_leak_findings,
        },
        "artifacts": {
            "json": "artifacts/macos-local-trial/macos_local_trial_gate.json",
            "markdown": "artifacts/macos-local-trial/MACOS_LOCAL_TRIAL_GATE.md",
            "noShipBoundaries": "artifacts/macos-local-trial/no_ship_boundaries.json",
        },
    }
    (output_root / "macos_local_trial_gate.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_root / "MACOS_LOCAL_TRIAL_GATE.md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    (output_root / "no_ship_boundaries.json").write_text(
        json.dumps(
            {
                "schemaVersion": "macos.local-trial.no-ship-boundaries/v1",
                "items": no_ship_boundaries,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# macOS M4 Local Trial Gate",
        "",
        f"- Status: `{report['status']}`",
        f"- Profile: `{report['profile']}`",
        "",
        "## Checks",
    ]
    for check in report["checks"]:
        lines.append(f"- `{check['status']}` `{check['name']}` `{check['reasonCode']}`")
    if report["conditionalNotes"]:
        lines.extend(["", "## Conditional Notes"])
        lines.extend(f"- `{item}`" for item in report["conditionalNotes"])
    if report["blockers"]:
        lines.extend(["", "## Blockers"])
        lines.extend(f"- `{item}`" for item in report["blockers"])
    lines.extend(["", "## No-Ship Boundaries"])
    lines.extend(f"- `{item}`" for item in report["noShipBoundaries"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run macOS M4 local trial readiness gate.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = run_macos_local_trial_gate(
        profile=args.profile, output_root=args.output_root, full=args.full
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"status={report['status']} output={args.output_root}")
    return {"pass": 0, "conditional": 3, "blocked": 1}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
