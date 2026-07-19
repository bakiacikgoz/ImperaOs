from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from imperaos import __version__
from imperaos.computer_use.models import ComputerUseMode, RiskClass
from imperaos.computer_use.vision_runtime.approval import validate_approval_snapshot
from imperaos.computer_use.vision_runtime.models import (
    InputActionType,
    NormalizedBBox,
    SurfaceKind,
    VisionAction,
    VisionObservation,
)
from imperaos.computer_use.vision_runtime.policy import UniversalComputerUsePolicy
from imperaos.computer_use.vision_runtime.replay import verify_replay
from imperaos.contracts import OperatorCapabilitiesPayload
from imperaos.runtime.config import ComputerUseRuntimeConfig, resolve_runtime_config
from imperaos.runtime.platform import current_platform

SCHEMA_VERSION = "computer-use-integration-gate/v1"
WINDOWS_NOT_QUALIFIED = "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
ENTRYPOINT_COMMANDS = (
    ("console_version", ("uv", "run", "imperaos", "--version")),
    ("module_version", ("uv", "run", "python", "-m", "imperaos", "--version")),
    (
        "console_capabilities",
        ("uv", "run", "imperaos", "operator", "capabilities", "--json"),
    ),
    (
        "module_capabilities",
        ("uv", "run", "python", "-m", "imperaos", "operator", "capabilities", "--json"),
    ),
)
LEGACY_STATE_ROOT_NAME = "." + "bin" + "liquid"
CURRENT_STATE_ROOT_NAME = ".imperaos"
IGNORED_COPY_NAMES = {
    LEGACY_STATE_ROOT_NAME,
    CURRENT_STATE_ROOT_NAME,
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".worktrees",
    "artifacts",
    "build",
    "dist",
    "node_modules",
    "target",
}


@dataclass(frozen=True)
class CommandProbe:
    command: tuple[str, ...]
    cwd: Path
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def as_report(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "cwd": str(self.cwd),
            "returncode": self.returncode,
            "ok": self.ok,
            "stdout": self.stdout.strip(),
            "stderr": self.stderr.strip(),
            "timed_out": self.timed_out,
        }


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _gate_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("IMPERAOS_")}
    env.pop("VIRTUAL_ENV", None)
    env["NO_COLOR"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["UV_LINK_MODE"] = "copy"
    return env


def run_command(
    command: tuple[str, ...],
    *,
    cwd: Path,
    timeout_s: int = 120,
) -> CommandProbe:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=_gate_env(),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandProbe(
            command=command,
            cwd=cwd,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            timed_out=True,
        )
    return CommandProbe(
        command=command,
        cwd=cwd,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _git(repo: Path, *args: str) -> CommandProbe:
    return run_command(("git", *args), cwd=repo, timeout_s=60)


def _ok(value: Any, expected: Any) -> dict[str, Any]:
    return {"value": value, "expected": expected, "ok": value == expected}


def _branch_hygiene(repo: Path) -> dict[str, Any]:
    status = _git(repo, "status", "--short")
    branch = _git(repo, "branch", "--show-current")
    log = _git(repo, "log", "--oneline", "--decorate", "-5")
    diff_stat = _git(repo, "diff", "--stat", "main...HEAD")
    diff_check = _git(repo, "diff", "--check")
    commit = _git(repo, "rev-parse", "--short", "HEAD")
    return {
        "status_short": status.stdout.splitlines(),
        "branch": branch.stdout.strip(),
        "commit": commit.stdout.strip() or "unknown",
        "log_oneline_decorate_5": log.stdout.splitlines(),
        "diff_stat_main_head": diff_stat.stdout.splitlines(),
        "diff_check": diff_check.as_report(),
    }


def _evaluate_defaults(repo: Path, profile: str) -> dict[str, Any]:
    config, source_map = resolve_runtime_config(profile=profile, root_dir=repo, env={})
    computer_use = config.computer_use
    checks = {
        "runtime_mode": _ok(computer_use.runtime_mode, "legacy_pilot"),
        "vision_enabled": _ok(computer_use.vision_enabled, False),
        "vision_provider": _ok(computer_use.vision_provider, "none"),
        "vision_model": _ok(computer_use.vision_model, None),
        "macos_live_enabled": _ok(computer_use.macos_live_enabled, False),
        "macos_input_backend": _ok(computer_use.macos_input_backend, "disabled"),
        "raw_screenshot_retention": _ok(
            computer_use.raw_screenshot_retention,
            "disabled",
        ),
        "raw_screenshot_max_count": _ok(computer_use.raw_screenshot_max_count, 0),
        "terminal_control": _ok(computer_use.terminal_control, "deny"),
        "platform_qualification_required": _ok(
            computer_use.platform_qualification_required,
            True,
        ),
    }
    return {
        "profile": profile,
        "ok": all(item["ok"] for item in checks.values()),
        "checks": checks,
        "source_map": {
            key: source_map.get(f"computer_use.{key}", "unknown")
            for key in checks
        },
    }


def _run_entrypoint_commands(cwd: Path) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, command in ENTRYPOINT_COMMANDS:
        probe = run_command(command, cwd=cwd, timeout_s=180)
        report = probe.as_report()
        if name.endswith("version") and probe.ok:
            report["version_matches"] = probe.stdout.strip() == __version__
            report["ok"] = bool(report["ok"] and report["version_matches"])
        if name.endswith("capabilities") and probe.ok:
            try:
                payload = json.loads(probe.stdout)
            except json.JSONDecodeError:
                report["json_valid"] = False
                report["ok"] = False
            else:
                report["json_valid"] = True
                report["contract_version"] = payload.get("contractVersion")
        results[name] = report
    return {
        "ok": all(item["ok"] for item in results.values()),
        "commands": results,
    }


def _ignore_copy_names(_directory: str, names: list[str]) -> list[str]:
    ignored: list[str] = []
    for name in names:
        if name in IGNORED_COPY_NAMES or name.endswith(".egg-info"):
            ignored.append(name)
    return ignored


def _copy_repo(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=_ignore_copy_names,
        dirs_exist_ok=False,
    )


def _evaluate_entrypoint_path_matrix(
    repo: Path,
    mode: Literal["all", "current-only"],
) -> dict[str, Any]:
    locations: list[tuple[str, Path, bool]] = [("current", repo, False)]
    temp_root_report: str | None = None
    temp_results: dict[str, Any] = {}

    if mode == "all":
        with tempfile.TemporaryDirectory(prefix="imperaos_gate_") as temp_dir:
            temp_root = Path(temp_dir)
            temp_root_report = str(temp_root)
            copy_targets = [
                ("temp_ascii", temp_root / "imperaos-gate-ascii"),
                ("temp_space", temp_root / "ImperaOS Gate Space"),
                ("temp_unicode", temp_root / "Masaustu Test Alani"),
                ("temp_unicode_native", temp_root / "Masa\u00fcst\u00fc Test Alan\u0131"),
            ]
            for label, target in copy_targets:
                _copy_repo(repo, target)
                locations.append((label, target, True))
            for label, path, copied in locations:
                temp_results[label] = {
                    "path": str(path),
                    "copied": copied,
                    **_run_entrypoint_commands(path),
                }
    else:
        for label, path, copied in locations:
            temp_results[label] = {
                "path": str(path),
                "copied": copied,
                **_run_entrypoint_commands(path),
            }

    return {
        "mode": mode,
        "ok": all(item["ok"] for item in temp_results.values()),
        "temp_root": temp_root_report,
        "locations": temp_results,
    }


def _evaluate_operator_contract(repo: Path) -> dict[str, Any]:
    probe = run_command(
        ("uv", "run", "imperaos", "operator", "capabilities", "--json"),
        cwd=repo,
        timeout_s=180,
    )
    report = {
        "command": probe.as_report(),
        "payload_valid": False,
        "schema_present": (
            repo / "contracts" / "operator_panel" / "schemas" / "operator_capabilities.schema.json"
        ).exists(),
        "contract_version": None,
        "windows_live_blocked": None,
        "vision_runtime_disabled": None,
        "reason_codes": {},
    }
    if not probe.ok:
        report["ok"] = False
        return report
    try:
        payload = json.loads(probe.stdout)
        model = OperatorCapabilitiesPayload.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        report["ok"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        return report

    report["payload_valid"] = True
    report["contract_version"] = model.contract_version
    computer_use_pilot = payload["features"]["computerUsePilot"]
    vision_runtime = payload["features"]["computerUseVisionRuntime"]
    report["reason_codes"] = {
        "computerUsePilot": computer_use_pilot.get("reasonCode"),
        "computerUseVisionRuntime": vision_runtime.get("reasonCode"),
    }
    if current_platform().label == "windows":
        report["windows_live_blocked"] = (
            computer_use_pilot.get("enabled") is False
            and computer_use_pilot.get("reasonCode") == WINDOWS_NOT_QUALIFIED
            and vision_runtime.get("enabled") is False
            and vision_runtime.get("reasonCode") == WINDOWS_NOT_QUALIFIED
        )
    else:
        report["windows_live_blocked"] = True
    report["vision_runtime_disabled"] = vision_runtime.get("enabled") is False
    report["ok"] = bool(
        report["payload_valid"]
        and report["schema_present"]
        and report["windows_live_blocked"]
        and report["vision_runtime_disabled"]
    )
    return report


def _observation(
    *,
    surface_kind: SurfaceKind = SurfaceKind.BROWSER,
    active_app: str = "Safari",
    sensitive_indicators: list[str] | None = None,
) -> VisionObservation:
    return VisionObservation(
        screenshot_hash="a" * 64,
        captured_at=datetime.now(UTC).isoformat(),
        platform="macos",
        active_app=active_app,
        surface_kind=surface_kind,
        sensitive_indicators=sensitive_indicators or [],
        confidence=0.95,
    )


def _action(
    *,
    action_type: InputActionType = InputActionType.CLICK,
    risk_class: RiskClass = RiskClass.MEDIUM,
) -> VisionAction:
    return VisionAction(
        action_id="gate-action-1",
        action_type=action_type,
        target_bbox=NormalizedBBox(x=0.2, y=0.2, w=0.1, h=0.1),
        rationale="Exercise the guarded policy path.",
        expected_effect="Only a safe observed state changes.",
        risk_class=risk_class,
        requires_approval=False,
        confidence=0.91,
    )


def _evaluate_security_invariants() -> dict[str, Any]:
    config = ComputerUseRuntimeConfig()
    policy = UniversalComputerUsePolicy(config)
    sensitive = policy.detect_surface_stop(
        _observation(sensitive_indicators=["password field"]),
        objective="Sign in",
    )
    terminal = policy.classify(
        _action(action_type=InputActionType.TYPE_TEXT, risk_class=RiskClass.HIGH),
        _observation(surface_kind=SurfaceKind.TERMINAL, active_app="Terminal"),
        mode=ComputerUseMode.EXECUTE,
    )
    risky = policy.classify(
        _action(),
        _observation(),
        mode=ComputerUseMode.STEP_APPROVAL,
    )
    stale_snapshot = validate_approval_snapshot(
        snapshot={
            "created_at": (datetime.now(UTC) - timedelta(seconds=60)).isoformat(),
            "max_age_ms": 1000,
            "action_hash": "mismatch",
            "policy_hash": "mismatch",
            "before_screenshot_hash": "b" * 64,
            "active_app": "Safari",
            "active_window_title": None,
            "surface_kind": SurfaceKind.BROWSER.value,
        },
        current_observation=_observation(),
        action=_action(),
        policy_hash="policy",
        config=config,
    )
    checks = {
        "sensitive_surface_stops": {
            "ok": sensitive is not None and sensitive.denied is True,
            "reason_code": sensitive.reason_code if sensitive else None,
        },
        "terminal_denied": {
            "ok": terminal.denied is True,
            "reason_code": terminal.reason_code,
        },
        "step_approval_requires_approval": {
            "ok": risky.requires_approval is True and risky.allowed is False,
            "reason_code": risky.reason_code,
        },
        "stale_approval_snapshot_denied": {
            "ok": stale_snapshot.allowed is False,
            "reason_code": stale_snapshot.reason_code,
        },
        "replay_verifier_present": {
            "ok": callable(verify_replay),
            "name": getattr(verify_replay, "__name__", None),
        },
    }
    return {
        "ok": all(item["ok"] for item in checks.values()),
        "checks": checks,
    }


def _evaluate_docs_and_tests(repo: Path) -> dict[str, Any]:
    required = {
        "integration_gate_rfc": repo / "docs" / "RFC_COMPUTER_USE_005_INTEGRATION_GATE.md",
        "vision_qualification_doc": repo / "docs" / "COMPUTER_USE_VISION_QUALIFICATION.md",
        "privacy_model": repo / "docs" / "PRIVACY_MODEL.md",
        "security_model": repo / "docs" / "SECURITY_MODEL.md",
        "console_entrypoint_test": repo / "tests" / "test_console_entrypoint_unicode_path.py",
        "integration_gate_test": repo / "tests" / "test_computer_use_integration_gate.py",
        "privacy_regression_test": repo / "tests" / "test_privacy_regression.py",
        "policy_fail_closed_test": repo / "tests" / "test_policy_fail_closed.py",
        "operator_contract_test": repo / "tests" / "test_operator_contracts.py",
    }
    checks = {
        name: {"path": str(path), "ok": path.exists()}
        for name, path in required.items()
    }
    return {"ok": all(item["ok"] for item in checks.values()), "checks": checks}


def _evaluate_live_release_status(repo: Path) -> dict[str, Any]:
    live_path = repo / "artifacts" / "computer_use_vision_qualification" / "live.json"
    live_blockers: list[str] = []
    live_payload: dict[str, Any] | None = None
    if live_path.exists():
        try:
            live_payload = json.loads(live_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            live_blockers.append("live_macos_qualification_invalid")
        else:
            if live_payload.get("mode") != "live" or live_payload.get("status") != "pass":
                live_blockers.append("live_macos_qualification_not_passing")
    else:
        live_blockers.append("live_macos_qualification_missing")
    return {
        "foundation_merge": "disabled_beta_candidate",
        "public_live_claims": "blocked" if live_blockers else "qualified",
        "live_macos_qualified": not live_blockers,
        "live_evidence_path": str(live_path),
        "live_evidence_present": live_path.exists(),
        "live_evidence_payload": live_payload,
        "live_blockers": live_blockers,
    }


def evaluate_integration_gate(
    *,
    repo: Path,
    profile: str,
    path_check_mode: Literal["all", "current-only"] = "all",
) -> dict[str, Any]:
    hygiene = _branch_hygiene(repo)
    defaults = _evaluate_defaults(repo, profile)
    path_matrix = _evaluate_entrypoint_path_matrix(repo, path_check_mode)
    operator_contract = _evaluate_operator_contract(repo)
    security_invariants = _evaluate_security_invariants()
    docs_and_tests = _evaluate_docs_and_tests(repo)
    release_status = _evaluate_live_release_status(repo)

    checks = {
        "git_diff_check": hygiene["diff_check"]["ok"],
        "defaults_disabled": defaults["ok"],
        "console_entrypoints": path_matrix["ok"],
        "operator_contract": operator_contract["ok"],
        "security_invariants": security_invariants["ok"],
        "docs_and_tests_present": docs_and_tests["ok"],
    }
    blockers = [
        name
        for name, ok in checks.items()
        if not ok
    ]
    merge_ready = not blockers
    status = "pass" if merge_ready else "blocked"
    platform_info = current_platform()
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "merge_ready": merge_ready,
        "release_status": release_status,
        "branch": hygiene["branch"],
        "commit": hygiene["commit"],
        "dirty": bool(hygiene["status_short"]),
        "changed_files": hygiene["status_short"],
        "branch_hygiene": hygiene,
        "defaults": defaults,
        "platform_gates": {
            "current_platform": asdict(platform_info),
            "windows_not_qualified_reason": WINDOWS_NOT_QUALIFIED,
            "live_macos_qualification_blocks_public_claims": bool(
                release_status["live_blockers"]
            ),
            "live_macos_qualification_blocks_foundation_merge": False,
        },
        "operator_contract": operator_contract,
        "security_invariants": security_invariants,
        "entrypoint_path_matrix": path_matrix,
        "docs_and_tests": docs_and_tests,
        "checks": checks,
        "blockers": blockers,
    }


def render_markdown(report: dict[str, Any]) -> str:
    checks = report["checks"]
    lines = [
        "# Computer-Use Integration Gate",
        "",
        f"- Status: `{report['status']}`",
        f"- Merge ready: `{str(report['merge_ready']).lower()}`",
        f"- Branch: `{report['branch']}`",
        f"- Commit: `{report['commit']}`",
        f"- Dirty worktree: `{str(report['dirty']).lower()}`",
        f"- Public live claims: `{report['release_status']['public_live_claims']}`",
        "",
        "## Checks",
        "",
        "| Check | Result |",
        "| --- | --- |",
    ]
    for name, ok in checks.items():
        lines.append(f"| `{name}` | `{'pass' if ok else 'fail'}` |")

    lines.extend(
        [
            "",
            "## Console Path Matrix",
            "",
            "| Location | Result | Path |",
            "| --- | --- | --- |",
        ]
    )
    for name, location in report["entrypoint_path_matrix"]["locations"].items():
        lines.append(
            f"| `{name}` | `{'pass' if location['ok'] else 'fail'}` | `{location['path']}` |"
        )

    live_blockers = report["release_status"]["live_blockers"]
    lines.extend(
        [
            "",
            "## Public Live Blockers",
            "",
            *(f"- `{reason}`" for reason in live_blockers),
        ]
    )
    if not live_blockers:
        lines.append("- None")

    if report["blockers"]:
        lines.extend(["", "## Merge Blockers", ""])
        lines.extend(f"- `{reason}`" for reason in report["blockers"])
    else:
        lines.extend(["", "## Merge Blockers", "", "- None"])
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate computer-use integration gate.")
    parser.add_argument("--profile", default="balanced")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument(
        "--path-check-mode",
        choices=("all", "current-only"),
        default="all",
        help="Use current-only for fast unit tests; all verifies temp ASCII/space/Unicode paths.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()
    report = evaluate_integration_gate(
        repo=root,
        profile=args.profile,
        path_check_mode=args.path_check_mode,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["merge_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
