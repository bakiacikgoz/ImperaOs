from __future__ import annotations

from pathlib import Path

from imperaos.computer_use import (
    BrowserAllowlistPolicy,
    BrowserTaskFamily,
    ComputerUseMode,
    ComputerUseSession,
    PerceptionSnapshot,
    ScaffoldBrowserAdapter,
    SessionRequest,
    TargetDescriptor,
)
from imperaos.computer_use.models import EvidenceEnvelope, PerceptionSource, SelectorContext
from imperaos.computer_use.perception import build_perception_fingerprint, select_perception_source
from imperaos.computer_use.planner import plan_browser_task
from imperaos.governance.runtime import GovernanceRuntime
from imperaos.runtime.config import RuntimeConfig


def _target(url: str = "https://ops.example.internal/queue") -> TargetDescriptor:
    return TargetDescriptor(
        target_ref="queue-row-17",
        window_identity="tab-17",
        app_identity="browser:safari",
        selector_source="dom",
        selector="[data-row-id='17']",
        expected_effect="Inspect or update the selected queue row.",
        current_url=url,
    )


class _StaticAdapter(ScaffoldBrowserAdapter):
    def __init__(self, snapshot: PerceptionSnapshot):
        self._snapshot = snapshot

    def inspect_target(self, *, target: TargetDescriptor) -> PerceptionSnapshot:
        del target
        return self._snapshot


def _snapshot(
    url: str = "https://ops.example.internal/queue",
    *,
    sensitive: bool = False,
    source: PerceptionSource = PerceptionSource.DOM,
    confidence: float = 0.94,
    focused: bool = True,
    unexpected_modal: bool = False,
    selector_ambiguous: bool = False,
    raw_screenshot_path: str | None = None,
) -> PerceptionSnapshot:
    selector_context = SelectorContext(
        selector="[data-row-id='17']",
        selector_source="dom",
        selector_trace=["queue-table", "queue-row-17"],
    )
    return PerceptionSnapshot(
        source=source,
        confidence=confidence,
        perception_fingerprint=build_perception_fingerprint(
            window_or_tab_identity="tab-17",
            app_identity="browser:safari",
            selector_context=selector_context.model_dump(mode="json"),
            screenshot_hash="shot-hash-1",
        ),
        sensitive_surface=sensitive,
        focused=focused,
        unexpected_modal=unexpected_modal,
        selector_ambiguous=selector_ambiguous,
        window_or_tab_identity="tab-17",
        app_identity="browser:safari",
        current_url=url,
        selector_context=selector_context,
        evidence=EvidenceEnvelope(
            screenshot_hash="shot-hash-1",
            redacted_fingerprint="fingerprint-1",
            accessibility_subset={"role": "row"},
            raw_screenshot_path=raw_screenshot_path,
        ),
    )


def test_select_perception_source_prefers_dom() -> None:
    assert (
        select_perception_source([PerceptionSource.SCREENSHOT, PerceptionSource.DOM])
        == PerceptionSource.DOM
    )


def test_computer_use_session_blocks_sensitive_surface() -> None:
    policy = BrowserAllowlistPolicy(allowlisted_domains=["ops.example.internal"])
    session = ComputerUseSession(policy=policy)
    request = SessionRequest(
        run_id="run-sensitive",
        prompt="update queue",
        mode=ComputerUseMode.DRY_RUN,
        task_family=BrowserTaskFamily.QUEUE_STATUS_UPDATE,
        allowlisted_domains=["ops.example.internal"],
    )
    actions = plan_browser_task(family=request.task_family, mode=request.mode, target=_target())
    outcome = session.run(request=request, perception=_snapshot(sensitive=True), actions=actions)
    assert outcome.status.value == "stopped"
    assert outcome.stop_reason.value == "sensitive_surface_detected"


def test_step_approval_records_device_action_snapshot(tmp_path: Path) -> None:
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
        run_id="run-device-action",
        prompt="inspect queue row",
        mode=ComputerUseMode.STEP_APPROVAL,
        task_family=BrowserTaskFamily.PAGE_INSPECTION,
        allowlisted_domains=["ops.example.internal"],
    )
    actions = plan_browser_task(family=request.task_family, mode=request.mode, target=_target())
    outcome = session.run(request=request, perception=_snapshot(), actions=actions)

    assert outcome.status.value == "awaiting_approval"
    assert len(outcome.approval_ids) == 1
    ticket = runtime.get_approval(outcome.approval_ids[0])
    assert ticket is not None
    assert ticket.target_kind == "device_action"
    assert ticket.snapshot["kind"] == "device_action"
    assert ticket.snapshot["target_kind"] == "device_action"
    assert ticket.snapshot["action_hash"] == ticket.action_hash
    assert ticket.snapshot["policy_hash"] == ticket.policy_hash
    assert ticket.snapshot["window_or_tab_identity"] == "tab-17"
    assert ticket.snapshot["app_identity"] == "browser:safari"
    assert "selector_context" in ticket.snapshot
    assert "perception_fingerprint" in ticket.snapshot
    assert "action_plan" in ticket.snapshot
    assert "execution_contract" in ticket.snapshot
    assert ticket.snapshot["execution_contract"]["policy_hash"]


def test_run_browser_task_blocks_unsupported_platform() -> None:
    policy = BrowserAllowlistPolicy(allowlisted_domains=["ops.example.internal"])
    session = ComputerUseSession(policy=policy, platform_name="linux")
    request = SessionRequest(
        run_id="run-platform",
        prompt="inspect queue",
        mode=ComputerUseMode.DRY_RUN,
        task_family=BrowserTaskFamily.PAGE_INSPECTION,
        allowlisted_domains=["ops.example.internal"],
    )
    outcome = session.run_browser_task(request=request, target=_target())
    assert outcome.status.value == "stopped"
    assert outcome.stop_reason.value == "unsupported_platform"


def test_run_browser_task_requires_browser_adapter() -> None:
    policy = BrowserAllowlistPolicy(allowlisted_domains=["ops.example.internal"])
    session = ComputerUseSession(policy=policy, platform_name="darwin")
    request = SessionRequest(
        run_id="run-missing-adapter",
        prompt="inspect queue",
        mode=ComputerUseMode.DRY_RUN,
        task_family=BrowserTaskFamily.PAGE_INSPECTION,
        allowlisted_domains=["ops.example.internal"],
    )
    outcome = session.run_browser_task(request=request, target=_target())
    assert outcome.status.value == "stopped"
    assert outcome.stop_reason.value == "missing_adapter"


def test_run_browser_task_reports_scaffold_only_adapter() -> None:
    policy = BrowserAllowlistPolicy(allowlisted_domains=["ops.example.internal"])
    session = ComputerUseSession(
        policy=policy,
        browser_adapter=ScaffoldBrowserAdapter(),
        platform_name="darwin",
    )
    request = SessionRequest(
        run_id="run-scaffold-only",
        prompt="inspect queue",
        mode=ComputerUseMode.DRY_RUN,
        task_family=BrowserTaskFamily.PAGE_INSPECTION,
        allowlisted_domains=["ops.example.internal"],
    )
    outcome = session.run_browser_task(request=request, target=_target())
    assert outcome.status.value == "stopped"
    assert outcome.stop_reason.value == "autonomy_not_enabled"


def test_computer_use_session_hard_stops_on_visual_drift_signals() -> None:
    policy = BrowserAllowlistPolicy(allowlisted_domains=["ops.example.internal"])
    session = ComputerUseSession(policy=policy)
    request = SessionRequest(
        run_id="run-hard-stop",
        prompt="inspect queue",
        mode=ComputerUseMode.DRY_RUN,
        task_family=BrowserTaskFamily.PAGE_INSPECTION,
        allowlisted_domains=["ops.example.internal"],
    )
    cases = [
        (_snapshot(source=PerceptionSource.OCR), "unknown_visual"),
        (_snapshot(selector_ambiguous=True), "selector_ambiguous"),
        (_snapshot(focused=False), "focus_drift"),
        (_snapshot(unexpected_modal=True), "unexpected_modal"),
        (_snapshot(confidence=0.42), "confidence_below_threshold"),
    ]

    for perception, expected_reason in cases:
        outcome = session.run(
            request=request,
            perception=perception,
            actions=plan_browser_task(
                family=request.task_family,
                mode=request.mode,
                target=_target(),
            ),
        )
        assert outcome.status.value == "stopped"
        assert outcome.stop_reason.value == expected_reason


def test_recorder_defaults_to_redacted_evidence() -> None:
    policy = BrowserAllowlistPolicy(allowlisted_domains=["ops.example.internal"])
    session = ComputerUseSession(policy=policy)
    request = SessionRequest(
        run_id="run-redacted",
        prompt="inspect queue",
        mode=ComputerUseMode.DRY_RUN,
        task_family=BrowserTaskFamily.PAGE_INSPECTION,
        allowlisted_domains=["ops.example.internal"],
        raw_evidence_opt_in=False,
    )
    actions = plan_browser_task(family=request.task_family, mode=request.mode, target=_target())
    outcome = session.run(
        request=request,
        perception=_snapshot(raw_screenshot_path="/tmp/raw-preview.png"),
        actions=actions,
    )

    trace = outcome.recorder_artifact["traces"][0]
    assert "raw_screenshot_path" not in trace["evidence"]
    assert trace["evidence"]["redacted_fingerprint"] == "fingerprint-1"


def test_run_browser_task_uses_adapter_snapshot_for_dry_run() -> None:
    policy = BrowserAllowlistPolicy(allowlisted_domains=["ops.example.internal"])
    session = ComputerUseSession(
        policy=policy,
        browser_adapter=_StaticAdapter(_snapshot()),
        platform_name="darwin",
    )
    request = SessionRequest(
        run_id="run-adapter",
        prompt="inspect queue",
        mode=ComputerUseMode.DRY_RUN,
        task_family=BrowserTaskFamily.PAGE_INSPECTION,
        allowlisted_domains=["ops.example.internal"],
    )
    outcome = session.run_browser_task(request=request, target=_target())

    assert outcome.status.value == "preview_ready"
    assert outcome.actions[0].execution_result["status"] == "preview_only"
