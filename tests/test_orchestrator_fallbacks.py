import time
from datetime import UTC, datetime, timedelta

from imperaos.core.llm_ollama import StubLLM
from imperaos.core.orchestrator import Orchestrator
from imperaos.core.planner import PlannerRun
from imperaos.experts.base import ExpertBase
from imperaos.governance.models import (
    ApprovalStatus,
    ApprovalTicket,
    GovernanceAction,
    GovernanceDecision,
    GovernancePhase,
)
from imperaos.router.rule_router import RuleRouter
from imperaos.runtime.config import RuntimeConfig, RuntimeLimits
from imperaos.schemas.models import (
    ExpertName,
    ExpertRequest,
    ExpertResult,
    ExpertStatus,
    PlannerOutput,
    ResponseMode,
    TaskType,
)
from imperaos.schemas.reason_codes import ReasonCode
from imperaos.telemetry.tracer import Tracer


class StaticPlanner:
    def __init__(self, output: PlannerOutput):
        self.output = output

    def plan(self, user_input: str) -> PlannerRun:
        del user_input
        return PlannerRun(
            output=self.output,
            raw_output="{}",
            parse_failed=False,
            error=None,
            elapsed_ms=1,
            reason_code=ReasonCode.PLANNER_OK,
        )


class SlowResearchExpert(ExpertBase):
    name = ExpertName.RESEARCH

    def run(self, request: ExpertRequest) -> ExpertResult:
        del request
        time.sleep(0.05)
        return ExpertResult(
            expert_name=self.name,
            status=ExpertStatus.OK,
            confidence=0.5,
            payload={
                "summary": "slow",
                "evidence": [],
                "citations": [],
                "uncertainty": 0.5,
            },
            elapsed_ms=50,
        )


class FastPlanExpert(ExpertBase):
    name = ExpertName.PLAN

    def run(self, request: ExpertRequest) -> ExpertResult:
        del request
        return ExpertResult(
            expert_name=self.name,
            status=ExpertStatus.OK,
            confidence=0.8,
            payload={
                "plan_steps": ["A", "B"],
                "state_summary": "ok",
                "memory_candidates": [],
                "confidence": 0.8,
            },
            elapsed_ms=1,
        )


class FailingExpert(ExpertBase):
    name = ExpertName.RESEARCH

    def __init__(self) -> None:
        self.calls = 0

    def run(self, request: ExpertRequest) -> ExpertResult:
        del request
        self.calls += 1
        raise RuntimeError("boom")


class MixedResearchExpert(ExpertBase):
    name = ExpertName.RESEARCH

    def run(self, request: ExpertRequest) -> ExpertResult:
        del request
        return ExpertResult(
            expert_name=self.name,
            status=ExpertStatus.OK,
            confidence=0.8,
            payload={
                "summary": "research_view",
                "evidence": ["e1"],
                "citations": [],
                "uncertainty": 0.2,
            },
            elapsed_ms=1,
        )


class MixedPlanExpert(ExpertBase):
    name = ExpertName.PLAN

    def run(self, request: ExpertRequest) -> ExpertResult:
        del request
        return ExpertResult(
            expert_name=self.name,
            status=ExpertStatus.OK,
            confidence=0.8,
            payload={
                "plan_steps": ["A", "B"],
                "state_summary": "plan_view",
                "memory_candidates": ["A"],
                "confidence": 0.8,
            },
            elapsed_ms=1,
        )


class GovernanceRuntimeStub:
    def __init__(self, action: GovernanceAction):
        self._action = action
        self.finalize_calls: list[str] = []

    def evaluate_task(  # noqa: PLR0913
        self,
        *,
        run_id: str,
        task_type: str,
        user_input: str,
        override_approval_id: str | None = None,
        execution_contract_hash: str | None = None,
        resume_token_ref: str | None = None,
    ):
        del user_input, override_approval_id, execution_contract_hash, resume_token_ref
        decision = GovernanceDecision(
            phase=GovernancePhase.TASK,
            target=task_type,
            action=self._action,
            reason_code=(
                "APPROVAL_REQUIRED"
                if self._action == GovernanceAction.REQUIRE_APPROVAL
                else "POLICY_DENY"
            ),
            matched_rule_path="rules.test",
            policy_schema_version="1",
            policy_version="test",
            policy_hash="policy-hash",
            decision_engine_version="test",
            approval_required=self._action == GovernanceAction.REQUIRE_APPROVAL,
            approval_id="approval-1" if self._action == GovernanceAction.REQUIRE_APPROVAL else None,
            explain="test decision",
        )
        if self._action == GovernanceAction.REQUIRE_APPROVAL:
            ticket = ApprovalTicket(
                version=1,
                approval_id="approval-1",
                run_id=run_id,
                status=ApprovalStatus.PENDING,
                target_kind="task",
                target_ref=task_type,
                action_hash="action-hash",
                policy_hash="policy-hash",
                request_hash="request-hash",
                snapshot_hash="snapshot-hash",
                snapshot={},
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
                idempotency_key="approval-1",
            )
            return decision, ticket
        return decision, None

    def finalize_run(
        self,
        *,
        run_id: str,
        router_reason_code: str,
        model_metadata: dict[str, object],
    ):
        del router_reason_code, model_metadata
        self.finalize_calls.append(run_id)
        return "audit.json"


def _config(timeout_ms: int = 10, threshold: int = 3, cooldown_s: int = 300) -> RuntimeConfig:
    limits = RuntimeLimits(
        expert_timeout_ms=timeout_ms,
        max_retries=0,
        circuit_breaker_threshold=threshold,
        circuit_breaker_cooldown_s=cooldown_s,
    )
    return RuntimeConfig(
        model_name="fake",
        profile_name="test",
        planner_temperature=0.0,
        answer_temperature=0.0,
        router_confidence_threshold=0.6,
        latency_budget_ms=1000,
        debug_mode=False,
        privacy_mode=True,
        enable_persistent_memory=False,
        web_enabled=False,
        trace_dir=".imperaos/test-traces",
        limits=limits,
    )


def test_orchestrator_timeout_uses_fallback_expert() -> None:
    planner_output = PlannerOutput(
        task_type=TaskType.RESEARCH,
        intent="research",
        needs_expert=True,
        expert_candidates=[ExpertName.RESEARCH, ExpertName.PLAN],
        confidence=0.95,
        latency_budget_ms=1000,
        can_fallback=True,
        response_mode=ResponseMode.TOOL_FIRST,
    )
    planner = StaticPlanner(planner_output)
    llm = StubLLM(responses=["final from llm"])
    router = RuleRouter(confidence_threshold=0.6)
    experts = {
        ExpertName.RESEARCH.value: SlowResearchExpert(),
        ExpertName.PLAN.value: FastPlanExpert(),
    }
    orchestrator = Orchestrator(
        planner=planner,
        llm=llm,
        router=router,
        experts=experts,
        tracer=Tracer(),
        config=_config(timeout_ms=10),
    )

    result = orchestrator.process("research this", use_router=True)

    assert result.used_path == "expert:plan_expert"
    assert any("fallback_expert_used:plan_expert" in item for item in result.fallback_events)


def test_orchestrator_opens_circuit_breaker_after_threshold() -> None:
    planner_output = PlannerOutput(
        task_type=TaskType.RESEARCH,
        intent="research",
        needs_expert=True,
        expert_candidates=[ExpertName.RESEARCH],
        confidence=0.95,
        latency_budget_ms=1000,
        can_fallback=True,
        response_mode=ResponseMode.TOOL_FIRST,
    )

    failing = FailingExpert()
    orchestrator = Orchestrator(
        planner=StaticPlanner(planner_output),
        llm=StubLLM(responses=["x", "x", "x", "x"]),
        router=RuleRouter(confidence_threshold=0.6),
        experts={ExpertName.RESEARCH.value: failing},
        tracer=Tracer(),
        config=_config(timeout_ms=100, threshold=3, cooldown_s=600),
    )

    for _ in range(3):
        orchestrator.process("test", use_router=True)

    fourth = orchestrator.process("test", use_router=True)

    assert failing.calls == 3
    assert "CB_OPEN" in fourth.fallback_events
    assert fourth.metrics["router_reason_code"] == "CB_OPEN"


def test_orchestrator_adjudicates_mixed_expert_outputs() -> None:
    planner_output = PlannerOutput(
        task_type=TaskType.MIXED,
        intent="mixed",
        needs_expert=True,
        expert_candidates=[ExpertName.RESEARCH, ExpertName.PLAN],
        confidence=0.95,
        latency_budget_ms=1000,
        can_fallback=True,
        response_mode=ResponseMode.TOOL_FIRST,
    )

    orchestrator = Orchestrator(
        planner=StaticPlanner(planner_output),
        llm=StubLLM(responses=["adjudicated-final"]),
        router=RuleRouter(confidence_threshold=0.6),
        experts={
            ExpertName.RESEARCH.value: MixedResearchExpert(),
            ExpertName.PLAN.value: MixedPlanExpert(),
        },
        tracer=Tracer(),
        config=_config(timeout_ms=100),
    )

    result = orchestrator.process("mixed request", use_router=True)

    assert result.final_text == "adjudicated-final"
    assert result.used_path == "expert_adjudicated:research_expert+plan_expert"
    assert "expert_adjudication" in result.fallback_events


def test_governance_pending_uses_governance_run_id_without_name_error() -> None:
    planner_output = PlannerOutput(
        task_type=TaskType.RESEARCH,
        intent="research",
        needs_expert=True,
        expert_candidates=[ExpertName.RESEARCH],
        confidence=0.95,
        latency_budget_ms=1000,
        can_fallback=True,
        response_mode=ResponseMode.TOOL_FIRST,
    )
    governance = GovernanceRuntimeStub(GovernanceAction.REQUIRE_APPROVAL)
    orchestrator = Orchestrator(
        planner=StaticPlanner(planner_output),
        llm=StubLLM(responses=["x"]),
        router=RuleRouter(confidence_threshold=0.6),
        experts={ExpertName.RESEARCH.value: MixedResearchExpert()},
        tracer=Tracer(),
        config=_config(timeout_ms=100),
        governance_runtime=governance,
    )

    result = orchestrator.process(
        "needs approval",
        session_context={"governance_run_id": "task-run-1"},
        use_router=True,
    )

    assert result.used_path == "governance_pending"
    assert governance.finalize_calls == ["task-run-1"]
    assert result.metrics["approval_id"] == "approval-1"
    assert "needs approval" not in result.final_text
    assert "Approval ID: approval-1" in result.final_text


def test_governance_blocked_uses_governance_run_id_without_name_error() -> None:
    planner_output = PlannerOutput(
        task_type=TaskType.RESEARCH,
        intent="research",
        needs_expert=True,
        expert_candidates=[ExpertName.RESEARCH],
        confidence=0.95,
        latency_budget_ms=1000,
        can_fallback=True,
        response_mode=ResponseMode.TOOL_FIRST,
    )
    governance = GovernanceRuntimeStub(GovernanceAction.DENY)
    orchestrator = Orchestrator(
        planner=StaticPlanner(planner_output),
        llm=StubLLM(responses=["x"]),
        router=RuleRouter(confidence_threshold=0.6),
        experts={ExpertName.RESEARCH.value: MixedResearchExpert()},
        tracer=Tracer(),
        config=_config(timeout_ms=100),
        governance_runtime=governance,
    )

    result = orchestrator.process(
        "denied request",
        session_context={"governance_run_id": "task-run-2"},
        use_router=True,
    )

    assert result.used_path == "governance_blocked"
    assert governance.finalize_calls == ["task-run-2"]
    assert result.metrics["governance_reason_code"] == "POLICY_DENY"
