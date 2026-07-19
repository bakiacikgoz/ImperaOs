from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from imperaos import __version__
from imperaos.control_plane.models import (
    AgentRecord,
    ControlPlaneDecisionAction,
    ControlPlaneRunSummary,
    RunStatus,
)
from imperaos.control_plane.policy_simulator import PolicySimulator
from imperaos.control_plane.registry import AgentRegistry
from imperaos.control_plane.storage import ControlPlaneStore, canonical_json_hash
from imperaos.enterprise.identity import IdentityResolutionError, require_permission
from imperaos.governance.approval_store import ApprovalStore
from imperaos.runtime.config import RuntimeConfig
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT


class ControlPlaneRunCoordinator:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        registry: AgentRegistry,
        root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
    ):
        self.config = config
        self.registry = registry
        self.store = ControlPlaneStore(root_dir)
        self.policy = PolicySimulator(config=config)
        self.approvals = ApprovalStore(config.governance.approval_store_path)

    def submit_run(
        self,
        *,
        agent_id: str,
        user_input: str,
        actor: str,
        mode: str = "supervised",
    ) -> ControlPlaneRunSummary:
        record = self.registry.get(agent_id)
        run_id = _new_run_id()
        input_hash = canonical_json_hash({"agent_id": agent_id, "user_input": user_input})
        identity_ref, identity_error = self._identity_ref(permission="runtime.run")
        simulation = self.policy.simulate_agent(record.spec)
        blocking_reasons = list(simulation.blocking_reasons)
        if identity_error is not None:
            blocking_reasons.append(identity_error)

        status = RunStatus.CREATED
        approval_ids: list[str] = []
        next_actions: list[str] = []

        if blocking_reasons:
            status = RunStatus.POLICY_BLOCKED
            next_actions = ["policy.simulate", "agent.update"]
        else:
            approval_decisions = [
                item
                for item in simulation.decisions
                if item.decision_action == ControlPlaneDecisionAction.REQUIRE_APPROVAL
            ]
            if approval_decisions and mode != "dry_run":
                for decision in approval_decisions:
                    snapshot = {
                        "kind": "control_plane_action",
                        "run_id": run_id,
                        "agent_id": agent_id,
                        "action_id": decision.action_id,
                        "decision": decision.model_dump(mode="json"),
                        "input_hash": input_hash,
                        "runtime_version": __version__,
                    }
                    ticket = self.approvals.create_ticket(
                        workspace_id=(
                            self.config.memory.workspace_authority.default_workspace_id
                        ),
                        run_id=run_id,
                        target_kind="control_plane_action",
                        target_ref=f"{agent_id}:{decision.action_id}",
                        action_hash=canonical_json_hash(decision.model_dump(mode="json")),
                        policy_hash=decision.policy_hash,
                        request_hash=input_hash,
                        snapshot_hash=canonical_json_hash(snapshot),
                        snapshot=snapshot,
                        ttl_seconds=self.config.governance.approval_ttl_seconds,
                        idempotency_key=f"control-plane:{run_id}:{decision.action_id}",
                    )
                    approval_ids.append(ticket.approval_id)
                status = RunStatus.APPROVAL_PENDING
                next_actions = ["approval.show", "approval.decide", "approval.execute"]
            else:
                status = RunStatus.COMPLETED
                next_actions = ["evidence.export", "evidence.verify"]

        summary = ControlPlaneRunSummary(
            run_id=run_id,
            agent_id=agent_id,
            profile=self.config.profile_name,
            status=status,
            submitted_by=actor,
            identity_ref=identity_ref,
            input_hash=input_hash,
            policy_hash=simulation.policy_hash,
            completed_at=datetime.now(UTC) if status == RunStatus.COMPLETED else None,
            approval_ids=approval_ids,
            artifact_refs=[],
            blocking_reasons=sorted(set(blocking_reasons)),
            next_actions=next_actions,
        )
        self._write_run(summary, record=record, simulation=simulation.model_dump(mode="json"))
        self.registry.update_record(
            record.model_copy(update={"last_run_id": run_id, "updated_at": datetime.now(UTC)})
        )
        return summary

    def get_status(self, *, run_id: str) -> ControlPlaneRunSummary:
        payload = self.store.read_json(f"runs/{run_id}.json", default=None)
        if not isinstance(payload, dict):
            raise FileNotFoundError(f"control-plane run not found: {run_id}")
        summary = ControlPlaneRunSummary.model_validate(payload["run"])
        if summary.status == RunStatus.APPROVAL_PENDING:
            workspace_id = self.config.memory.workspace_authority.default_workspace_id
            tickets = [
                self.approvals.get(item, workspace_id=workspace_id)
                for item in summary.approval_ids
            ]
            if tickets and all(ticket and ticket.status.value == "executed" for ticket in tickets):
                summary = summary.model_copy(
                    update={
                        "status": RunStatus.COMPLETED,
                        "completed_at": datetime.now(UTC),
                        "next_actions": ["evidence.export", "evidence.verify"],
                    }
                )
                payload["run"] = summary.model_dump(mode="json")
                self.store.write_json_atomic(f"runs/{run_id}.json", payload)
        return summary

    def list_runs(self) -> list[ControlPlaneRunSummary]:
        runs_root = self.store.path("runs")
        if not runs_root.exists():
            return []
        items: list[ControlPlaneRunSummary] = []
        for path in sorted(runs_root.glob("*.json"), reverse=True):
            payload = self.store.read_json(f"runs/{path.name}", default=None)
            if isinstance(payload, dict) and isinstance(payload.get("run"), dict):
                items.append(ControlPlaneRunSummary.model_validate(payload["run"]))
        return items

    def _write_run(self, summary: ControlPlaneRunSummary, *, record: AgentRecord, simulation: dict):
        self.store.write_json_atomic(
            f"runs/{summary.run_id}.json",
            {
                "version": "control-plane.run-state/v1",
                "run": summary.model_dump(mode="json"),
                "agent_spec": record.spec.model_dump(mode="json"),
                "policy_simulation": simulation,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

    def _identity_ref(self, *, permission: str) -> tuple[str | None, str | None]:
        try:
            actor = require_permission(self.config, permission=permission)
        except IdentityResolutionError as exc:
            return None, exc.error_code
        if actor is None:
            return "identity:disabled", None
        return f"identity:{actor.actor_id}:{actor.key_id}", None


def _new_run_id() -> str:
    now = datetime.now(UTC)
    return f"cp-run-{now.strftime('%Y%m%d-%H%M%S-%f')}"
