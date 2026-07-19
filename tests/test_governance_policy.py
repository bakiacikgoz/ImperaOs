from __future__ import annotations

from pathlib import Path

from imperaos.governance.models import GovernanceAction
from imperaos.governance.policy import (
    evaluate_handoff,
    evaluate_memory_scope_write,
    evaluate_task,
    evaluate_tool,
    load_policy,
    normalize_command,
)


def test_default_policy_requires_approval_for_code_tasks() -> None:
    bundle = load_policy(Path("config/policies/default.toml"))
    match = evaluate_task(bundle.policy, task_type="code")

    assert match.action == GovernanceAction.REQUIRE_APPROVAL
    assert match.reason_code == "POLICY_REQUIRE_APPROVAL"


def test_tool_policy_blocks_destructive_python_args() -> None:
    bundle = load_policy(Path("config/policies/default.toml"))
    match = evaluate_tool(
        bundle.policy,
        command_root="python",
        args=["-c", "import os; os.remove('tmp.txt')"],
    )

    assert match.action == GovernanceAction.DENY
    assert match.reason_code == "POLICY_DENY"


def test_normalize_command_resolves_paths_against_workdir(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root, args = normalize_command(["python", "../outside.txt", "./inside.txt"], workdir=workspace)

    assert root == "python"
    assert args[0].endswith("outside.txt")
    assert args[1] == "./inside.txt"


def test_restricted_policy_requires_approval_for_execution_handoff() -> None:
    bundle = load_policy(Path("config/policies/restricted.toml"))
    match = evaluate_handoff(
        bundle.policy,
        from_role="Research Analyst Agent",
        to_role="Execution Agent",
    )

    assert match.action == GovernanceAction.REQUIRE_APPROVAL
    assert match.reason_code == "POLICY_REQUIRE_APPROVAL"


def test_restricted_policy_denies_unlisted_memory_scope_write() -> None:
    bundle = load_policy(Path("config/policies/restricted.toml"))
    match = evaluate_memory_scope_write(
        bundle.policy,
        scope="team",
        producer_role="Execution Agent",
        visibility="team",
    )

    assert match.action == GovernanceAction.DENY
    assert match.reason_code == "MEMORY_SCOPE_DENY"
