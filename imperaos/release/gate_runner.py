from __future__ import annotations

import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from imperaos.release.gate_artifacts import collect_gate_artifacts
from imperaos.release.gate_ledger import build_gate_evidence_ledger, write_gate_evidence_ledger
from imperaos.release.gate_models import (
    GateCommandExecution,
    GateCommandSpec,
    GateEvidenceLedger,
    GateRunResult,
    ReleaseGatePlan,
    ReleaseGateSpec,
)

SAFE_ENV_KEYS = {
    "CI",
    "PYTHONPATH",
    "FALLOW_TELEMETRY_DISABLED",
    "DO_NOT_TRACK",
    "PATH",
    "SYSTEMROOT",
}
UNSAFE_PATTERNS = {
    ("git", "push"),
    ("git", "merge"),
    ("git", "tag"),
    ("gh", "release"),
    ("rm", "-rf"),
}


def run_release_gate_plan(
    *,
    plan: ReleaseGatePlan,
    repo_root: Path,
    output_root: Path,
) -> GateEvidenceLedger:
    results = [
        run_release_gate(gate=gate, repo_root=repo_root, output_root=output_root)
        for gate in plan.gates
    ]
    ledger = build_gate_evidence_ledger(
        plan=plan,
        gate_results=results,
        repo_root=repo_root,
        output_root=output_root,
    )
    write_gate_evidence_ledger(ledger=ledger, repo_root=repo_root)
    return ledger


def run_release_gate(
    *,
    gate: ReleaseGateSpec,
    repo_root: Path,
    output_root: Path,
) -> GateRunResult:
    _ = output_root
    started = datetime.now(UTC)
    start_monotonic = time.monotonic()
    executions: list[GateCommandExecution] = []
    blockers: list[str] = []
    warnings: list[str] = []
    exit_code: int | None = None
    for spec in gate.commands:
        if _is_unsafe(spec):
            blockers.append("UNSAFE_GATE_COMMAND")
            executions.append(
                GateCommandExecution(
                    commandId=spec.command_id,
                    status="blocked",
                    blockingReasons=["UNSAFE_GATE_COMMAND"],
                )
            )
            break
        execution = _run_command(spec=spec, repo_root=repo_root)
        executions.append(execution)
        exit_code = execution.exit_code
        blockers.extend(execution.blocking_reasons)
        if execution.status != "pass":
            blockers.append("GATE_COMMAND_FAILED")
            break
    artifact_refs, missing, secret_findings, raw_findings = collect_gate_artifacts(
        requirements=gate.artifact_requirements,
        repo_root=repo_root,
    )
    blockers.extend(secret_findings)
    blockers.extend(raw_findings)
    if missing:
        warnings.extend(f"MISSING_REQUIRED_ARTIFACT:{item}" for item in missing)
    if blockers:
        status = "blocked"
    elif missing:
        status = "conditional"
    else:
        status = "pass"
    finished = datetime.now(UTC)
    return GateRunResult(
        gateId=gate.gate_id,
        status=status,
        startedAtUtc=started,
        finishedAtUtc=finished,
        durationMs=max(0, int((time.monotonic() - start_monotonic) * 1000)),
        exitCode=exit_code,
        commands=executions,
        artifactRefs=artifact_refs,
        missingArtifactRequirements=missing,
        blockingReasons=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        secretScanStatus="fail" if secret_findings else "pass",
        rawMarkerScanStatus="fail" if raw_findings else "pass",
    )


def _run_command(*, spec: GateCommandSpec, repo_root: Path) -> GateCommandExecution:
    started = time.monotonic()
    env = {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ}
    env.update(spec.env)
    cwd = repo_root / spec.cwd
    try:
        completed = subprocess.run(
            spec.argv,
            cwd=cwd,
            env=env,
            shell=False,
            text=True,
            capture_output=True,
            timeout=spec.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return GateCommandExecution(
            commandId=spec.command_id,
            status="timeout",
            exitCode=None,
            durationMs=int((time.monotonic() - started) * 1000),
            redactedStdoutTail=_tail(exc.stdout or ""),
            redactedStderrTail=_tail(exc.stderr or ""),
            blockingReasons=["GATE_COMMAND_TIMEOUT"],
        )
    except OSError:
        return GateCommandExecution(
            commandId=spec.command_id,
            status="fail",
            durationMs=int((time.monotonic() - started) * 1000),
            blockingReasons=["GATE_COMMAND_NOT_FOUND"],
        )
    ok = completed.returncode in spec.expected_exit_codes
    return GateCommandExecution(
        commandId=spec.command_id,
        status="pass" if ok else "fail",
        exitCode=completed.returncode,
        durationMs=int((time.monotonic() - started) * 1000),
        redactedStdoutTail=_tail(completed.stdout),
        redactedStderrTail=_tail(completed.stderr),
        blockingReasons=[] if ok else ["GATE_COMMAND_NONZERO_EXIT"],
    )


def _is_unsafe(spec: GateCommandSpec) -> bool:
    argv = [item.lower() for item in spec.argv]
    if spec.mutates_worktree or spec.destructive:
        return True
    if len(argv) >= 2 and (argv[0], argv[1]) in UNSAFE_PATTERNS:
        return True
    joined = " ".join(argv)
    return any(token in joined for token in ["migrate apply", "deploy", "remove-item -recurse"])


def _tail(text: str, limit: int = 1000) -> str:
    redacted = text.replace(os.path.expanduser("~"), "<USER_HOME>")
    return redacted[-limit:]
