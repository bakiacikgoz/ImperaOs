from __future__ import annotations

from pathlib import Path

from imperaos.governance.runtime import GovernanceRuntime
from imperaos.runtime.config import RuntimeConfig

APPROVAL_POLICY = """
policy_schema_version = "1.0"
policy_version = "team-approval"
web_egress = "deny"

[[task_rules]]
id = "task-chat-allow"
task_types = ["chat", "plan", "research", "code", "mixed"]
action = "allow"

[[tool_rules]]
id = "tool-python"
command_roots = ["python", "uv", "pytest", "ruff", "rg"]
action = "allow"
arg_deny_regex = []

[[handoff_rules]]
id = "handoff-requires-approval"
from_roles = ["Intake Agent"]
to_roles = ["Execution Agent"]
action = "require_approval"

[[memory_scope_rules]]
id = "memory-requires-approval"
scopes = ["case"]
producer_roles = ["Execution Agent"]
visibilities = ["team"]
action = "require_approval"

[pii_rules]
patterns = []
"""


def _runtime(tmp_path: Path) -> GovernanceRuntime:
    cfg = RuntimeConfig.from_profile("default")
    cfg = cfg.model_copy(
        update={
            "governance": cfg.governance.model_copy(
                update={
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            )
        }
    )
    return GovernanceRuntime(config=cfg)


def test_handoff_policy_allows_with_default_rule(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    decision, ticket = runtime.evaluate_handoff(
        run_id="job-1",
        from_role="Intake Agent",
        to_role="Execution Agent",
        payload={"output": "ok"},
    )

    assert decision.action.value == "allow"
    assert decision.reason_code == "RULE_ROUTE"
    assert ticket is None


def test_memory_scope_policy_allows_with_default_rule(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    decision, ticket = runtime.evaluate_memory_write(
        run_id="job-2",
        scope="case",
        producer_role="Execution Agent",
        visibility="team",
    )

    assert decision.action.value == "allow"
    assert decision.reason_code == "RULE_ROUTE"
    assert ticket is None


def test_handoff_override_allows_after_approval(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.toml"
    policy_path.write_text(APPROVAL_POLICY, encoding="utf-8")

    cfg = RuntimeConfig.from_profile("default")
    cfg = cfg.model_copy(
        update={
            "governance": cfg.governance.model_copy(
                update={
                    "policy_path": str(policy_path),
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            )
        }
    )
    runtime = GovernanceRuntime(config=cfg)

    decision, ticket = runtime.evaluate_handoff(
        run_id="job-handoff",
        from_role="Intake Agent",
        to_role="Execution Agent",
        payload={"output": "x"},
    )
    assert decision.action.value == "require_approval"
    assert ticket is not None

    decided = runtime.decide_approval(
        approval_id=ticket.approval_id,
        approve=True,
        actor="tester",
        reason="ok",
    )
    assert decided.error_code is None
    executed = runtime.execute_approval(approval_id=ticket.approval_id)
    assert executed.error_code is None

    override_decision, override_ticket = runtime.evaluate_handoff(
        run_id="job-handoff-resume",
        from_role="Intake Agent",
        to_role="Execution Agent",
        payload={"output": "x"},
        override_approval_id=ticket.approval_id,
    )
    assert override_ticket is None
    assert override_decision.action.value == "allow"
    assert override_decision.matched_rule_path == "approval_override"


def test_memory_write_override_allows_after_approval(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.toml"
    policy_path.write_text(APPROVAL_POLICY, encoding="utf-8")

    cfg = RuntimeConfig.from_profile("default")
    cfg = cfg.model_copy(
        update={
            "governance": cfg.governance.model_copy(
                update={
                    "policy_path": str(policy_path),
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            )
        }
    )
    runtime = GovernanceRuntime(config=cfg)

    decision, ticket = runtime.evaluate_memory_write(
        run_id="job-memory",
        scope="case",
        producer_role="Execution Agent",
        visibility="team",
    )
    assert decision.action.value == "require_approval"
    assert ticket is not None

    decided = runtime.decide_approval(
        approval_id=ticket.approval_id,
        approve=True,
        actor="tester",
        reason="ok",
    )
    assert decided.error_code is None
    executed = runtime.execute_approval(approval_id=ticket.approval_id)
    assert executed.error_code is None

    override_decision, override_ticket = runtime.evaluate_memory_write(
        run_id="job-memory-resume",
        scope="case",
        producer_role="Execution Agent",
        visibility="team",
        override_approval_id=ticket.approval_id,
    )
    assert override_ticket is None
    assert override_decision.action.value == "allow"
    assert override_decision.matched_rule_path == "approval_override"


def test_handoff_override_rejects_approved_but_not_executed_ticket(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.toml"
    policy_path.write_text(APPROVAL_POLICY, encoding="utf-8")

    cfg = RuntimeConfig.from_profile("default")
    cfg = cfg.model_copy(
        update={
            "governance": cfg.governance.model_copy(
                update={
                    "policy_path": str(policy_path),
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            )
        }
    )
    runtime = GovernanceRuntime(config=cfg)

    decision, ticket = runtime.evaluate_handoff(
        run_id="job-handoff",
        from_role="Intake Agent",
        to_role="Execution Agent",
        payload={"output": "x"},
    )
    assert decision.action.value == "require_approval"
    assert ticket is not None

    decided = runtime.decide_approval(
        approval_id=ticket.approval_id,
        approve=True,
        actor="tester",
        reason="ok",
    )
    assert decided.error_code is None

    override_decision, override_ticket = runtime.evaluate_handoff(
        run_id="job-handoff-resume",
        from_role="Intake Agent",
        to_role="Execution Agent",
        payload={"output": "x"},
        override_approval_id=ticket.approval_id,
    )
    assert override_ticket is not None
    assert override_decision.action.value == "require_approval"
