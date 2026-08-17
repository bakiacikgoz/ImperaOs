from __future__ import annotations

from imperaos.computer_use.models import (
    ActionCategory,
    BrowserTaskFamily,
    ComputerUseMode,
    ProposedAction,
    RiskClass,
    TargetDescriptor,
)


def plan_browser_task(
    *,
    family: BrowserTaskFamily,
    mode: ComputerUseMode,
    target: TargetDescriptor,
) -> list[ProposedAction]:
    preview = {
        BrowserTaskFamily.PAGE_INSPECTION: (
            "Inspect allowlisted page state without mutating the surface."
        ),
        BrowserTaskFamily.FORM_FILL_DRAFT: (
            "Prepare a bounded draft in the current form without submitting externally."
        ),
        BrowserTaskFamily.QUEUE_STATUS_UPDATE: (
            "Update a low-risk queue state on the current allowlisted page."
        ),
    }[family]
    action_id = {
        BrowserTaskFamily.PAGE_INSPECTION: "inspect_element",
        BrowserTaskFamily.FORM_FILL_DRAFT: "form_fill",
        BrowserTaskFamily.QUEUE_STATUS_UPDATE: "queue_status_update",
    }[family]
    category = {
        BrowserTaskFamily.PAGE_INSPECTION: ActionCategory.READ_ONLY,
        BrowserTaskFamily.FORM_FILL_DRAFT: ActionCategory.MUTATION,
        BrowserTaskFamily.QUEUE_STATUS_UPDATE: ActionCategory.MUTATION,
    }[family]
    risk = {
        BrowserTaskFamily.PAGE_INSPECTION: RiskClass.LOW,
        BrowserTaskFamily.FORM_FILL_DRAFT: RiskClass.MEDIUM,
        BrowserTaskFamily.QUEUE_STATUS_UPDATE: RiskClass.MEDIUM,
    }[family]
    return [
        ProposedAction(
            action_id=action_id,
            category=category,
            risk_class=risk,
            target_descriptor=target,
            window_identity=target.window_identity,
            app_identity=target.app_identity,
            selector_source=target.selector_source,
            expected_effect=target.expected_effect,
            approval_required=mode == ComputerUseMode.STEP_APPROVAL,
            dry_run_preview=preview,
        )
    ]
