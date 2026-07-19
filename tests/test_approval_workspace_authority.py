from __future__ import annotations

import hashlib
import inspect
from types import SimpleNamespace

import pytest

import imperaos.cli as cli
import imperaos.computer_use.runtime as computer_use_runtime
import imperaos.team.supervisor as team_supervisor
from imperaos.control_plane.models import ControlPlaneRunSummary, RunStatus
from imperaos.control_plane.run_coordinator import ControlPlaneRunCoordinator
from imperaos.governance.approval_store import ApprovalStore
from imperaos.governance.runtime import GovernanceRuntime
from imperaos.runtime.config import RuntimeConfig


def _ticket(store: ApprovalStore, workspace_id: str, key: str):
    snapshot = {"workspaceId": workspace_id, "kind": "task"}
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return store.create_ticket(
        workspace_id=workspace_id,
        run_id=f"run-{key}",
        target_kind="task",
        target_ref="chat",
        action_hash=digest,
        policy_hash=digest,
        request_hash=digest,
        snapshot_hash=digest,
        snapshot=snapshot,
        ttl_seconds=900,
        idempotency_key=key,
    )


def test_store_hides_foreign_ticket_for_pending_get_decide_and_execute(tmp_path) -> None:
    store = ApprovalStore(tmp_path / "approvals.sqlite3")
    local = _ticket(store, "workspace-a", "local")
    foreign = _ticket(store, "workspace-b", "foreign")

    assert [item.approval_id for item in store.list_pending(workspace_id="workspace-a")] == [
        local.approval_id
    ]
    assert store.get(foreign.approval_id, workspace_id="workspace-a") is None
    decision = store.decide(
        approval_id=foreign.approval_id,
        workspace_id="workspace-a",
        approve=True,
        actor="user-a",
        reason="should not exist",
    )
    execution = store.mark_executed(
        approval_id=foreign.approval_id,
        workspace_id="workspace-a",
        executed_by="user-a",
    )
    assert decision.error_code == execution.error_code == "APPROVAL_NOT_FOUND"
    assert store.get(foreign.approval_id, workspace_id="workspace-b").status.value == "pending"


def test_execute_persists_verified_executor_separately_from_decider(tmp_path) -> None:
    store = ApprovalStore(tmp_path / "approvals.sqlite3")
    ticket = _ticket(store, "workspace-a", "execute")
    assert store.decide(
        approval_id=ticket.approval_id,
        workspace_id="workspace-a",
        approve=True,
        actor="reviewer-a",
        reason="approved",
    ).error_code is None
    executed = store.mark_executed(
        approval_id=ticket.approval_id,
        workspace_id="workspace-a",
        executed_by="executor-a",
    )
    assert executed.error_code is None
    assert executed.ticket.actor == "reviewer-a"
    assert executed.ticket.executed_by == "executor-a"


def test_artifact_ticket_rejects_conflicting_workspace_bindings(tmp_path) -> None:
    store = ApprovalStore(tmp_path / "approvals.sqlite3")
    digest = "a" * 64
    with pytest.raises(ValueError, match="workspace binding"):
        store.create_ticket(
            workspace_id="workspace-a",
            run_id="run-conflict",
            target_kind="artifact_mutation_proposal",
            target_ref="workspace-b:artifact-1:proposal-1",
            action_hash=digest,
            policy_hash=digest,
            request_hash=digest,
            snapshot_hash=digest,
            snapshot={"workspaceId": "workspace-a"},
            ttl_seconds=900,
            idempotency_key="conflict",
        )


def test_store_omitted_workspace_fails_closed_without_existence_or_mutation(tmp_path) -> None:
    store = ApprovalStore(tmp_path / "approvals.sqlite3")
    ticket = _ticket(store, "workspace-a", "omitted")

    assert store.list_pending() == []
    assert store.get(ticket.approval_id) is None
    assert store.get_by_idempotency_key(ticket.idempotency_key) is None
    assert store.decide(
        approval_id=ticket.approval_id,
        approve=True,
        actor="unscoped-actor",
        reason="must not mutate",
    ).error_code == "APPROVAL_NOT_FOUND"
    assert store.get(ticket.approval_id, workspace_id="workspace-a").status.value == "pending"

    assert store.decide(
        approval_id=ticket.approval_id,
        workspace_id="workspace-a",
        approve=True,
        actor="reviewer-a",
        reason="approved",
    ).error_code is None
    assert store.mark_executed(
        approval_id=ticket.approval_id,
        executed_by="unscoped-executor",
    ).error_code == "APPROVAL_NOT_FOUND"
    scoped = store.get(ticket.approval_id, workspace_id="workspace-a")
    assert scoped.status.value == "approved"
    assert scoped.executed_by is None


def test_ticket_creation_requires_a_nonempty_workspace_binding(tmp_path) -> None:
    store = ApprovalStore(tmp_path / "approvals.sqlite3")
    digest = "b" * 64
    with pytest.raises(ValueError, match="workspace binding"):
        store.create_ticket(
            run_id="run-unbound",
            target_kind="task",
            target_ref="chat",
            action_hash=digest,
            policy_hash=digest,
            request_hash=digest,
            snapshot_hash=digest,
            snapshot={"kind": "task"},
            ttl_seconds=900,
            idempotency_key="unbound",
        )


def _runtime(tmp_path) -> GovernanceRuntime:
    config = RuntimeConfig.from_profile("default")
    config = config.model_copy(
        update={
            "governance": config.governance.model_copy(
                update={
                    "approval_store_path": str(tmp_path / "runtime-approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            )
        }
    )
    return GovernanceRuntime(config=config)


def _coordinator(tmp_path, workspace_id: str = "workspace-a") -> ControlPlaneRunCoordinator:
    config = RuntimeConfig.from_profile("default")
    config = config.model_copy(
        update={
            "governance": config.governance.model_copy(
                update={"approval_store_path": str(tmp_path / "coordinator-approvals.sqlite3")}
            ),
            "memory": config.memory.model_copy(
                update={
                    "workspace_authority": config.memory.workspace_authority.model_copy(
                        update={"default_workspace_id": workspace_id}
                    )
                }
            ),
        }
    )
    return ControlPlaneRunCoordinator(
        config=config,
        registry=SimpleNamespace(),
        root_dir=tmp_path / "control-plane",
    )


def _write_pending_run(
    coordinator: ControlPlaneRunCoordinator,
    *,
    run_id: str,
    approval_id: str,
) -> None:
    summary = ControlPlaneRunSummary(
        run_id=run_id,
        agent_id="agent-1",
        profile="default",
        status=RunStatus.APPROVAL_PENDING,
        submitted_by="operator-a",
        input_hash="a" * 64,
        policy_hash="b" * 64,
        approval_ids=[approval_id],
        next_actions=["approval.show", "approval.decide", "approval.execute"],
    )
    coordinator.store.write_json_atomic(
        f"runs/{run_id}.json",
        {"run": summary.model_dump(mode="json")},
    )


def test_runtime_carries_initiating_workspace_and_scopes_normal_lookup(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    _decision, ticket = runtime.evaluate_task(
        run_id="run-workspace-a",
        task_type="code",
        user_input="change code",
        workspace_id="workspace-a",
    )
    assert ticket is not None
    assert ticket.workspace_id == "workspace-a"
    assert runtime.get_approval(
        approval_id=ticket.approval_id,
        workspace_id="workspace-b",
    ) is None
    assert runtime.get_approval(
        approval_id=ticket.approval_id,
        run_id="run-workspace-a",
    ).approval_id == ticket.approval_id

    _manual_decision, manual = runtime.request_manual_task_approval(
        run_id="run-workspace-a",
        task_type="code",
        user_input="retry code",
        reason_code="MANUAL_REVIEW",
        explain="review required",
    )
    assert manual is not None
    assert manual.workspace_id == "workspace-a"


def test_resume_collection_hides_foreign_workspace_and_preserves_executor(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    ticket = _ticket(runtime.approval_store, "workspace-a", "resume")
    assert runtime.decide_approval(
        approval_id=ticket.approval_id,
        workspace_id="workspace-a",
        approve=True,
        actor="reviewer-a",
        reason="approved",
    ).error_code is None
    assert runtime.execute_approval(
        approval_id=ticket.approval_id,
        workspace_id="workspace-a",
        executed_by="executor-a",
    ).error_code is None
    events = [
        {
            "event": "approval_requested",
            "task_id": "task-1",
            "data": {"approval_id": ticket.approval_id, "target": "task"},
        }
    ]

    hidden, hidden_resolved = cli._collect_resume_overrides(
        events=events,
        governance_runtime=runtime,
        workspace_id="workspace-b",
    )
    assert hidden == {}
    assert hidden_resolved == []
    visible, resolved = cli._collect_resume_overrides(
        events=events,
        governance_runtime=runtime,
        workspace_id="workspace-a",
    )
    assert visible == {"task-1": {"task": ticket.approval_id}}
    assert resolved[0]["approval_id"] == ticket.approval_id
    assert runtime.get_approval(
        approval_id=ticket.approval_id,
        workspace_id="workspace-a",
    ).executed_by == "executor-a"


def test_run_coordinator_completes_after_same_workspace_approval_executes(tmp_path) -> None:
    coordinator = _coordinator(tmp_path)
    ticket = _ticket(coordinator.approvals, "workspace-a", "coordinator-local")
    assert coordinator.approvals.decide(
        approval_id=ticket.approval_id,
        workspace_id="workspace-a",
        approve=True,
        actor="reviewer-a",
        reason="approved",
    ).error_code is None
    assert coordinator.approvals.mark_executed(
        approval_id=ticket.approval_id,
        workspace_id="workspace-a",
        executed_by="executor-a",
    ).error_code is None
    _write_pending_run(
        coordinator,
        run_id="run-local",
        approval_id=ticket.approval_id,
    )

    result = coordinator.get_status(run_id="run-local")

    assert result.status == RunStatus.COMPLETED
    assert result.completed_at is not None


def test_run_coordinator_treats_foreign_approval_as_missing(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinator = _coordinator(tmp_path)
    foreign = _ticket(coordinator.approvals, "workspace-b", "coordinator-foreign")
    assert coordinator.approvals.decide(
        approval_id=foreign.approval_id,
        workspace_id="workspace-b",
        approve=True,
        actor="reviewer-b",
        reason="approved",
    ).error_code is None
    assert coordinator.approvals.mark_executed(
        approval_id=foreign.approval_id,
        workspace_id="workspace-b",
        executed_by="executor-b",
    ).error_code is None
    _write_pending_run(
        coordinator,
        run_id="run-foreign",
        approval_id=foreign.approval_id,
    )
    _write_pending_run(
        coordinator,
        run_id="run-missing",
        approval_id="approval-missing",
    )
    observed_workspaces: list[str | None] = []
    get_approval = coordinator.approvals.get

    def recording_get(approval_id: str, *, workspace_id: str | None = None):
        observed_workspaces.append(workspace_id)
        return get_approval(approval_id, workspace_id=workspace_id)

    monkeypatch.setattr(coordinator.approvals, "get", recording_get)

    foreign_result = coordinator.get_status(run_id="run-foreign")
    missing_result = coordinator.get_status(run_id="run-missing")

    assert observed_workspaces == ["workspace-a", "workspace-a"]
    assert foreign_result.status == missing_result.status == RunStatus.APPROVAL_PENDING
    assert foreign_result.completed_at is missing_result.completed_at is None
    assert foreign_result.next_actions == missing_result.next_actions


def test_operator_panel_uses_trusted_workspace_and_verified_decision_actor(monkeypatch) -> None:
    calls: dict[str, object] = {"decisions": []}

    class Store:
        def list_pending(self, *, workspace_id: str):
            calls["pending_workspace"] = workspace_id
            return []

    class Runtime:
        approval_store = Store()

        def decide_approval(self, **kwargs):
            calls["decisions"].append(kwargs)
            return SimpleNamespace(error_code=None, ticket=None)

    def require_permission(_config, permission: str):
        calls["permission"] = permission
        return SimpleNamespace(actor_id="verified-operator")

    prompts = iter(
        ["/pending", "/approve approval-a", "/reject approval-b", "/exit"]
    )
    monkeypatch.setattr(cli.RuntimeConfig, "from_profile", lambda _profile: object())
    monkeypatch.setattr(cli, "_require_permission_or_exit", require_permission)
    monkeypatch.setattr(cli, "_build_governance_runtime", lambda _config: Runtime())
    monkeypatch.setattr(cli, "_startup_abort", lambda _config, _runtime: None)
    monkeypatch.setattr(cli.typer, "prompt", lambda _label: next(prompts))

    cli.operator_panel(
        profile="balanced",
        stream=False,
        workspace_id="workspace-a",
    )

    assert calls["permission"] == "approval.decide"
    assert calls["pending_workspace"] == "workspace-a"
    assert [item["workspace_id"] for item in calls["decisions"]] == [
        "workspace-a",
        "workspace-a",
    ]
    assert [item["actor"] for item in calls["decisions"]] == [
        "verified-operator",
        "verified-operator",
    ]


def test_supervisor_and_computer_use_do_not_bypass_scoped_runtime_lookup() -> None:
    assert ".approval_store.get(" not in inspect.getsource(team_supervisor)
    assert ".approval_store.get(" not in inspect.getsource(computer_use_runtime)
