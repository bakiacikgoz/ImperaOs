from __future__ import annotations

import json
from pathlib import Path

from imperaos.computer_use.models import ComputerUseMode, RiskClass
from imperaos.computer_use.vision_runtime.models import (
    ExecutionResult,
    InputActionType,
    VerificationResult,
    VisionAction,
    VisionObservation,
    VisionPolicyDecision,
    VisionRunRequest,
    VisionStepResult,
)
from imperaos.computer_use.vision_runtime.recorder import RedactedVisionAuditRecorder
from imperaos.computer_use.vision_runtime.replay import load_replay_summary, verify_replay
from imperaos.computer_use.vision_runtime.runtime import VisionComputerUseRuntime
from imperaos.computer_use.vision_runtime.runtime_gate import (
    ComputerUseOperationIntent,
    RuntimePreflightContext,
)
from imperaos.runtime.config import ComputerUseRuntimeConfig


def _step(step_index: int) -> VisionStepResult:
    return VisionStepResult(
        step_index=step_index,
        before_hash="e" * 64,
        action=VisionAction(
            action_id=f"act-{step_index}",
            action_type=InputActionType.WAIT,
            rationale="Wait for stable UI.",
            expected_effect="UI remains stable.",
            risk_class=RiskClass.LOW,
            requires_approval=False,
            confidence=0.9,
        ),
        policy_decision=VisionPolicyDecision(
            allowed=True,
            requires_approval=False,
            denied=False,
            reason_code="POLICY_ALLOW",
            risk_reasons=[],
            policy_hash="policy",
        ),
        execution_status="executed",
        after_hash="f" * 64,
    )


class _NeverCapture:
    def capture(self) -> VisionObservation:
        raise AssertionError("capture must not run for preflight-blocked replay fixture")


class _NeverPlanner:
    def next_action(self, **_kwargs: object) -> VisionAction:
        raise AssertionError("planner must not run for preflight-blocked replay fixture")


class _NeverExecutor:
    def execute(self, _action: VisionAction) -> ExecutionResult:
        raise AssertionError("executor must not run for preflight-blocked replay fixture")


class _NeverVerifier:
    def verify(self, **_kwargs: object) -> VerificationResult:
        raise AssertionError("verifier must not run for preflight-blocked replay fixture")


def _blocked_preflight_context() -> RuntimePreflightContext:
    return RuntimePreflightContext(
        profile="balanced",
        platform="windows",
        operation_intent=ComputerUseOperationIntent.NORMAL_RUNTIME_LIVE,
        config=ComputerUseRuntimeConfig(runtime_mode="vision_first", vision_enabled=True),
        current_commit="fixture-commit",
    )


def test_recorder_writes_redacted_hash_chain_and_replay_summary(tmp_path: Path) -> None:
    recorder = RedactedVisionAuditRecorder(
        job_id="job-replay",
        job_dir=tmp_path / "job-replay",
        runtime_config_hash="runtime-hash",
        policy_hash="policy-hash",
    )

    recorder.record_step(_step(0))
    envelope = recorder.finalize("completed")
    (tmp_path / "job-replay" / "vision_runtime_summary.json").write_text(
        json.dumps(
            {
                "artifact_version": "computer_use_vision_runtime_summary/v1",
                "job_id": "job-replay",
                "status": "completed",
                "candidate_actions_seen": 1,
                "candidate_actions_rejected": 0,
                "candidate_reject_reasons": {},
                "actions_executed": 1,
                "approval_blocks": 0,
                "approval_resumes": 0,
                "semantic_verification": {
                    "satisfied": 0,
                    "inconclusive": 0,
                    "failed": 0,
                    "skipped": 0,
                },
                "no_progress_stops": 0,
                "raw_screenshot_persisted": 0,
                "stop_reason": "completed",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    events_path = tmp_path / "job-replay" / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]

    assert envelope["integrity"]["hash_chain_verified"] is True
    assert events[0]["prev_hash"] == ""
    assert events[0]["hash"]
    assert "raw_screenshot_path" not in json.dumps(events)

    replay = load_replay_summary(tmp_path / "job-replay")

    assert replay["job_id"] == "job-replay"
    assert replay["status"] == "completed"
    assert replay["event_count"] == 1
    assert replay["redacted"] is True
    assert replay["checks"]["hash_chain_verified"] is True
    assert replay["safety_summary"]["actions_executed"] == 1
    assert replay["safety_summary"]["raw_screenshot_persisted"] == 0


def test_replay_verifier_accepts_preflight_blocked_safe_stop(tmp_path: Path) -> None:
    runtime = VisionComputerUseRuntime(
        config=ComputerUseRuntimeConfig(runtime_mode="vision_first", vision_enabled=True),
        artifact_root=tmp_path,
        capture=_NeverCapture(),
        vision=None,
        planner=_NeverPlanner(),
        executor=_NeverExecutor(),
        verifier=_NeverVerifier(),
        runtime_preflight_context=_blocked_preflight_context(),
    )

    artifact = runtime.run(
        VisionRunRequest(
            job_id="job-preflight-replay",
            objective="Click export",
            mode=ComputerUseMode.EXECUTE,
        )
    )

    job_dir = tmp_path / "job-preflight-replay"
    events = [
        json.loads(line)
        for line in (job_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    verification = verify_replay(job_dir)
    replay = load_replay_summary(job_dir)
    encoded = json.dumps(replay, sort_keys=True)

    assert artifact.status == "blocked"
    assert [event["event_type"] for event in events] == [
        "runtime_start",
        "preflight_blocked",
        "runtime_stop",
    ]
    assert verification["verified"] is True
    assert verification["checks"]["preflight_blocked_safe_stop"] is True
    assert replay["verified"] is True
    assert replay["safety_summary"]["runtimePreflight"]["approvalConsumed"] is False
    assert "rawScreenshotPath" not in encoded
    assert "C:/Users" not in encoded
    assert "approvalSnapshotBody" not in encoded


def test_replay_verifier_detects_tampered_event_hash(tmp_path: Path) -> None:
    recorder = RedactedVisionAuditRecorder(
        job_id="job-tamper",
        job_dir=tmp_path / "job-tamper",
        runtime_config_hash="runtime-hash",
        policy_hash="policy-hash",
    )
    recorder.record_step(_step(0))
    recorder.finalize("completed")

    events_path = tmp_path / "job-tamper" / "events.jsonl"
    event = json.loads(events_path.read_text(encoding="utf-8").splitlines()[0])
    event["payload"]["execution_status"] = "executed_after_tamper"
    events_path.write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")

    verification = verify_replay(tmp_path / "job-tamper")

    assert verification["verified"] is False
    assert "hash_chain" in verification["errors"][0]
