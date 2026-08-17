from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from imperaos.governance.models import GovernanceAction
from imperaos.governance.runtime import GovernanceRuntime
from imperaos.runtime.allowlist import is_allowed_command


@dataclass(slots=True)
class SandboxResult:
    command: list[str]
    allowed: bool
    exit_code: int
    stdout: str
    stderr: str


class SandboxRunner:
    def __init__(
        self,
        *,
        workdir: str | Path = ".",
        timeout_s: float = 8.0,
        governance_runtime: GovernanceRuntime | None = None,
        governance_run_id: str | None = None,
    ):
        self.workdir = Path(workdir)
        self.timeout_s = timeout_s
        self.governance_runtime = governance_runtime
        self.governance_run_id = governance_run_id

    def run(self, command: list[str]) -> SandboxResult:
        if self.governance_runtime is not None and self.governance_run_id is not None:
            decision, approval_ticket, _normalized_args = (
                self.governance_runtime.evaluate_tool_command(
                    run_id=self.governance_run_id,
                    command=command,
                    workdir=self.workdir,
                )
            )
            if decision.action == GovernanceAction.DENY:
                return SandboxResult(
                    command=command,
                    allowed=False,
                    exit_code=126,
                    stdout="",
                    stderr=f"command denied by governance policy ({decision.reason_code})",
                )
            if decision.action == GovernanceAction.REQUIRE_APPROVAL:
                approval_id = approval_ticket.approval_id if approval_ticket else "unknown"
                return SandboxResult(
                    command=command,
                    allowed=False,
                    exit_code=125,
                    stdout="",
                    stderr=f"command requires approval (approval_id={approval_id})",
                )

        if not is_allowed_command(command):
            return SandboxResult(
                command=command,
                allowed=False,
                exit_code=126,
                stdout="",
                stderr="command is not in allowlist",
            )

        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                cwd=str(self.workdir),
                timeout=self.timeout_s,
            )
            return SandboxResult(
                command=command,
                allowed=True,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        except FileNotFoundError:
            return SandboxResult(
                command=command,
                allowed=True,
                exit_code=127,
                stdout="",
                stderr="command not found",
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                command=command,
                allowed=True,
                exit_code=124,
                stdout="",
                stderr="command timed out",
            )
