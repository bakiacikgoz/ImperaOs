from __future__ import annotations

from pathlib import Path

from imperaos.computer_use import (
    BrowserAllowlistPolicy,
    BrowserTaskFamily,
    ComputerUseMode,
    ComputerUseSession,
    SessionRequest,
    TargetDescriptor,
)
from imperaos.computer_use.models import (
    EvidenceEnvelope,
    PerceptionSnapshot,
    PerceptionSource,
    SelectorContext,
)
from imperaos.computer_use.perception import build_perception_fingerprint
from imperaos.computer_use.planner import plan_browser_task
from imperaos.governance.runtime import GovernanceRuntime
from imperaos.runtime.config import RuntimeConfig


def _target() -> TargetDescriptor:
    return TargetDescriptor(
        target_ref="queue-row-17",
        window_identity="tab-17",
        app_identity="browser:safari",
        selector_source="dom",
        selector="[data-row-id='17']",
        expected_effect="Inspect the selected queue row.",
        current_url="https://ops.example.internal/queue",
    )


def _snapshot(*, focused: bool = True):
    selector_context = SelectorContext(
        selector="[data-row-id='17']",
        selector_source="dom",
        selector_trace=["queue-table", "queue-row-17"],
    )
    return {
        "source": PerceptionSource.DOM,
        "confidence": 0.95,
        "perception_fingerprint": build_perception_fingerprint(
            window_or_tab_identity="tab-17",
            app_identity="browser:safari",
            selector_context=selector_context.model_dump(mode="json"),
            screenshot_hash="shot-hash-1",
        ),
        "sensitive_surface": False,
        "focused": focused,
        "unexpected_modal": False,
        "selector_ambiguous": False,
        "window_or_tab_identity": "tab-17",
        "app_identity": "browser:safari",
        "current_url": "https://ops.example.internal/queue",
        "selector_context": selector_context,
        "evidence": EvidenceEnvelope(
            screenshot_hash="shot-hash-1",
            redacted_fingerprint="fingerprint-1",
            accessibility_subset={"role": "row"},
        ),
    }


def test_world_model_tracks_preview_checkpoint_state() -> None:
    policy = BrowserAllowlistPolicy(allowlisted_domains=["ops.example.internal"])
    session = ComputerUseSession(policy=policy)
    request = SessionRequest(
        run_id="run-preview",
        prompt="inspect queue",
        mode=ComputerUseMode.DRY_RUN,
        task_family=BrowserTaskFamily.PAGE_INSPECTION,
        allowlisted_domains=["ops.example.internal"],
    )
    target = _target()
    actions = plan_browser_task(family=request.task_family, mode=request.mode, target=target)
    outcome = session.run(
        request=request,
        perception=PerceptionSnapshot.model_validate(_snapshot()),
        actions=actions,
    )

    assert outcome.world_model is not None
    assert outcome.world_model.stage.value == "checkpoint"
    assert outcome.world_model.active_window is not None
    assert outcome.world_model.active_window.app_identity == "browser:safari"
    assert outcome.world_model.changed_resources[0].status == "preview_only"
    assert outcome.execution_trace[-1].stage.value == "completed"


def test_world_model_tracks_pending_approval_state(tmp_path: Path) -> None:
    config = RuntimeConfig.from_profile("default").model_copy(
        update={
            "governance": RuntimeConfig.from_profile("default").governance.model_copy(
                update={"approval_store_path": str(tmp_path / "approvals.sqlite3")}
            )
        }
    )
    runtime = GovernanceRuntime(config=config)
    policy = BrowserAllowlistPolicy(allowlisted_domains=["ops.example.internal"])
    session = ComputerUseSession(policy=policy, governance_runtime=runtime)
    request = SessionRequest(
        run_id="run-approval",
        prompt="inspect queue",
        mode=ComputerUseMode.STEP_APPROVAL,
        task_family=BrowserTaskFamily.PAGE_INSPECTION,
        allowlisted_domains=["ops.example.internal"],
    )
    target = _target()
    actions = plan_browser_task(family=request.task_family, mode=request.mode, target=target)
    outcome = session.run(
        request=request,
        perception=PerceptionSnapshot.model_validate(_snapshot()),
        actions=actions,
    )

    assert outcome.world_model is not None
    assert outcome.world_model.stage.value == "require_approval"
    assert outcome.world_model.pending_approval_ids == outcome.approval_ids
    assert outcome.world_model.user_intervention_required is True
    assert any(turn.stage.value == "require_approval" for turn in outcome.execution_trace)


def test_world_model_marks_drift_on_fail_closed_stop() -> None:
    policy = BrowserAllowlistPolicy(allowlisted_domains=["ops.example.internal"])
    session = ComputerUseSession(policy=policy)
    request = SessionRequest(
        run_id="run-drift",
        prompt="inspect queue",
        mode=ComputerUseMode.DRY_RUN,
        task_family=BrowserTaskFamily.PAGE_INSPECTION,
        allowlisted_domains=["ops.example.internal"],
    )
    target = _target()
    actions = plan_browser_task(family=request.task_family, mode=request.mode, target=target)
    snapshot = _snapshot(focused=False)
    outcome = session.run(
        request=request,
        perception=PerceptionSnapshot.model_validate(snapshot),
        actions=actions,
    )

    assert outcome.world_model is not None
    assert outcome.world_model.drift_detected is True
    assert "focus_drift" in outcome.world_model.notes
    assert outcome.execution_trace[-1].stage.value == "stopped"
