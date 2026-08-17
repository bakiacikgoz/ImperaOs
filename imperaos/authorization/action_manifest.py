from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    action_id: str
    permission: str
    bridge_command: str | None
    cli_command: str
    mutating: bool = True


ACTION_MANIFEST = {
    item.action_id: item
    for item in (
        ActionDefinition(
            "agent.register",
            "agent.registry.write",
            "bridge_control_plane_agent_register",
            "imperaos control-plane agent register",
        ),
        ActionDefinition(
            "agent.disable",
            "agent.registry.write",
            "bridge_control_plane_agent_disable",
            "imperaos control-plane agent disable",
        ),
        ActionDefinition(
            "run.submit",
            "runtime.run",
            "bridge_control_plane_run_submit",
            "imperaos control-plane run submit",
        ),
        ActionDefinition(
            "approval.decide",
            "approval.decide",
            "bridge_approval_decide",
            "imperaos approval decide",
        ),
        ActionDefinition(
            "approval.execute",
            "approval.execute",
            "bridge_approval_execute",
            "imperaos approval execute",
        ),
        ActionDefinition(
            "approval.reconcile", "approval.reconcile", None, "imperaos approval reconcile"
        ),
        ActionDefinition(
            "evidence.verify_latest",
            "evidence.verify",
            "bridge_control_plane_evidence_verify",
            "imperaos control-plane evidence verify",
            False,
        ),
    )
}
