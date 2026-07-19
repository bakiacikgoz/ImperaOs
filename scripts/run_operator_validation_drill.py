from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.runtime.paths import TEAM_ARTIFACT_ROOT

SCHEMA_VERSION = "imperaos-operator-validation-drill/v2"
ATTESTATION_SCHEMA_VERSION = "imperaos-non-developer-operator-attestation/v2"


@dataclass(frozen=True)
class CommandSpec:
    name: str
    args: list[str]
    expect_json: bool = True
    timeout_seconds: int = 90


@dataclass(frozen=True)
class CommandResult:
    name: str
    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


CommandRunner = Callable[[CommandSpec], CommandResult]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _default_commands() -> list[CommandSpec]:
    python_bin = sys.executable
    base = [python_bin, "-m", "imperaos"]
    return [
        CommandSpec("version", [*base, "--version"], expect_json=False),
        CommandSpec(
            "balanced_config_resolve",
            [*base, "config", "resolve", "--profile", "balanced", "--json"],
        ),
        CommandSpec("balanced_doctor", [*base, "doctor", "--profile", "balanced", "--json"]),
        CommandSpec("operator_capabilities", [*base, "operator", "capabilities", "--json"]),
        CommandSpec(
            "team_list",
            [*base, "team", "list", "--root-dir", TEAM_ARTIFACT_ROOT, "--json"],
        ),
        CommandSpec(
            "computer_use_doctor_all",
            [*base, "computer-use", "doctor", "--platform", "all", "--json"],
        ),
        CommandSpec(
            "enterprise_keys_status",
            [*base, "keys", "status", "--profile", "enterprise", "--json"],
        ),
        CommandSpec(
            "enterprise_keys_rotate_plan",
            [
                *base,
                "keys",
                "rotate-plan",
                "--profile",
                "enterprise",
                "--next-key-id",
                "operator-validation-next",
                "--json",
            ],
        ),
    ]


def _default_command_runner(spec: CommandSpec) -> CommandResult:
    try:
        proc = subprocess.run(
            spec.args,
            text=True,
            capture_output=True,
            check=False,
            timeout=spec.timeout_seconds,
        )
        return CommandResult(
            name=spec.name,
            args=spec.args,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            name=spec.name,
            args=spec.args,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            timed_out=True,
        )


def _parse_json_output(result: CommandResult) -> tuple[dict[str, Any] | None, str | None]:
    if not result.stdout.strip():
        return None, "stdout_empty"
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return None, f"invalid_json:{exc.msg}"
    if not isinstance(payload, dict):
        return None, "json_not_object"
    return payload, None


def _write_command_evidence(
    *,
    output_root: Path,
    spec: CommandSpec,
    result: CommandResult,
) -> dict[str, Any]:
    command_dir = output_root / "commands"
    command_dir.mkdir(parents=True, exist_ok=True)
    safe_name = spec.name.replace("/", "_")
    stdout_path = command_dir / f"{safe_name}.stdout"
    stderr_path = command_dir / f"{safe_name}.stderr"
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")

    json_payload: dict[str, Any] | None = None
    json_error: str | None = None
    if spec.expect_json and result.returncode == 0:
        json_payload, json_error = _parse_json_output(result)
        if json_payload is not None:
            _write_json(command_dir / f"{safe_name}.json", json_payload)

    return {
        "name": spec.name,
        "args": result.args,
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "expect_json": spec.expect_json,
        "json_parse_status": "pass" if spec.expect_json and json_payload is not None else (
            "not_required" if not spec.expect_json else "fail"
        ),
        "json_error": json_error,
        "stdout_file": f"commands/{safe_name}.stdout",
        "stderr_file": f"commands/{safe_name}.stderr",
        "status": (
            "pass"
            if result.returncode == 0
            and not result.timed_out
            and (not spec.expect_json or json_payload is not None)
            else "fail"
        ),
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _evidence_checks(root: Path) -> list[dict[str, Any]]:
    closure_manifest_path = (
        root
        / "artifacts/release-pack/0.4.1-hat-a-closure-2026-05-13/release_pack_closure_manifest.json"
    )
    closure_manifest = _read_json(closure_manifest_path)
    managed_kms_summary = _read_json(
        root / "artifacts/readiness/2026-05-13/managed_kms_adapter_drill/summary.json"
    )
    managed_kms_report = _read_json(
        root
        / "artifacts/readiness/2026-05-13/managed_kms_adapter_drill"
        / "managed_kms_live_drill.json"
    )
    release_checklist = root / "docs/RELEASE_CHECKLIST.md"
    release_notes = root / "docs/RELEASE_NOTES_HAT_A_CLOSURE_2026-05-13.md"
    operator_unsigned_manifests = sorted(
        (
            root
            / "artifacts/readiness/2026-05-13/operator_panel_internal_unsigned_25814422248"
        ).glob("operator-panel-*/**/*internal-unsigned*.json")
    )

    checks: list[dict[str, Any]] = [
        {
            "name": "closure_manifest_exists",
            "status": "pass" if closure_manifest is not None else "fail",
            "path": str(closure_manifest_path),
        },
        {
            "name": "hat_a_no_ship_empty",
            "status": (
                "pass"
                if closure_manifest is not None
                and len(closure_manifest.get("no_ship", {}).get("hat_a_closure", [])) == 0
                else "fail"
            ),
        },
        {
            "name": "hat_b_remains_blocked",
            "status": (
                "pass"
                if closure_manifest is not None
                and closure_manifest.get("status", {})
                .get("macos_desktop_release", "")
                .startswith("blocked")
                and closure_manifest.get("status", {})
                .get("windows_desktop_release", "")
                .startswith("blocked")
                else "fail"
            ),
        },
        {
            "name": "managed_kms_summary_pass",
            "status": (
                "pass"
                if managed_kms_summary is not None
                and managed_kms_summary.get("status") == "pass"
                and managed_kms_summary.get("report_verified") is True
                else "fail"
            ),
        },
        {
            "name": "managed_kms_no_secret_material",
            "status": (
                "pass"
                if managed_kms_report is not None
                and managed_kms_report.get("data", {}).get(
                    "secret_material_persisted_in_evidence"
                )
                is False
                else "fail"
            ),
        },
        {
            "name": "internal_unsigned_manifests_present",
            "status": "pass" if len(operator_unsigned_manifests) == 3 else "fail",
            "count": len(operator_unsigned_manifests),
        },
        {
            "name": "release_checklist_exists",
            "status": "pass" if release_checklist.exists() else "fail",
            "path": str(release_checklist),
        },
        {
            "name": "closure_release_notes_exists",
            "status": "pass" if release_notes.exists() else "fail",
            "path": str(release_notes),
        },
    ]
    return checks


def _attestation_status(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "status": "not_provided",
            "non_developer_operator_validated": False,
            "notes": (
                "Automated proxy validation only; human non-developer attestation "
                "was not provided."
            ),
        }
    payload = _read_json(path)
    if payload is None:
        return {
            "status": "invalid",
            "non_developer_operator_validated": False,
            "path": str(path),
        }
    required = {
        "schema_version",
        "operator_name",
        "operator_role",
        "non_developer_operator",
        "reviewed_runbook",
        "completed_validation",
        "validation_report_path",
        "release_pack_path",
        "signed_at_utc",
    }
    missing = sorted(required - set(payload))
    string_fields = {
        "schema_version",
        "operator_name",
        "operator_role",
        "validation_report_path",
        "release_pack_path",
        "signed_at_utc",
    }
    empty_fields = sorted(
        field
        for field in string_fields
        if field not in missing and not str(payload.get(field) or "").strip()
    )
    placeholder_candidates = string_fields | {"notes"}
    placeholder_fields = sorted(
        field
        for field in placeholder_candidates
        if field not in missing
        and "REPLACE_WITH_" in str(payload.get(field) or "")
    )
    invalid_fields = [
        field
        for field, expected in {
            "schema_version": ATTESTATION_SCHEMA_VERSION,
            "non_developer_operator": True,
            "reviewed_runbook": True,
            "completed_validation": True,
        }.items()
        if field not in missing and payload.get(field) != expected
    ]
    signed_at_utc = payload.get("signed_at_utc")
    signed_at_valid = _valid_utc_timestamp(signed_at_utc)
    if "signed_at_utc" not in missing and not signed_at_valid:
        invalid_fields.append("signed_at_utc")
    valid = (
        not missing
        and not empty_fields
        and not placeholder_fields
        and not invalid_fields
    )
    return {
        "status": "pass" if valid else "fail",
        "non_developer_operator_validated": bool(valid),
        "path": str(path),
        "missing_fields": missing,
        "empty_fields": empty_fields,
        "placeholder_fields": placeholder_fields,
        "invalid_fields": sorted(set(invalid_fields)),
        "expected_schema_version": ATTESTATION_SCHEMA_VERSION,
    }


def _valid_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == UTC.utcoffset(None)


def _write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Operator Validation Drill",
        "",
        f"Status: `{report['status']}`",
        f"Scope: `{report['validation_scope']}`",
        f"Generated: `{report['generated_at_utc']}`",
        "",
        "## Command Checks",
        "",
    ]
    for item in report["commands"]:
        lines.append(f"- `{item['name']}`: `{item['status']}`")
    lines.extend(["", "## Evidence Checks", ""])
    for item in report["evidence_checks"]:
        lines.append(f"- `{item['name']}`: `{item['status']}`")
    lines.extend(
        [
            "",
            "## Attestation",
            "",
            f"- Status: `{report['operator_attestation']['status']}`",
            (
                "- Non-developer validated: "
                f"`{report['operator_attestation']['non_developer_operator_validated']}`"
            ),
            "",
            (
                "This report is an automated operator proxy validation unless a "
                "separate non-developer operator attestation is provided."
            ),
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_validation(
    *,
    output_root: Path,
    root: Path,
    command_runner: CommandRunner = _default_command_runner,
    operator_attestation_path: Path | None = None,
) -> dict[str, Any]:
    output_root = output_root.resolve()
    if output_root.exists():
        for item in output_root.iterdir():
            if item.is_dir():
                import shutil

                shutil.rmtree(item)
            else:
                item.unlink()
    output_root.mkdir(parents=True, exist_ok=True)

    commands = [
        _write_command_evidence(output_root=output_root, spec=spec, result=command_runner(spec))
        for spec in _default_commands()
    ]
    evidence_checks = _evidence_checks(root)
    attestation = _attestation_status(operator_attestation_path)

    command_status = "pass" if all(item["status"] == "pass" for item in commands) else "fail"
    evidence_status = (
        "pass" if all(item["status"] == "pass" for item in evidence_checks) else "fail"
    )
    proxy_status = "pass" if command_status == "pass" and evidence_status == "pass" else "fail"
    human_attested = attestation["non_developer_operator_validated"] is True
    validation_scope = (
        "non_developer_operator_attested"
        if human_attested
        else "operator_proxy_dry_run"
    )
    status = (
        "pass"
        if proxy_status == "pass"
        and (human_attested or attestation["status"] == "not_provided")
        else "fail"
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _now_iso(),
        "validation_scope": validation_scope,
        "status": status,
        "command_status": command_status,
        "evidence_status": evidence_status,
        "operator_attestation": attestation,
        "commands": commands,
        "evidence_checks": evidence_checks,
        "no_ship_boundaries": [
            (
                "This automated proxy validation is not a substitute for an "
                "independent human non-developer operator sign-off."
            ),
            (
                "Hat B desktop release remains blocked until signing/notarization/"
                "signed-RC/clean-machine gates pass."
            ),
        ],
    }
    _write_json(output_root / "operator_validation_report.json", report)
    _write_markdown_report(output_root / "OPERATOR_VALIDATION_REPORT.md", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run operator-facing validation drill.")
    parser.add_argument(
        "--output-root",
        default="artifacts/readiness/2026-05-13/operator_validation_drill",
    )
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--operator-attestation",
        default=None,
        help="Optional JSON attestation from a non-developer operator.",
    )
    args = parser.parse_args()

    report = run_validation(
        output_root=Path(args.output_root),
        root=Path(args.root).resolve(),
        operator_attestation_path=(
            Path(args.operator_attestation).resolve() if args.operator_attestation else None
        ),
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
