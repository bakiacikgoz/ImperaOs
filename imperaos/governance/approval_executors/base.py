from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from imperaos.governance.approval_snapshots import ApprovalSnapshot
from imperaos.governance.models import ApprovalTicket


@dataclass(frozen=True, slots=True)
class PreflightOutcome:
    allowed: bool
    reason_code: str = "OK"


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    result: dict[str, Any] = field(default_factory=dict)
    result_hash: str = ""


class ApprovalExecutor(Protocol):
    kind: str

    def preflight(self, ticket: ApprovalTicket, snapshot: ApprovalSnapshot) -> PreflightOutcome: ...

    def execute(
        self, ticket: ApprovalTicket, snapshot: ApprovalSnapshot, attempt_id: str
    ) -> ExecutionOutcome: ...
