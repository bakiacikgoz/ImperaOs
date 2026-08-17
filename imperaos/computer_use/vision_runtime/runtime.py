from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.computer_use.vision_runtime.approval import hash_json
from imperaos.computer_use.vision_runtime.errors import VisionRuntimeError
from imperaos.computer_use.vision_runtime.models import (
    InputActionType,
    StopDecision,
    VerificationResult,
    VisionAction,
    VisionObservation,
    VisionPolicyDecision,
    VisionRunArtifact,
    VisionRunRequest,
    VisionStepResult,
)
from imperaos.computer_use.vision_runtime.policy import UniversalComputerUsePolicy
from imperaos.computer_use.vision_runtime.ports import (
    ActionPlannerPort,
    InputExecutorPort,
    ScreenCapturePort,
    StepVerifierPort,
    VisionAuditSink,
    VisionInterpreterPort,
)
from imperaos.computer_use.vision_runtime.recorder import RedactedVisionAuditRecorder
from imperaos.computer_use.vision_runtime.runtime_gate import (
    ResolverSnapshotCallable,
    RuntimePreflightContext,
    evaluate_runtime_preflight,
)
from imperaos.runtime.config import ComputerUseRuntimeConfig


class VisionComputerUseRuntime:
    def __init__(
        self,
        *,
        config: ComputerUseRuntimeConfig,
        artifact_root: Path,
        capture: ScreenCapturePort,
        vision: VisionInterpreterPort | None,
        planner: ActionPlannerPort,
        executor: InputExecutorPort,
        verifier: StepVerifierPort,
        audit: VisionAuditSink | None = None,
        runtime_preflight_context: RuntimePreflightContext | None = None,
        runtime_preflight_resolver: ResolverSnapshotCallable | None = None,
    ) -> None:
        self.config = config
        self.artifact_root = Path(artifact_root)
        self.capture = capture
        self.vision = vision
        self.planner = planner
        self.executor = executor
        self.verifier = verifier
        self._policy: UniversalComputerUsePolicy | None = None
        self.audit = audit
        self.runtime_preflight_context = runtime_preflight_context
        self.runtime_preflight_resolver = runtime_preflight_resolver

    @property
    def policy(self) -> UniversalComputerUsePolicy:
        if self._policy is None:
            self._policy = UniversalComputerUsePolicy(self.config)
        return self._policy

    def run(self, request: VisionRunRequest) -> VisionRunArtifact:
        if self.runtime_preflight_context is not None:
            preflight = evaluate_runtime_preflight(
                context=self.runtime_preflight_context,
                resolver=self.runtime_preflight_resolver,
            )
            if not preflight.allowed:
                runtime_preflight = preflight.to_payload()["runtimePreflight"]
                recorder = self._recorder(
                    request,
                    policy_hash=_hash_json(
                        {
                            "runtime": "vision_first",
                            "policy": "runtime_preflight_blocked",
                        }
                    ),
                )
                if isinstance(runtime_preflight, dict):
                    _record_preflight_blocked_lifecycle(
                        recorder,
                        runtime_preflight=runtime_preflight,
                        reason_code=preflight.reason_code,
                    )
                envelope = recorder.finalize("blocked")
                return self._artifact(
                    request=request,
                    status="blocked",
                    steps=[],
                    envelope=envelope,
                    stop_reason=preflight.reason_code,
                    runtime_preflight=runtime_preflight
                    if isinstance(runtime_preflight, dict)
                    else None,
                )
        policy = self.policy
        recorder = self._recorder(request, policy_hash=policy.policy_hash)
        if self.vision is None:
            envelope = recorder.finalize("failed")
            return self._artifact(
                request=request,
                status="failed",
                steps=[],
                envelope=envelope,
                stop_reason="VISION_PROVIDER_UNAVAILABLE",
            )

        steps: list[VisionStepResult] = []
        recovery_attempts = 0
        seen_action_digests: set[str] = set()
        consecutive_wait_actions = 0
        for step_index in range(self.config.max_steps):
            try:
                before = self.capture.capture()
            except VisionRuntimeError as exc:
                envelope = recorder.finalize("failed")
                return self._artifact(
                    request=request,
                    status="failed",
                    steps=steps,
                    envelope=envelope,
                    stop_reason=exc.reason_code,
                )
            surface_stop = policy.detect_surface_stop(before, objective=request.objective)
            if surface_stop is not None:
                step = self._blocked_step(step_index, before.screenshot_hash, surface_stop)
                steps.append(step)
                recorder.record_step(step)
                envelope = recorder.finalize("failed")
                return self._artifact(
                    request=request,
                    status="failed",
                    steps=steps,
                    envelope=envelope,
                    stop_reason=surface_stop.reason_code,
                )

            try:
                interpretation = self.vision.interpret(
                    objective=request.objective,
                    observation=before,
                    world=None,
                )
            except VisionRuntimeError as exc:
                envelope = recorder.finalize("failed")
                return self._artifact(
                    request=request,
                    status="failed",
                    steps=steps,
                    envelope=envelope,
                    stop_reason=exc.reason_code,
                )
            if interpretation.confidence < self.config.min_verification_confidence:
                envelope = recorder.finalize("failed")
                return self._artifact(
                    request=request,
                    status="failed",
                    steps=steps,
                    envelope=envelope,
                    stop_reason="VISION_CONFIDENCE_BELOW_THRESHOLD",
                )
            before = self._enrich_observation(before, interpretation)
            surface_stop = policy.detect_surface_stop(before, objective=request.objective)
            if surface_stop is not None:
                step = self._blocked_step(step_index, before.screenshot_hash, surface_stop)
                steps.append(step)
                recorder.record_step(step)
                envelope = recorder.finalize("failed")
                return self._artifact(
                    request=request,
                    status="failed",
                    steps=steps,
                    envelope=envelope,
                    stop_reason=surface_stop.reason_code,
                )
            action_or_stop = self.planner.next_action(
                objective=request.objective,
                interpretation=interpretation,
                world=None,
            )
            if isinstance(action_or_stop, StopDecision):
                envelope = recorder.finalize("completed")
                return self._artifact(
                    request=request,
                    status="completed",
                    steps=steps,
                    envelope=envelope,
                    stop_reason=action_or_stop.reason,
                )

            action = action_or_stop
            action_digest = _hash_json(action.model_dump(mode="json", exclude_none=True))
            if action_digest in seen_action_digests:
                step = self._loop_guard_step(
                    step_index=step_index,
                    before_hash=before.screenshot_hash,
                    action=action,
                    reason_code="VISION_REPEATED_ACTION_REJECTED",
                )
                steps.append(step)
                recorder.record_step(step)
                envelope = recorder.finalize("failed")
                return self._artifact(
                    request=request,
                    status="failed",
                    steps=steps,
                    envelope=envelope,
                    stop_reason="VISION_REPEATED_ACTION_REJECTED",
                )
            if (
                action.action_type == InputActionType.WAIT
                and consecutive_wait_actions >= self.config.max_consecutive_wait_actions
            ):
                step = self._loop_guard_step(
                    step_index=step_index,
                    before_hash=before.screenshot_hash,
                    action=action,
                    reason_code="VISION_WAIT_BUDGET_EXCEEDED",
                )
                steps.append(step)
                recorder.record_step(step)
                envelope = recorder.finalize("failed")
                return self._artifact(
                    request=request,
                    status="failed",
                    steps=steps,
                    envelope=envelope,
                    stop_reason="VISION_WAIT_BUDGET_EXCEEDED",
                )
            seen_action_digests.add(action_digest)
            decision = policy.classify(action, before, mode=request.mode)
            if decision.denied:
                step = self._step(
                    step_index=step_index,
                    before_hash=before.screenshot_hash,
                    action=action,
                    decision=decision,
                    execution_status="blocked",
                )
                steps.append(step)
                recorder.record_step(step)
                envelope = recorder.finalize("failed")
                return self._artifact(
                    request=request,
                    status="failed",
                    steps=steps,
                    envelope=envelope,
                    stop_reason=decision.reason_code,
                )
            if decision.requires_approval:
                step = self._step(
                    step_index=step_index,
                    before_hash=before.screenshot_hash,
                    action=action,
                    decision=decision,
                    execution_status="approval_required",
                    approval_snapshot=self._approval_snapshot(
                        request=request,
                        step_index=step_index,
                        before=before,
                        action=action,
                        decision=decision,
                    ),
                )
                steps.append(step)
                recorder.record_step(step)
                envelope = recorder.finalize("awaiting_approval")
                return self._artifact(
                    request=request,
                    status="awaiting_approval",
                    steps=steps,
                    envelope=envelope,
                )

            execution = self.executor.execute(action)
            if execution.status == "blocked":
                reason = str(
                    execution.details.get("reason_code") or "COMPUTER_USE_APPROVAL_REQUIRED"
                )
                step = self._step(
                    step_index=step_index,
                    before_hash=before.screenshot_hash,
                    action=action,
                    decision=VisionPolicyDecision(
                        allowed=False,
                        denied=True,
                        requires_approval=False,
                        reason_code=reason,
                        risk_reasons=[reason],
                        policy_hash=self.policy.policy_hash,
                    ),
                    execution_status="blocked",
                )
                steps.append(step)
                recorder.record_step(step)
                envelope = recorder.finalize("failed")
                return self._artifact(
                    request=request,
                    status="failed",
                    steps=steps,
                    envelope=envelope,
                    stop_reason=reason,
                )
            if execution.status == "failed":
                verification = VerificationResult(
                    verified=False,
                    confidence=0.0,
                    message=execution.message or "execution failed",
                )
                step = self._step(
                    step_index=step_index,
                    before_hash=before.screenshot_hash,
                    action=action,
                    decision=decision,
                    execution_status="failed",
                    verification=verification,
                )
                steps.append(step)
                recorder.record_step(step)
                envelope = recorder.finalize("failed")
                return self._artifact(
                    request=request,
                    status="failed",
                    steps=steps,
                    envelope=envelope,
                    stop_reason=str(
                        execution.details.get("reason_code") or "EXECUTION_FAILED"
                    ),
                )

            try:
                after = self.capture.capture()
            except VisionRuntimeError as exc:
                envelope = recorder.finalize("failed")
                return self._artifact(
                    request=request,
                    status="failed",
                    steps=steps,
                    envelope=envelope,
                    stop_reason=exc.reason_code,
                )
            verification = self.verifier.verify(before=before, action=action, after=after)
            step = self._step(
                step_index=step_index,
                before_hash=before.screenshot_hash,
                action=action,
                decision=decision,
                execution_status="executed",
                after_hash=after.screenshot_hash,
                verification=verification,
                checkpoint_id=f"{request.job_id}:{step_index}",
            )
            steps.append(step)
            recorder.record_step(step)
            if action.action_type == InputActionType.WAIT:
                consecutive_wait_actions += 1
            else:
                consecutive_wait_actions = 0
            if not verification.verified:
                if recovery_attempts >= self.config.max_recovery_attempts:
                    envelope = recorder.finalize("failed")
                    return self._artifact(
                        request=request,
                        status="failed",
                        steps=steps,
                        envelope=envelope,
                        stop_reason=(
                            verification.reason_code
                            or "COMPUTER_USE_RECOVERY_BUDGET_EXCEEDED"
                        ),
                    )
                recovery_attempts += 1

        envelope = recorder.finalize("failed")
        return self._artifact(
            request=request,
            status="failed",
            steps=steps,
            envelope=envelope,
            stop_reason="COMPUTER_USE_MAX_STEPS_EXCEEDED",
        )

    def _blocked_step(
        self,
        step_index: int,
        before_hash: str,
        decision: VisionPolicyDecision,
    ) -> VisionStepResult:
        return self._step(
            step_index=step_index,
            before_hash=before_hash,
            action=VisionAction(
                action_id=f"blocked-{step_index}",
                action_type="wait",
                rationale="Policy blocked before action planning.",
                expected_effect="No action is executed.",
                risk_class="critical",
                requires_approval=False,
                confidence=1.0,
            ),
            decision=decision,
            execution_status="blocked",
        )

    def _loop_guard_step(
        self,
        *,
        step_index: int,
        before_hash: str,
        action: VisionAction,
        reason_code: str,
    ) -> VisionStepResult:
        return self._step(
            step_index=step_index,
            before_hash=before_hash,
            action=action,
            decision=VisionPolicyDecision(
                allowed=False,
                denied=True,
                requires_approval=False,
                reason_code=reason_code,
                risk_reasons=[reason_code],
                policy_hash=self.policy.policy_hash,
            ),
            execution_status="blocked",
        )

    @staticmethod
    def _step(
        *,
        step_index: int,
        before_hash: str,
        action: VisionAction,
        decision: VisionPolicyDecision,
        execution_status: str,
        after_hash: str | None = None,
        verification: VerificationResult | None = None,
        checkpoint_id: str | None = None,
        approval_snapshot: dict[str, Any] | None = None,
    ) -> VisionStepResult:
        return VisionStepResult(
            step_index=step_index,
            before_hash=before_hash,
            action=action,
            policy_decision=decision,
            execution_status=execution_status,
            after_hash=after_hash,
            verification=verification,
            checkpoint_id=checkpoint_id,
            approval_snapshot=approval_snapshot,
        )

    def _approval_snapshot(
        self,
        *,
        request: VisionRunRequest,
        step_index: int,
        before: VisionObservation,
        action: VisionAction,
        decision: VisionPolicyDecision,
    ) -> dict[str, Any]:
        return build_approval_snapshot(
            job_id=request.job_id,
            step_index=step_index,
            objective=request.objective,
            observation=before,
            action=action,
            policy_hash=decision.policy_hash,
            risk_reasons=decision.risk_reasons,
            max_age_ms=self.config.approval_snapshot_max_age_ms,
        )

    @staticmethod
    def _enrich_observation(
        observation,
        interpretation,
    ):
        updates: dict[str, Any] = {
            "surface_kind": interpretation.surface_kind,
            "visible_text_redacted": interpretation.visible_text_redacted,
            "ui_elements": interpretation.ui_elements,
            "sensitive_indicators": interpretation.sensitive_indicators,
        }
        if interpretation.active_app_guess:
            updates["active_app"] = interpretation.active_app_guess
        if interpretation.active_window_title_guess:
            updates["active_window_title"] = interpretation.active_window_title_guess
        return observation.model_copy(update=updates)

    def _recorder(
        self,
        request: VisionRunRequest,
        *,
        policy_hash: str,
    ) -> VisionAuditSink:
        return self.audit or RedactedVisionAuditRecorder(
            job_id=request.job_id,
            job_dir=self.artifact_root / request.job_id,
            runtime_config_hash=_hash_json(self.config.model_dump(mode="json")),
            policy_hash=policy_hash,
        )

    def _artifact(
        self,
        *,
        request: VisionRunRequest,
        status: str,
        steps: list[VisionStepResult],
        envelope: dict[str, Any],
        stop_reason: str | None = None,
        runtime_preflight: dict[str, Any] | None = None,
    ) -> VisionRunArtifact:
        artifact = VisionRunArtifact(
            job_id=request.job_id,
            status=status,
            objective=request.objective,
            steps=steps,
            redaction_report=envelope.get("redaction_report", {}),
            integrity=envelope.get("integrity", {}),
            stop_reason=stop_reason,
            runtime_preflight=runtime_preflight,
        )
        summary = _build_runtime_safety_summary(
            request=request,
            status=status,
            steps=steps,
            envelope=envelope,
            stop_reason=stop_reason,
            runtime_preflight=runtime_preflight,
        )
        summary_path = self.artifact_root / request.job_id / "vision_runtime_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return artifact


def _hash_json(payload: object) -> str:
    return hash_json(payload)


def _record_preflight_blocked_lifecycle(
    recorder: VisionAuditSink,
    *,
    runtime_preflight: dict[str, Any],
    reason_code: str,
) -> None:
    record_start = getattr(recorder, "record_runtime_start", None)
    record_blocked = getattr(recorder, "record_preflight_blocked", None)
    record_stop = getattr(recorder, "record_runtime_stop", None)
    if callable(record_start) and callable(record_blocked) and callable(record_stop):
        record_start()
        record_blocked(runtime_preflight)
        record_stop(status="blocked", reason_code=reason_code)


def _build_runtime_safety_summary(
    *,
    request: VisionRunRequest,
    status: str,
    steps: list[VisionStepResult],
    envelope: dict[str, Any],
    stop_reason: str | None,
    runtime_preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reject_reasons: Counter[str] = Counter()
    semantic_counts: Counter[str] = Counter(
        {
            "satisfied": 0,
            "inconclusive": 0,
            "failed": 0,
            "skipped": 0,
        }
    )
    approval_blocks = 0
    actions_executed = 0

    for step in steps:
        decision = step.policy_decision
        if step.execution_status == "executed":
            actions_executed += 1
        if step.execution_status == "approval_required" or decision.requires_approval:
            approval_blocks += 1
        if decision.denied:
            reject_reasons[decision.reason_code] += 1
        if step.verification is not None:
            verification_status = _verification_status_key(step.verification)
            semantic_counts[verification_status] += 1

    redaction_report = envelope.get("redaction_report", {})
    raw_screenshot_count = _safe_int(
        redaction_report.get("raw_screenshot_persisted_count"),
        default=0,
    )
    effective_stop_reason = stop_reason or status
    no_progress_reasons = {
        "VISION_NO_PROGRESS_DETECTED",
        "VISION_REPEATED_ACTION_REJECTED",
        "VISION_WAIT_BUDGET_EXCEEDED",
    }
    summary = {
        "artifact_version": "computer_use_vision_runtime_summary/v1",
        "job_id": request.job_id,
        "status": status,
        "candidate_actions_seen": len(steps),
        "candidate_actions_rejected": sum(reject_reasons.values()),
        "candidate_reject_reasons": dict(sorted(reject_reasons.items())),
        "actions_executed": actions_executed,
        "approval_blocks": approval_blocks,
        "approval_resumes": 0,
        "semantic_verification": {
            key: int(semantic_counts[key])
            for key in ("satisfied", "inconclusive", "failed", "skipped")
        },
        "no_progress_stops": 1 if effective_stop_reason in no_progress_reasons else 0,
        "raw_screenshot_persisted": raw_screenshot_count,
        "stop_reason": effective_stop_reason,
    }
    if runtime_preflight is not None:
        summary["runtimePreflight"] = runtime_preflight
    return summary


def _verification_status_key(verification: VerificationResult) -> str:
    status = verification.status
    if status is not None:
        return str(getattr(status, "value", status))
    if verification.verified:
        return "satisfied"
    return "failed"


def _safe_int(value: object, *, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def build_approval_snapshot(
    *,
    job_id: str,
    step_index: int,
    objective: str,
    observation: VisionObservation,
    action: VisionAction,
    policy_hash: str,
    risk_reasons: list[str],
    max_age_ms: int,
    created_at: str | None = None,
    planner_version: str = "candidate_action_planner/v1",
    provider_name: str | None = None,
    provider_model: str | None = None,
) -> dict[str, Any]:
    action_payload = action.model_dump(mode="json", exclude_none=True)
    action_hash = hash_json(action_payload)
    objective_hash = hash_json({"objective": objective})
    return {
        "kind": "computer_use_vision_action",
        "approval_kind": "computer_use_step",
        "job_id": job_id,
        "step_index": step_index,
        "step_id": f"step_{step_index:03d}",
        "objective_hash": objective_hash,
        "objective_digest": objective_hash,
        "before_screenshot_hash": observation.screenshot_hash,
        "observation_digest": observation.screenshot_hash,
        "action_hash": action_hash,
        "action_digest": action_hash,
        "policy_hash": policy_hash,
        "planner_version": planner_version,
        "provider_name": provider_name,
        "provider_model": provider_model,
        "active_app": observation.active_app,
        "active_window_title": observation.active_window_title,
        "surface_kind": observation.surface_kind.value,
        "target_element_id": action.target_element_id,
        "target_bbox": action.target_bbox.model_dump(mode="json")
        if action.target_bbox is not None
        else None,
        "action_type": action.action_type.value,
        "expected_effect": action.expected_effect,
        "risk_class": action.risk_class.value,
        "risk_reasons": risk_reasons,
        "created_at": created_at or datetime.now(UTC).isoformat(),
        "max_age_ms": max_age_ms,
        "raw_screenshot_path": None,
        "execution_contract": {
            "action_hash": action_hash,
            "max_age_ms": max_age_ms,
        },
    }
