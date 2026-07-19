from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from imperaos.control_plane.storage import canonical_json_hash
from imperaos.memory.models import StrictModel

PilotOpsDrillStatus = Literal["pass", "conditional", "blocked"]
PilotOpsStepStatus = Literal["pass", "conditional", "blocked", "skipped"]
CommandRunner = Callable[[list[str], int], tuple[int, str, str]]


class PilotOpsDrillStep(StrictModel):
    step_id: str = Field(alias="stepId")
    command: str
    status: PilotOpsStepStatus
    exit_code: int | None = Field(default=None, alias="exitCode")
    started_at_utc: datetime = Field(alias="startedAtUtc")
    finished_at_utc: datetime = Field(alias="finishedAtUtc")
    duration_ms: int = Field(alias="durationMs")
    output_hash: str | None = Field(default=None, alias="outputHash")
    artifact_path: str | None = Field(default=None, alias="artifactPath")
    reason_codes: list[str] = Field(default_factory=list, alias="reasonCodes")


class PilotOpsDrillMetrics(StrictModel):
    step_count: int = Field(default=0, alias="stepCount")
    passed_count: int = Field(default=0, alias="passedCount")
    conditional_count: int = Field(default=0, alias="conditionalCount")
    blocked_count: int = Field(default=0, alias="blockedCount")
    skipped_count: int = Field(default=0, alias="skippedCount")


class PilotOpsDrillReport(StrictModel):
    schema_version: Literal["control-plane.pilot-ops-drill/v1"] = Field(
        default="control-plane.pilot-ops-drill/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: PilotOpsDrillStatus
    mode: Literal["deterministic", "target_environment"] = "deterministic"
    profile: str
    steps: list[PilotOpsDrillStep] = Field(default_factory=list)
    metrics: PilotOpsDrillMetrics = Field(default_factory=PilotOpsDrillMetrics)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifact_root: str = Field(alias="artifactRoot")


SAFE_DRILL_STEPS = (
    ("config-resolve", ["imperaos", "config", "resolve"]),
    ("control-plane-doctor", ["imperaos", "control-plane", "doctor"]),
    ("security-baseline", ["imperaos", "security", "baseline"]),
    ("identity-whoami", ["imperaos", "auth", "whoami"]),
    ("metrics-snapshot", ["imperaos", "metrics", "snapshot"]),
    ("control-plane-snapshot", ["imperaos", "control-plane", "snapshot"]),
    ("claim-guard-verify", ["imperaos", "control-plane", "claims", "verify"]),
    (
        "governed-pilot-workflow-verify",
        [
            "imperaos",
            "pilot",
            "workflow",
            "verify",
            "--report",
            "artifacts/governed-pilot-workflow/latest/report.json",
            "--no-strict",
        ],
    ),
    ("field-evidence-verify", ["imperaos", "pilot", "field", "verify"]),
    (
        "evidence-pack-verify",
        [
            "imperaos",
            "control-plane",
            "evidence",
            "verify",
            "--path",
            "artifacts/evidence-pack/manifest.json",
        ],
    ),
    ("support-bundle-export", ["imperaos", "support", "bundle", "export"]),
    (
        "handoff-pack-build-verify",
        [
            "imperaos",
            "release",
            "handoff",
            "verify",
            "--manifest",
            "artifacts/design-partner-handoff/manifest.json",
        ],
    ),
)


def run_pilot_ops_drill(
    *,
    profile: str,
    output_root: Path,
    mode: Literal["deterministic", "target_environment"] = "deterministic",
    command_runner: CommandRunner | None = None,
    timeout_seconds: int = 60,
    now: datetime | None = None,
) -> PilotOpsDrillReport:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    runner = command_runner or _deterministic_runner(output_root)
    steps = [
        _run_step(
            step_id=step_id,
            command=[*command, "--profile", profile],
            runner=runner,
            timeout=timeout_seconds,
        )
        for step_id, command in SAFE_DRILL_STEPS
    ]
    blockers = sorted(
        {code for step in steps for code in step.reason_codes if step.status == "blocked"}
    )
    warnings = sorted(
        {code for step in steps for code in step.reason_codes if step.status == "conditional"}
    )
    metrics = PilotOpsDrillMetrics(
        stepCount=len(steps),
        passedCount=sum(1 for step in steps if step.status == "pass"),
        conditionalCount=sum(1 for step in steps if step.status == "conditional"),
        blockedCount=sum(1 for step in steps if step.status == "blocked"),
        skippedCount=sum(1 for step in steps if step.status == "skipped"),
    )
    status: PilotOpsDrillStatus = "blocked" if blockers else "conditional" if warnings else "pass"
    report = PilotOpsDrillReport(
        generatedAtUtc=now or datetime.now(UTC),
        status=status,
        mode=mode,
        profile=profile,
        steps=steps,
        metrics=metrics,
        blockers=blockers,
        warnings=warnings,
        artifactRoot=str(output_root),
    )
    _write_json(
        output_root / "PILOT_OPS_DRILL_REPORT.json", report.model_dump(mode="json", by_alias=True)
    )
    return report


def load_pilot_ops_drill_report(path: Path) -> PilotOpsDrillReport:
    return PilotOpsDrillReport.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _run_step(
    *,
    step_id: str,
    command: list[str],
    runner: CommandRunner,
    timeout: int,
) -> PilotOpsDrillStep:
    started = datetime.now(UTC)
    tick = time.perf_counter()
    try:
        exit_code, stdout, stderr = runner(command, timeout)
    except TimeoutError:
        finished = datetime.now(UTC)
        return PilotOpsDrillStep(
            stepId=step_id,
            command=" ".join(command),
            status="blocked",
            exitCode=None,
            startedAtUtc=started,
            finishedAtUtc=finished,
            durationMs=int((time.perf_counter() - tick) * 1000),
            outputHash=None,
            reasonCodes=[f"DRILL_STEP_TIMEOUT:{step_id}"],
        )
    finished = datetime.now(UTC)
    status: PilotOpsStepStatus = "pass"
    reason_codes: list[str] = []
    if exit_code in {2, 3}:
        status = "conditional"
        reason_codes.append(f"DRILL_STEP_CONDITIONAL:{step_id}")
    elif exit_code != 0:
        status = "blocked"
        reason_codes.append(f"DRILL_STEP_BLOCKED:{step_id}")
    output_hash = canonical_json_hash(
        {
            "stdoutHash": canonical_json_hash({"stdout": _redacted_text(stdout)}),
            "stderrHash": canonical_json_hash({"stderr": _redacted_text(stderr)}),
            "exitCode": exit_code,
        }
    )
    return PilotOpsDrillStep(
        stepId=step_id,
        command=" ".join(command),
        status=status,
        exitCode=exit_code,
        startedAtUtc=started,
        finishedAtUtc=finished,
        durationMs=int((time.perf_counter() - tick) * 1000),
        outputHash=output_hash,
        reasonCodes=reason_codes,
    )


def _deterministic_runner(output_root: Path) -> CommandRunner:
    def _run(command: list[str], timeout: int) -> tuple[int, str, str]:
        _ = timeout
        joined = " ".join(command)
        conditional_steps = {
            "imperaos auth whoami",
            "imperaos pilot field verify",
        }
        if any(joined.startswith(step) for step in conditional_steps):
            return 3, f"{joined}: conditional in deterministic drill", ""
        return 0, f"{joined}: deterministic pass under {output_root}", ""

    return _run


def subprocess_runner(command: list[str], timeout: int) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError from exc
    return result.returncode, result.stdout, result.stderr


def _redacted_text(value: str) -> str:
    text = value[:2000]
    for marker in ("sk-", "token=", "password=", "private_key", "BEGIN RAW"):
        text = text.replace(marker, "***REDACTED***")
    return text


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
