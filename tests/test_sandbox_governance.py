from __future__ import annotations

from pathlib import Path

from imperaos.governance.runtime import GovernanceRuntime
from imperaos.runtime.config import RuntimeConfig
from imperaos.tools.sandbox_runner import SandboxRunner

CUSTOM_POLICY = """
policy_schema_version = "1.0"
policy_version = "custom-approval"
web_egress = "deny"

[[task_rules]]
id = "chat"
task_types = ["chat"]
action = "allow"

[[tool_rules]]
id = "python-approval"
command_roots = ["python"]
action = "require_approval"
arg_deny_regex = []

[pii_rules]
patterns = []
"""


def _runtime(tmp_path: Path, policy_path: str) -> GovernanceRuntime:
    cfg = RuntimeConfig.from_profile("default")
    cfg = cfg.model_copy(
        update={
            "governance": cfg.governance.model_copy(
                update={
                    "policy_path": policy_path,
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            )
        }
    )
    return GovernanceRuntime(config=cfg)


def test_sandbox_runner_blocks_destructive_command_with_default_policy(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, "config/policies/default.toml")
    runner = SandboxRunner(
        workdir=tmp_path,
        governance_runtime=runtime,
        governance_run_id="run-sandbox",
    )

    result = runner.run(["python", "-c", "import os; os.remove('x')"])
    assert result.allowed is False
    assert result.exit_code == 126


def test_sandbox_runner_creates_approval_ticket_when_policy_requires(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.toml"
    policy_path.write_text(CUSTOM_POLICY, encoding="utf-8")

    runtime = _runtime(tmp_path, str(policy_path))
    runner = SandboxRunner(
        workdir=tmp_path,
        governance_runtime=runtime,
        governance_run_id="run-sandbox-approval",
    )

    result = runner.run(["python", "-c", "print('ok')"])
    assert result.allowed is False
    assert result.exit_code == 125
    assert "approval_id" in result.stderr
    assert len(runtime.approval_store.list_pending(workspace_id="default")) == 1
