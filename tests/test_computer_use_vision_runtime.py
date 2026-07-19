from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import imperaos.computer_use.runtime as computer_use_runtime
import imperaos.computer_use.vision_runtime.runtime as vision_runtime_module
from imperaos.computer_use.models import ComputerUseMode, RiskClass
from imperaos.computer_use.vision_runtime.models import (
    ExecutionResult,
    InputActionType,
    NormalizedBBox,
    StopDecision,
    SurfaceKind,
    VerificationResult,
    VisionAction,
    VisionInterpretation,
    VisionObservation,
    VisionRunRequest,
    VisionVerificationStatus,
)
from imperaos.computer_use.vision_runtime.providers.mock_vision import (
    DeterministicActionPlanner,
    DeterministicScreenCapture,
    DeterministicStepVerifier,
)
from imperaos.computer_use.vision_runtime.runtime import VisionComputerUseRuntime
from imperaos.computer_use.vision_runtime.runtime_gate import (
    ComputerUseOperationIntent,
    RuntimePreflightContext,
)
from imperaos.runtime.config import ComputerUseRuntimeConfig, RuntimeConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "contracts" / "computer_use" / "fixtures"


def _observation(hash_char: str = "c") -> VisionObservation:
    return VisionObservation(
        screenshot_hash=hash_char * 64,
        captured_at="2026-05-05T00:00:00+00:00",
        platform="macos",
        active_app="Safari",
        surface_kind=SurfaceKind.BROWSER,
        confidence=0.92,
    )


def _action(
    *,
    action_id: str = "act-1",
    action_type: InputActionType = InputActionType.WAIT,
    risk_class: RiskClass = RiskClass.LOW,
    requires_approval: bool = False,
) -> VisionAction:
    return VisionAction(
        action_id=action_id,
        action_type=action_type,
        target_bbox=NormalizedBBox(x=0.1, y=0.1, w=0.2, h=0.2),
        rationale="Advance deterministic test.",
        expected_effect="State changes.",
        risk_class=risk_class,
        requires_approval=requires_approval,
        confidence=0.9,
    )


@dataclass
class _Interpreter:
    def interpret(self, *, objective, observation, world):  # noqa: ANN001
        return VisionInterpretation(
            observation_hash=observation.screenshot_hash,
            summary=f"Objective: {objective}",
            candidate_actions=[_action()],
            confidence=0.91,
        )


class _Executor:
    def __init__(self) -> None:
        self.executed: list[VisionAction] = []

    def execute(self, action: VisionAction) -> ExecutionResult:
        self.executed.append(action)
        return ExecutionResult(status="executed", message="ok")


class _CountingCapture:
    def __init__(self) -> None:
        self.calls = 0

    def capture(self) -> VisionObservation:
        self.calls += 1
        return _observation()


class _CountingInterpreter:
    def __init__(self) -> None:
        self.calls = 0

    def interpret(self, *, objective, observation, world):  # noqa: ANN001
        self.calls += 1
        return _Interpreter().interpret(
            objective=objective,
            observation=observation,
            world=world,
        )


class _CountingPlanner:
    def __init__(self, action: VisionAction | None = None) -> None:
        self.calls = 0
        self.action = action or _action()

    def next_action(self, *, objective, interpretation, world):  # noqa: ANN001
        del objective, interpretation, world
        self.calls += 1
        return self.action


class _MacOSPlatform:
    label = "macos"
    system = "Darwin"
    machine = "arm64"
    release = "test"


class _WindowsPlatform:
    label = "windows"
    system = "Windows"
    machine = "AMD64"
    release = "test"


def _blocked_preflight_context() -> RuntimePreflightContext:
    return RuntimePreflightContext(
        profile="balanced",
        platform="windows",
        operation_intent=ComputerUseOperationIntent.NORMAL_RUNTIME_LIVE,
        config=ComputerUseRuntimeConfig(runtime_mode="vision_first", vision_enabled=True),
        current_commit="fixture-commit",
    )


def _assert_blocked_runtime_preflight_payload(runtime_preflight: dict[str, object]) -> None:
    assert runtime_preflight["status"] == "blocked"
    assert runtime_preflight["reasonCode"] == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    assert "COMPUTER_USE_EVIDENCE_MISSING" in runtime_preflight["blockers"]
    assert runtime_preflight["operationIntent"] == "normal_runtime_live"
    assert runtime_preflight["publicLiveClaimAllowed"] is False
    assert runtime_preflight["liveExecutionAttempted"] is False
    assert runtime_preflight["captureAttempted"] is False
    assert runtime_preflight["providerAttempted"] is False
    assert runtime_preflight["executorAttempted"] is False
    assert runtime_preflight["approvalCreated"] is False
    assert runtime_preflight["approvalConsumed"] is False
    assert runtime_preflight["capabilityStatus"] == "blocked"
    assert runtime_preflight["evidenceStatus"] == "missing"


def test_runtime_preflight_block_stops_before_capture_provider_planner_and_executor(
    tmp_path,
    monkeypatch,
) -> None:
    class UnexpectedPolicy:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("policy must not be constructed when preflight blocks")

    capture = _CountingCapture()
    vision = _CountingInterpreter()
    planner = _CountingPlanner()
    executor = _Executor()
    monkeypatch.setattr(
        vision_runtime_module,
        "UniversalComputerUsePolicy",
        UnexpectedPolicy,
    )
    runtime = VisionComputerUseRuntime(
        config=ComputerUseRuntimeConfig(runtime_mode="vision_first", vision_enabled=True),
        artifact_root=tmp_path,
        capture=capture,
        vision=vision,
        planner=planner,
        executor=executor,
        verifier=DeterministicStepVerifier([VerificationResult(verified=True, confidence=0.9)]),
        runtime_preflight_context=_blocked_preflight_context(),
    )

    artifact = runtime.run(
        VisionRunRequest(
            job_id="job-preflight-blocked",
            objective="Click export",
            mode=ComputerUseMode.EXECUTE,
        )
    )

    assert artifact.status == "blocked"
    assert artifact.stop_reason == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    assert artifact.steps == []
    assert artifact.runtime_preflight is not None
    assert artifact.runtime_preflight["allowed"] is False
    _assert_blocked_runtime_preflight_payload(artifact.runtime_preflight)
    assert capture.calls == 0
    assert vision.calls == 0
    assert planner.calls == 0
    assert executor.executed == []
    summary = json.loads(
        (tmp_path / "job-preflight-blocked" / "vision_runtime_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["runtimePreflight"]["allowed"] is False
    _assert_blocked_runtime_preflight_payload(summary["runtimePreflight"])
    assert summary["approval_blocks"] == 0
    events_path = tmp_path / "job-preflight-blocked" / "events.jsonl"
    events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [event["event_type"] for event in events] == [
        "runtime_start",
        "preflight_blocked",
        "runtime_stop",
    ]


def test_runtime_preflight_block_does_not_create_approval_snapshot(tmp_path) -> None:
    capture = _CountingCapture()
    vision = _CountingInterpreter()
    planner = _CountingPlanner(
        _action(action_type=InputActionType.CLICK, risk_class=RiskClass.MEDIUM)
    )
    executor = _Executor()
    runtime = VisionComputerUseRuntime(
        config=ComputerUseRuntimeConfig(runtime_mode="vision_first", vision_enabled=True),
        artifact_root=tmp_path,
        capture=capture,
        vision=vision,
        planner=planner,
        executor=executor,
        verifier=DeterministicStepVerifier([]),
        runtime_preflight_context=_blocked_preflight_context(),
    )

    artifact = runtime.run(
        VisionRunRequest(
            job_id="job-preflight-approval-block",
            objective="Click export",
            mode=ComputerUseMode.STEP_APPROVAL,
        )
    )

    assert artifact.status == "blocked"
    assert artifact.steps == []
    assert capture.calls == 0
    assert planner.calls == 0
    assert executor.executed == []


def test_runtime_preflight_resolver_exception_blocks_without_leaking_details(tmp_path) -> None:
    def _raise_resolution_error(**_kwargs: object) -> dict[str, object]:
        raise RuntimeError("boom C:/Users/duzey/private/rawScreenshotPath.png")

    runtime = VisionComputerUseRuntime(
        config=ComputerUseRuntimeConfig(runtime_mode="vision_first", vision_enabled=True),
        artifact_root=tmp_path,
        capture=_CountingCapture(),
        vision=_CountingInterpreter(),
        planner=_CountingPlanner(),
        executor=_Executor(),
        verifier=DeterministicStepVerifier([]),
        runtime_preflight_context=_blocked_preflight_context(),
        runtime_preflight_resolver=_raise_resolution_error,
    )

    artifact = runtime.run(
        VisionRunRequest(
            job_id="job-preflight-resolver-error",
            objective="Click export",
            mode=ComputerUseMode.EXECUTE,
        )
    )

    encoded = json.dumps(artifact.model_dump(mode="json"), sort_keys=True)
    assert artifact.status == "blocked"
    assert artifact.stop_reason == "COMPUTER_USE_RUNTIME_RESOLUTION_FAILED"
    assert "COMPUTER_USE_RUNTIME_RESOLUTION_FAILED" in encoded
    assert "boom" not in encoded
    assert "C:/Users" not in encoded
    assert "rawScreenshotPath" not in encoded


def test_runner_live_preflight_blocks_before_provider_construction(
    tmp_path,
    monkeypatch,
) -> None:
    def _unexpected_constructor(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("provider/capture/executor must not be constructed when blocked")

    monkeypatch.setattr(computer_use_runtime, "current_platform", lambda: _WindowsPlatform())
    monkeypatch.setattr(
        computer_use_runtime,
        "MacOSScreenCaptureProvider",
        _unexpected_constructor,
    )
    monkeypatch.setattr(
        computer_use_runtime,
        "OllamaVisionInterpreter",
        _unexpected_constructor,
    )
    monkeypatch.setattr(
        computer_use_runtime,
        "MacOSInputExecutor",
        _unexpected_constructor,
    )
    monkeypatch.setattr(computer_use_runtime, "_current_git_sha", lambda: "fixture-commit")

    runner = computer_use_runtime.ComputerUseRunner(
        config=RuntimeConfig(
            computer_use=ComputerUseRuntimeConfig(
                runtime_mode="vision_first",
                vision_enabled=True,
                vision_provider="ollama",
                vision_model="llava",
                max_steps=1,
            )
        ),
        root_dir=tmp_path,
    )

    payload = runner.run(
        prompt="Click export",
        job_id="job-runner-preflight-blocked",
        mode=ComputerUseMode.EXECUTE,
        runtime_mode="vision_first",
    )

    runtime_preflight = payload["computer_use"]["runtimePreflight"]
    encoded = json.dumps(payload, sort_keys=True)
    assert payload["job"]["status"] == "blocked"
    assert payload["computer_use"]["status"] == "blocked"
    assert payload["computer_use"]["stop_reason"] == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    assert runtime_preflight["allowed"] is False
    _assert_blocked_runtime_preflight_payload(runtime_preflight)
    summary = json.loads(
        (tmp_path / "job-runner-preflight-blocked" / "vision_runtime_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["status"] == "blocked"
    assert summary["runtimePreflight"] == runtime_preflight
    events_path = tmp_path / "job-runner-preflight-blocked" / "events.jsonl"
    events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [event["event_type"] for event in events] == [
        "runtime_start",
        "preflight_blocked",
        "runtime_stop",
    ]
    assert "rawScreenshotPath" not in encoded
    assert "providerRawResponse" not in encoded
    assert "approvalSnapshotBody" not in encoded


def test_runtime_blocks_when_vision_provider_missing(tmp_path) -> None:
    runtime = VisionComputerUseRuntime(
        config=ComputerUseRuntimeConfig(runtime_mode="vision_first", vision_enabled=True),
        artifact_root=tmp_path,
        capture=DeterministicScreenCapture([_observation()]),
        vision=None,
        planner=DeterministicActionPlanner([_action()]),
        executor=_Executor(),
        verifier=DeterministicStepVerifier([VerificationResult(verified=True, confidence=0.9)]),
    )

    artifact = runtime.run(
        VisionRunRequest(
            job_id="job-vision-missing",
            objective="Read page",
            mode=ComputerUseMode.EXECUTE,
        )
    )

    assert artifact.status == "failed"
    assert artifact.stop_reason == "VISION_PROVIDER_UNAVAILABLE"
    assert artifact.redaction_report["raw_screenshot_persisted_count"] == 0


def test_runtime_completes_safe_mock_task_and_records_hash_chain(tmp_path) -> None:
    executor = _Executor()
    runtime = VisionComputerUseRuntime(
        config=ComputerUseRuntimeConfig(
            runtime_mode="vision_first",
            vision_enabled=True,
            max_steps=2,
        ),
        artifact_root=tmp_path,
        capture=DeterministicScreenCapture([_observation("c"), _observation("d")]),
        vision=_Interpreter(),
        planner=DeterministicActionPlanner([_action(), StopDecision(reason="done")]),
        executor=executor,
        verifier=DeterministicStepVerifier([VerificationResult(verified=True, confidence=0.9)]),
    )

    artifact = runtime.run(
        VisionRunRequest(job_id="job-complete", objective="Read page", mode=ComputerUseMode.EXECUTE)
    )

    assert artifact.status == "completed"
    assert len(artifact.steps) == 1
    assert executor.executed[0].action_type == InputActionType.WAIT
    assert artifact.integrity["hash_chain_verified"] is True
    summary = json.loads(
        (tmp_path / "job-complete" / "vision_runtime_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["actions_executed"] == 1
    assert summary["approval_blocks"] == 0
    assert summary["semantic_verification"]["skipped"] == 0
    assert summary["raw_screenshot_persisted"] == 0
    assert summary["stop_reason"] == "done"


def test_runtime_returns_awaiting_approval_without_executing(tmp_path) -> None:
    executor = _Executor()
    config = ComputerUseRuntimeConfig(
        runtime_mode="vision_first",
        vision_enabled=True,
        approval_snapshot_max_age_ms=12345,
    )
    runtime = VisionComputerUseRuntime(
        config=config,
        artifact_root=tmp_path,
        capture=DeterministicScreenCapture([_observation()]),
        vision=_Interpreter(),
        planner=DeterministicActionPlanner(
            [_action(action_type=InputActionType.CLICK, risk_class=RiskClass.MEDIUM)]
        ),
        executor=executor,
        verifier=DeterministicStepVerifier([]),
    )

    artifact = runtime.run(
        VisionRunRequest(
            job_id="job-approval",
            objective="Click export",
            mode=ComputerUseMode.STEP_APPROVAL,
        )
    )

    assert artifact.status == "awaiting_approval"
    assert artifact.steps[0].execution_status == "approval_required"
    assert artifact.steps[0].approval_snapshot is not None
    assert artifact.steps[0].approval_snapshot["max_age_ms"] == 12345
    assert executor.executed == []


def test_runtime_stops_after_verification_failure_budget(tmp_path) -> None:
    runtime = VisionComputerUseRuntime(
        config=ComputerUseRuntimeConfig(
            runtime_mode="vision_first",
            vision_enabled=True,
            max_recovery_attempts=0,
        ),
        artifact_root=tmp_path,
        capture=DeterministicScreenCapture([_observation("c"), _observation("d")]),
        vision=_Interpreter(),
        planner=DeterministicActionPlanner([_action()]),
        executor=_Executor(),
        verifier=DeterministicStepVerifier(
            [VerificationResult(verified=False, confidence=0.3, message="state mismatch")]
        ),
    )

    artifact = runtime.run(
        VisionRunRequest(
            job_id="job-verify-fail",
            objective="Read page",
            mode=ComputerUseMode.EXECUTE,
        )
    )

    assert artifact.status == "failed"
    assert artifact.stop_reason == "COMPUTER_USE_RECOVERY_BUDGET_EXCEEDED"
    assert artifact.steps[0].verification is not None
    assert artifact.steps[0].verification.verified is False


def test_runtime_stops_on_semantic_verification_inconclusive(tmp_path) -> None:
    runtime = VisionComputerUseRuntime(
        config=ComputerUseRuntimeConfig(
            runtime_mode="vision_first",
            vision_enabled=True,
            max_recovery_attempts=0,
        ),
        artifact_root=tmp_path,
        capture=DeterministicScreenCapture([_observation("c"), _observation("d")]),
        vision=_Interpreter(),
        planner=DeterministicActionPlanner([_action()]),
        executor=_Executor(),
        verifier=DeterministicStepVerifier(
            [
                VerificationResult(
                    verified=False,
                    confidence=0.4,
                    status=VisionVerificationStatus.INCONCLUSIVE,
                    reason_code="VISION_VERIFICATION_INCONCLUSIVE",
                    message="changed but expected effect was not observed",
                )
            ]
        ),
    )

    artifact = runtime.run(
        VisionRunRequest(
            job_id="job-verify-inconclusive",
            objective="Read page",
            mode=ComputerUseMode.EXECUTE,
        )
    )

    assert artifact.status == "failed"
    assert artifact.stop_reason == "VISION_VERIFICATION_INCONCLUSIVE"
    assert artifact.steps[0].verification is not None
    assert artifact.steps[0].verification.status == VisionVerificationStatus.INCONCLUSIVE


def test_runtime_rejects_repeated_action_digest_before_second_execution(tmp_path) -> None:
    executor = _Executor()
    action = _action(action_type=InputActionType.MOVE_MOUSE, risk_class=RiskClass.LOW)
    runtime = VisionComputerUseRuntime(
        config=ComputerUseRuntimeConfig(
            runtime_mode="vision_first",
            vision_enabled=True,
            max_steps=3,
        ),
        artifact_root=tmp_path,
        capture=DeterministicScreenCapture(
            [_observation("c"), _observation("d"), _observation("e")]
        ),
        vision=_Interpreter(),
        planner=DeterministicActionPlanner([action, action]),
        executor=executor,
        verifier=DeterministicStepVerifier(
            [
                VerificationResult(
                    verified=True,
                    confidence=0.9,
                    status=VisionVerificationStatus.SATISFIED,
                    reason_code="VISION_VERIFICATION_SATISFIED",
                )
            ]
        ),
    )

    artifact = runtime.run(
        VisionRunRequest(
            job_id="job-repeated-action",
            objective="Click once",
            mode=ComputerUseMode.EXECUTE,
        )
    )

    assert artifact.status == "failed"
    assert artifact.stop_reason == "VISION_REPEATED_ACTION_REJECTED"
    assert len(executor.executed) == 1
    summary = json.loads(
        (tmp_path / "job-repeated-action" / "vision_runtime_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["no_progress_stops"] == 1
    assert summary["stop_reason"] == "VISION_REPEATED_ACTION_REJECTED"
    assert summary["raw_screenshot_persisted"] == 0


def test_runtime_stops_when_wait_budget_is_exceeded(tmp_path) -> None:
    executor = _Executor()
    runtime = VisionComputerUseRuntime(
        config=ComputerUseRuntimeConfig(
            runtime_mode="vision_first",
            vision_enabled=True,
            max_steps=3,
            max_consecutive_wait_actions=1,
        ),
        artifact_root=tmp_path,
        capture=DeterministicScreenCapture(
            [_observation("c"), _observation("c"), _observation("c")]
        ),
        vision=_Interpreter(),
        planner=DeterministicActionPlanner(
            [
                _action(action_id="wait-1", action_type=InputActionType.WAIT),
                _action(action_id="wait-2", action_type=InputActionType.WAIT),
            ]
        ),
        executor=executor,
        verifier=DeterministicStepVerifier(
            [
                VerificationResult(
                    verified=True,
                    confidence=0.75,
                    status=VisionVerificationStatus.SKIPPED,
                    reason_code="VISION_VERIFICATION_SKIPPED",
                )
            ]
        ),
    )

    artifact = runtime.run(
        VisionRunRequest(
            job_id="job-wait-budget",
            objective="Wait until stable",
            mode=ComputerUseMode.EXECUTE,
        )
    )

    assert artifact.status == "failed"
    assert artifact.stop_reason == "VISION_WAIT_BUDGET_EXCEEDED"
    assert len(executor.executed) == 1


def test_runner_ollama_vision_first_uses_candidate_action_planner(
    tmp_path,
    monkeypatch,
) -> None:
    class FakeCapture:
        def __init__(self, **_: object) -> None:
            pass

        def capture(self) -> VisionObservation:
            return _observation()

    class FakeOllamaVision:
        def __init__(self, **_: object) -> None:
            pass

        def interpret(self, *, objective, observation, world):  # noqa: ANN001
            del objective, world
            return VisionInterpretation(
                observation_hash=observation.screenshot_hash,
                summary="A submit button is visible.",
                candidate_actions=[
                    _action(action_type=InputActionType.CLICK, risk_class=RiskClass.MEDIUM)
                ],
                surface_kind=SurfaceKind.BROWSER,
                active_app_guess="Safari",
                confidence=0.93,
            )

    class FakeMacOSExecutor:
        def __init__(self, **_: object) -> None:
            self.executed: list[VisionAction] = []

        def execute(self, action: VisionAction) -> ExecutionResult:
            self.executed.append(action)
            return ExecutionResult(status="executed", message="ok")

    monkeypatch.setattr(computer_use_runtime, "current_platform", lambda: _MacOSPlatform())
    monkeypatch.setattr(computer_use_runtime, "MacOSScreenCaptureProvider", FakeCapture)
    monkeypatch.setattr(computer_use_runtime, "OllamaVisionInterpreter", FakeOllamaVision)
    monkeypatch.setattr(computer_use_runtime, "MacOSInputExecutor", FakeMacOSExecutor)
    monkeypatch.setattr(computer_use_runtime, "_current_git_sha", lambda: "fixture-commit")

    runner = computer_use_runtime.ComputerUseRunner(
        config=RuntimeConfig(
            computer_use=ComputerUseRuntimeConfig(
                runtime_mode="vision_first",
                vision_enabled=True,
                vision_provider="ollama",
                vision_model="llava",
                macos_live_enabled=True,
                macos_capture_backend="screencapture",
                macos_input_backend="quartz",
                macos_qualification_report=str(
                    FIXTURE_ROOT / "macos_supervised_v2_evidence_pass.json"
                ),
                action_set=["click"],
                max_steps=1,
            )
        ),
        root_dir=tmp_path,
    )

    payload = runner.run(
        prompt="Submit safe fixture",
        job_id="job-ollama-candidate",
        mode=ComputerUseMode.STEP_APPROVAL,
        runtime_mode="vision_first",
    )

    assert payload["job"]["status"] == "awaiting_approval"
    assert payload["computer_use"]["steps"][0]["action"]["action_type"] == "click"
