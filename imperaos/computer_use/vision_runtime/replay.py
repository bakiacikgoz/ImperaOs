from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_replay_summary(job_dir: Path) -> dict[str, Any]:
    envelope_path = job_dir / "audit_envelope.json"
    events_path = job_dir / "events.jsonl"
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    verification = verify_replay(job_dir)
    safety_summary_path = job_dir / "vision_runtime_summary.json"
    safety_summary = (
        json.loads(safety_summary_path.read_text(encoding="utf-8"))
        if safety_summary_path.exists()
        else None
    )
    return {
        "artifact_version": "computer_use_vision_replay/v1",
        "job_id": envelope["job_id"],
        "status": envelope["status"],
        "event_count": len(events),
        "event_types": [event.get("event_type") for event in events],
        "redacted": envelope.get("redaction_report", {}).get("redacted") is True,
        "hash_chain_verified": envelope.get("integrity", {}).get("hash_chain_verified") is True,
        "steps": [
            {
                "step_index": event.get("step_index"),
                "event_type": event.get("event_type"),
                "action_type": event.get("payload", {}).get("action", {}).get("action_type"),
                "execution_status": event.get("payload", {}).get("execution_status"),
                "before_hash": event.get("payload", {}).get("before_hash"),
                "after_hash": event.get("payload", {}).get("after_hash"),
            }
            for event in events
            if event.get("event_type") == "checkpoint"
        ],
        "verified": verification["verified"],
        "checks": verification["checks"],
        "errors": verification["errors"],
        "safety_summary": safety_summary,
    }


def verify_replay(job_dir: Path) -> dict[str, Any]:
    events_path = job_dir / "events.jsonl"
    envelope_path = job_dir / "audit_envelope.json"
    errors: list[str] = []
    checks = {
        "hash_chain_verified": False,
        "step_index_monotonic": False,
        "approval_required_not_executed": False,
        "screenshot_hash_format": False,
        "raw_screenshot_policy": False,
        "preflight_blocked_safe_stop": True,
    }
    events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    previous = ""
    hash_ok = True
    for event in events:
        expected = _event_hash({key: value for key, value in event.items() if key != "hash"})
        if event.get("prev_hash") != previous or event.get("hash") != expected:
            hash_ok = False
            errors.append("hash_chain verification failed")
            break
        previous = str(event.get("hash") or "")
    checks["hash_chain_verified"] = hash_ok

    checkpoint_events = [event for event in events if event.get("event_type") == "checkpoint"]
    indices = [int(event.get("step_index", -1)) for event in checkpoint_events]
    checks["step_index_monotonic"] = indices == sorted(indices) and all(
        index >= 0 for index in indices
    )
    if not checkpoint_events:
        checks["step_index_monotonic"] = True
    if not checks["step_index_monotonic"]:
        errors.append("step_index monotonicity failed")

    approval_ok = True
    hash_format_ok = True
    for event in checkpoint_events:
        payload = event.get("payload", {})
        if (
            payload.get("execution_status") == "executed"
            and payload.get("policy_decision", {}).get("requires_approval") is True
        ):
            approval_ok = False
        for key in ("before_hash", "after_hash"):
            value = payload.get(key)
            if value is None:
                continue
            if not (isinstance(value, str) and len(value) == 64 and _is_hex(value)):
                hash_format_ok = False
    checks["approval_required_not_executed"] = approval_ok
    checks["screenshot_hash_format"] = hash_format_ok
    if not approval_ok:
        errors.append("approval-required action executed without replay-safe boundary")
    if not hash_format_ok:
        errors.append("screenshot hash format invalid")

    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    raw_count = envelope.get("redaction_report", {}).get("raw_screenshot_persisted_count", 0)
    checks["raw_screenshot_policy"] = raw_count == 0
    if raw_count != 0:
        errors.append("raw screenshot persistence violates default replay policy")

    if envelope.get("status") == "blocked":
        checks["preflight_blocked_safe_stop"] = _is_preflight_blocked_safe_stop(
            job_dir=job_dir,
            events=events,
        )
        if not checks["preflight_blocked_safe_stop"]:
            errors.append("preflight-blocked runtime did not stop at a safe replay boundary")

    return {
        "artifact_version": "computer_use_vision_replay_verification/v1",
        "verified": all(checks.values()),
        "checks": checks,
        "errors": errors,
    }


def verify_qualification_report_replay(report_path: Path) -> dict[str, Any]:
    report_path = Path(report_path)
    errors: list[str] = []
    checks = {
        "event_log_present": False,
        "hash_chain_verified": False,
        "step_index_monotonic": False,
        "audit_log_present": False,
        "audit_hash_chain_verified": False,
        "raw_screenshot_policy": False,
        "sensitive_surface_no_input": False,
        "terminal_no_execution": False,
    }
    if not report_path.exists():
        errors.append("qualification report missing")
        return {
            "artifact_version": "computer_use_qualification_replay_verification/v1",
            "reportPath": str(report_path),
            "verified": False,
            "qualificationStatus": "missing",
            "qualificationPassed": False,
            "replayIntegrityStatus": "failed",
            "replayIntegrityVerified": False,
            "auditHashChainVerified": False,
            "checks": checks,
            "errors": errors,
        }

    report = json.loads(report_path.read_text(encoding="utf-8"))
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    event_log_path = _resolve_artifact_path(report_path, artifacts.get("eventLogPath"))
    events: list[dict[str, Any]] = []
    last_hash = ""
    if event_log_path is None or not event_log_path.exists():
        errors.append("qualification event log missing")
    else:
        checks["event_log_present"] = True
        events = [
            json.loads(line)
            for line in event_log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        previous = ""
        hash_ok = True
        for event in events:
            expected = _event_hash({key: value for key, value in event.items() if key != "hash"})
            if event.get("prev_hash") != previous or event.get("hash") != expected:
                hash_ok = False
                break
            previous = str(event.get("hash") or "")
        last_hash = previous
        checks["hash_chain_verified"] = hash_ok and bool(events)
        if not checks["hash_chain_verified"]:
            errors.append("qualification hash_chain verification failed")
        indices = [int(event.get("step_index", -1)) for event in events]
        checks["step_index_monotonic"] = indices == sorted(indices) and all(
            index >= 0 for index in indices
        )
        if not checks["step_index_monotonic"]:
            errors.append("qualification event order verification failed")

    audit_path = _resolve_artifact_path(report_path, artifacts.get("auditPath"))
    if audit_path is None or not audit_path.exists():
        errors.append("qualification audit log missing")
    else:
        checks["audit_log_present"] = True
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        checks["audit_hash_chain_verified"] = (
            audit.get("event_count") == len(events)
            and audit.get("last_hash") == last_hash
            and audit.get("redacted") is True
        )
        if not checks["audit_hash_chain_verified"]:
            errors.append("qualification audit hash-chain verification failed")

    safety = report.get("safety") if isinstance(report.get("safety"), dict) else {}
    raw_count = safety.get(
        "rawScreenshotPersistedCount",
        safety.get(
            "rawScreenshotsPersisted",
            artifacts.get("rawScreenshotCount", -1),
        ),
    )
    try:
        checks["raw_screenshot_policy"] = (
            int(raw_count) == 0
            and artifacts.get("screenshotHashesOnly", True) is True
            and safety.get("rawScreenshotRetention") in {None, "disabled"}
        )
    except (TypeError, ValueError):
        checks["raw_screenshot_policy"] = False
    if not checks["raw_screenshot_policy"]:
        errors.append("raw screenshot persistence violates qualification policy")

    fixtures = report.get("fixtures") if isinstance(report.get("fixtures"), list) else []
    sensitive_fixtures = [
        fixture
        for fixture in fixtures
        if isinstance(fixture, dict) and fixture.get("id") == "sensitive_surface_stop"
    ]
    terminal_fixtures = [
        fixture
        for fixture in fixtures
        if isinstance(fixture, dict) and fixture.get("id") == "terminal_deny"
    ]
    checks["sensitive_surface_no_input"] = bool(sensitive_fixtures) and all(
        fixture.get("inputExecuted") is not True
        and fixture.get("osInputExecuted") is not True
        and int(fixture.get("stepsSucceeded", 0) or 0) == 0
        for fixture in sensitive_fixtures
    )
    checks["terminal_no_execution"] = bool(terminal_fixtures) and all(
        fixture.get("commandExecuted") is not True
        and fixture.get("terminalExecuted") is not True
        and int(fixture.get("stepsSucceeded", 0) or 0) == 0
        for fixture in terminal_fixtures
    )
    if not checks["sensitive_surface_no_input"]:
        errors.append("sensitive surface fixture allowed input")
    if not checks["terminal_no_execution"]:
        errors.append("terminal fixture allowed execution")

    qualification_status = str(
        report.get("qualificationStatus")
        or _qualification_status_from_report_status(report.get("status"))
    )
    qualification_passed = bool(
        report.get("qualificationPassed", qualification_status == "passed")
    )
    integrity_verified = all(checks.values())

    return {
        "artifact_version": "computer_use_qualification_replay_verification/v1",
        "reportPath": str(report_path),
        "status": report.get("status"),
        "stage": report.get("stage"),
        "qualificationStatus": qualification_status,
        "qualificationPassed": qualification_passed,
        "replayIntegrityStatus": "passed" if integrity_verified else "failed",
        "replayIntegrityVerified": integrity_verified,
        "auditHashChainVerified": checks["audit_hash_chain_verified"],
        "verified": integrity_verified,
        "checks": checks,
        "errors": errors,
    }


def _event_hash(event: dict[str, Any]) -> str:
    import hashlib

    payload = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_hex(value: str) -> bool:
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _is_preflight_blocked_safe_stop(
    *,
    job_dir: Path,
    events: list[dict[str, Any]],
) -> bool:
    event_types = [event.get("event_type") for event in events]
    if event_types != ["runtime_start", "preflight_blocked", "runtime_stop"]:
        return False
    summary_path = job_dir / "vision_runtime_summary.json"
    if not summary_path.exists():
        return False
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    runtime_preflight = summary.get("runtimePreflight")
    if not isinstance(runtime_preflight, dict):
        return False
    return (
        summary.get("status") == "blocked"
        and runtime_preflight.get("status") == "blocked"
        and runtime_preflight.get("publicLiveClaimAllowed") is False
        and runtime_preflight.get("liveExecutionAttempted") is False
        and runtime_preflight.get("captureAttempted") is False
        and runtime_preflight.get("providerAttempted") is False
        and runtime_preflight.get("executorAttempted") is False
        and runtime_preflight.get("approvalCreated") is False
        and runtime_preflight.get("approvalConsumed") is False
    )


def _resolve_artifact_path(report_path: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    cwd_candidate = Path.cwd() / path
    if cwd_candidate.exists():
        return cwd_candidate
    return report_path.parent / path


def _qualification_status_from_report_status(value: object) -> str:
    if value == "pass":
        return "passed"
    if value == "fail":
        return "failed"
    if value == "skipped":
        return "skipped"
    return "blocked"
