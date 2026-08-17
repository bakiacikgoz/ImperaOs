from __future__ import annotations

from imperaos.governance.approval_executors.base import PreflightOutcome


class ExternalAgentApprovalExecutor:
    """Fail-closed until a configured gateway can prove idempotent result lookup."""

    kind = "external_agent_action"

    def preflight(self, ticket, snapshot) -> PreflightOutcome:
        return PreflightOutcome(False, "EXTERNAL_AGENT_IDEMPOTENT_GATEWAY_REQUIRED")

    def execute(self, ticket, snapshot, attempt_id):  # pragma: no cover - blocked by preflight
        raise RuntimeError("external-agent execution is unavailable without an idempotent gateway")
