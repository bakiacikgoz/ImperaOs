from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.models import (
    ActionProposal,
    AgentSpec,
    ControlPlaneDecisionAction,
    ControlPlanePolicyDecision,
    PolicySimulationResult,
    PolicySimulationSummary,
    RiskClass,
)
from imperaos.control_plane.storage import file_sha256
from imperaos.runtime.config import RuntimeConfig


class PolicySimulator:
    def __init__(self, *, config: RuntimeConfig):
        self.config = config

    @property
    def policy_hash(self) -> str:
        if not self.config.governance.enabled:
            return "sha256:governance-disabled"
        policy_path = Path(self.config.governance.policy_path)
        if not policy_path.exists():
            return "unavailable"
        return f"sha256:{file_sha256(policy_path)}"

    @property
    def policy_available(self) -> bool:
        return not self.config.governance.enabled or self.policy_hash != "unavailable"

    def simulate_agent(self, spec: AgentSpec) -> PolicySimulationResult:
        policy_hash = self.policy_hash
        blocking_reasons: list[str] = []
        decisions: list[ControlPlanePolicyDecision] = []
        if policy_hash == "unavailable":
            blocking_reasons.append("POLICY_UNAVAILABLE")

        for action in spec.declared_actions:
            decision = self._decision_for_risk(
                action_id=action.action_id,
                phase=action.phase,
                risk_class=action.risk_class,
                policy_hash=policy_hash,
            )
            decisions.append(decision)
            if decision.decision_action == ControlPlaneDecisionAction.DENY:
                blocking_reasons.append(decision.reason_code)

        summary = PolicySimulationSummary(
            allow=sum(1 for item in decisions if item.decision_action == "allow"),
            require_approval=sum(
                1 for item in decisions if item.decision_action == "require_approval"
            ),
            deny=sum(1 for item in decisions if item.decision_action == "deny"),
            unknown=sum(1 for item in decisions if item.decision_action == "unknown"),
        )
        if blocking_reasons:
            overall_status = "blocked"
        elif summary.require_approval:
            overall_status = "conditional"
        else:
            overall_status = "pass"
        return PolicySimulationResult(
            agent_id=spec.agent_id,
            policy_hash=policy_hash,
            overall_status=overall_status,
            summary=summary,
            decisions=decisions,
            blocking_reasons=sorted(set(blocking_reasons)),
        )

    def simulate_action(self, proposal: ActionProposal) -> ControlPlanePolicyDecision:
        return self._decision_for_risk(
            action_id=proposal.action_id,
            phase=proposal.phase,
            risk_class=proposal.risk_class,
            policy_hash=self.policy_hash,
        )

    def _decision_for_risk(
        self,
        *,
        action_id: str,
        phase: str,
        risk_class: RiskClass,
        policy_hash: str,
    ) -> ControlPlanePolicyDecision:
        risk_value = str(risk_class)
        if policy_hash == "unavailable":
            return ControlPlanePolicyDecision(
                action_id=action_id,
                phase=phase,
                risk_class=risk_class,
                decision_action=ControlPlaneDecisionAction.DENY,
                reason_code="POLICY_UNAVAILABLE",
                matched_rule_path="control_plane.policy_available",
                policy_hash=policy_hash,
            )

        if risk_class == RiskClass.READ_ONLY:
            action = ControlPlaneDecisionAction.ALLOW
            reason = "RISK_READ_ONLY_ALLOWED"
            path = "risk_defaults[read_only]"
        elif risk_class in {
            RiskClass.LOCAL_WRITE,
            RiskClass.EXTERNAL_WRITE,
            RiskClass.MUTATION,
        }:
            action = ControlPlaneDecisionAction.REQUIRE_APPROVAL
            reason = "RISK_REQUIRES_APPROVAL"
            path = f"risk_defaults[{risk_value}]"
        elif risk_class == RiskClass.COMPUTER_USE_VISUAL:
            action = ControlPlaneDecisionAction.REQUIRE_APPROVAL
            reason = "COMPUTER_USE_REQUIRES_QUALIFICATION"
            path = "risk_defaults[computer_use_visual]"
        else:
            action = ControlPlaneDecisionAction.DENY
            reason = "UNKNOWN_RISK_DENIED" if risk_class == RiskClass.UNKNOWN else "RISK_DENIED"
            path = f"risk_defaults[{risk_value}]"

        return ControlPlanePolicyDecision(
            action_id=action_id,
            phase=phase,
            risk_class=risk_class,
            decision_action=action,
            reason_code=reason,
            matched_rule_path=path,
            policy_hash=policy_hash,
            qualification_required=risk_class == RiskClass.COMPUTER_USE_VISUAL,
        )
