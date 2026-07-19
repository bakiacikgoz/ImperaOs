from __future__ import annotations

import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from pydantic import ValidationError

from imperaos.core.llm_ollama import LLMClient
from imperaos.core.planner import Planner
from imperaos.experts.base import ExpertBase
from imperaos.governance.models import GovernanceAction, GovernanceDecision
from imperaos.governance.runtime import GovernanceRuntime
from imperaos.memory.context_pack import MemoryContextPack, empty_context_pack
from imperaos.memory.manager import MemoryManager
from imperaos.memory.prompt_injector import MemoryPromptInjector
from imperaos.memory.runtime_bridge import MemoryRuntimeBridge, RuntimeMemoryRequest
from imperaos.runtime.config import RuntimeConfig
from imperaos.schemas.expert_payloads import (
    CodeExpertPayload,
    PlanExpertPayload,
    ResearchExpertPayload,
)
from imperaos.schemas.models import (
    ExpertName,
    ExpertRequest,
    ExpertResult,
    ExpertStatus,
    OrchestratorResult,
    PlannerOutput,
    RouterDecision,
    TaskType,
)
from imperaos.schemas.reason_codes import ReasonCode
from imperaos.telemetry.tracer import Tracer


class RouterLike(Protocol):
    def decide(self, planner_output: PlannerOutput) -> RouterDecision:
        ...


@dataclass(slots=True)
class CircuitBreaker:
    threshold: int
    cooldown_s: int
    failures: dict[ExpertName, int] = field(default_factory=dict)
    open_until: dict[ExpertName, float] = field(default_factory=dict)

    def is_open(self, expert_name: ExpertName) -> bool:
        until = self.open_until.get(expert_name)
        return until is not None and time.monotonic() < until

    def record_failure(self, expert_name: ExpertName) -> None:
        if self.is_open(expert_name):
            return

        current = self.failures.get(expert_name, 0) + 1
        if current >= self.threshold:
            self.open_until[expert_name] = time.monotonic() + self.cooldown_s
            self.failures[expert_name] = 0
            return

        self.failures[expert_name] = current

    def record_success(self, expert_name: ExpertName) -> None:
        self.failures[expert_name] = 0


class Orchestrator:
    def __init__(
        self,
        planner: Planner,
        llm: LLMClient,
        router: RouterLike,
        experts: dict[str, ExpertBase],
        tracer: Tracer,
        config: RuntimeConfig,
        memory_manager: MemoryManager | None = None,
        memory_runtime_bridge: MemoryRuntimeBridge | None = None,
        shadow_router: RouterLike | None = None,
        governance_runtime: GovernanceRuntime | None = None,
    ):
        self._planner = planner
        self._llm = llm
        self._router = router
        self._shadow_router = shadow_router
        self._experts = experts
        self._tracer = tracer
        self._config = config
        self._memory_manager = memory_manager
        self._memory_runtime_bridge = memory_runtime_bridge
        self._governance_runtime = governance_runtime
        self._fast_path_sessions: dict[str, dict[str, int]] = {}
        self._expert_payload_models = {
            ExpertName.CODE: CodeExpertPayload,
            ExpertName.RESEARCH: ResearchExpertPayload,
            ExpertName.PLAN: PlanExpertPayload,
        }
        self._breaker = CircuitBreaker(
            threshold=config.limits.circuit_breaker_threshold,
            cooldown_s=config.limits.circuit_breaker_cooldown_s,
        )

    @property
    def governance_runtime(self) -> GovernanceRuntime | None:
        return self._governance_runtime

    @property
    def llm(self) -> LLMClient:
        return self._llm

    def process(
        self,
        user_input: str,
        session_context: dict[str, str] | None = None,
        use_router: bool = True,
    ) -> OrchestratorResult:
        started_total = time.perf_counter()
        request_id = str(uuid4())
        session_context = session_context or {}
        governance_run_id = str(session_context.get("governance_run_id") or request_id)
        requested_model_metadata = self._requested_model_metadata(session_context)
        fallback_events: list[str] = []
        expert_latency_ms = 0
        tool_budget_state = {"used": int(session_context.get("tool_calls_used", 0))}
        session_id = str(session_context.get("session_id", request_id))
        session_state = self._ensure_session_state(session_id)
        session_state["turn"] += 1

        recursion_depth = int(session_context.get("_depth", 0))
        if recursion_depth >= self._config.limits.max_recursion_depth:
            fallback_events.append("recursion_depth_exceeded")
            final_text = self._safe_fallback_text(user_input, "max recursion depth exceeded")
            return OrchestratorResult(
                final_text=final_text,
                used_path="llm_only",
                fallback_events=fallback_events,
                trace_id=request_id,
                metrics={
                    "router_reason_code": ReasonCode.RECURSION_DEPTH_EXCEEDED.value,
                    "total_latency_ms": int((time.perf_counter() - started_total) * 1000),
                    "fast_path_regret_flag": False,
                    "followup_correction_rate": self._followup_correction_rate(session_state),
                },
            )

        self._tracer.emit(request_id, "request_received", {"input": user_input})

        planner_run = self._planner.plan(user_input)
        planner_output = planner_run.output
        self._tracer.emit(
            request_id,
            "planner_output",
            {
                "parse_failed": planner_run.parse_failed,
                "error": planner_run.error,
                "reason_code": planner_run.reason_code.value,
                "output": planner_output.model_dump(mode="json"),
            },
        )
        if planner_run.parse_failed:
            fallback_events.append("planner_parse_fallback")

        governance_decision: GovernanceDecision | None = None
        if self._governance_runtime is not None:
            governance_decision, approval_ticket = self._governance_runtime.evaluate_task(
                run_id=governance_run_id,
                task_type=planner_output.task_type.value,
                user_input=user_input,
                override_approval_id=session_context.get("governance_approval_id"),
                execution_contract_hash=session_context.get("governance_execution_contract_hash"),
                resume_token_ref=session_context.get("governance_resume_token_ref"),
                **(
                    {"workspace_id": session_context["governance_workspace_id"]}
                    if session_context.get("governance_workspace_id")
                    else {}
                ),
            )
            self._tracer.emit(
                request_id,
                "policy_decision",
                governance_decision.model_dump(mode="json"),
            )
            if governance_decision.action == GovernanceAction.DENY:
                fallback_events.append("policy_denied")
                return self._blocked_result(
                    request_id=request_id,
                    started_total=started_total,
                    user_input=user_input,
                    reason_code=governance_decision.reason_code,
                    fallback_events=fallback_events,
                    governance_decision=governance_decision,
                    governance_run_id=governance_run_id,
                    requested_model_metadata=requested_model_metadata,
                )
            if governance_decision.action == GovernanceAction.REQUIRE_APPROVAL:
                fallback_events.append("approval_pending")
                self._tracer.emit(
                    request_id,
                    "approval_pending",
                    {
                        "approval_id": approval_ticket.approval_id if approval_ticket else None,
                        "run_id": request_id,
                        "task_type": planner_output.task_type.value,
                    },
                )
                return self._pending_result(
                    request_id=request_id,
                    started_total=started_total,
                    user_input=user_input,
                    fallback_events=fallback_events,
                    governance_decision=governance_decision,
                    approval_id=approval_ticket.approval_id if approval_ticket else None,
                    governance_run_id=governance_run_id,
                    requested_model_metadata=requested_model_metadata,
                )

        if use_router:
            routing_started = time.perf_counter()
            route = self._router.decide(planner_output)
            routing_elapsed = int((time.perf_counter() - routing_started) * 1000)
        else:
            route = RouterDecision(
                selected_expert=ExpertName.LLM_ONLY,
                selection_confidence=planner_output.confidence,
                estimated_cost=0.1,
                estimated_latency_ms=planner_output.latency_budget_ms,
                fallback_expert=None,
                reason_code=ReasonCode.BASELINE_A,
            )
            routing_elapsed = 0
        effective_reason_code = route.reason_code
        self._tracer.emit(request_id, "router_decision", route.model_dump(mode="json"))
        shadow_decision = None
        if use_router and self._shadow_router is not None:
            shadow_decision = self._shadow_router.decide(planner_output)
            agreement = shadow_decision.selected_expert == route.selected_expert
            disagreement_bucket = (
                "agree"
                if agreement
                else f"{route.selected_expert.value}->{shadow_decision.selected_expert.value}"
            )
            self._tracer.emit(
                request_id,
                "router_shadow_decision",
                {
                    "active_router_choice": route.selected_expert.value,
                    "shadow_router_choice": shadow_decision.selected_expert.value,
                    "agreement": agreement,
                    "disagreement_bucket": disagreement_bucket,
                },
            )

        memory_context_pack = self._retrieve_memory_context(
            request_id=request_id,
            user_input=user_input,
            session_context=session_context,
            requester_role="orchestrator",
        )
        memory_prompt_section = MemoryPromptInjector.build_section(
            memory_context_pack,
            max_chars=self._config.memory.runtime.max_context_chars,
        )
        selected_result: ExpertResult | None = None
        secondary_result: ExpertResult | None = None
        used_path = "llm_only"
        expert_needed_after_fast_path = self._is_expert_needed_after_fast_path(
            session_state=session_state,
            planner_output=planner_output,
        )
        fast_path_regret_flag = expert_needed_after_fast_path
        if fast_path_regret_flag:
            session_state["regret_count"] += 1
        followup_rate = self._followup_correction_rate(session_state)
        if followup_rate >= self._config.fast_path_regret_threshold:
            fast_path_regret_flag = True

        if (
            use_router
            and route.selected_expert != ExpertName.LLM_ONLY
            and planner_output.needs_expert
        ):
            if route.selection_confidence < self._config.router_confidence_threshold:
                fallback_events.append("router_low_confidence")
                effective_reason_code = ReasonCode.LOW_CONFIDENCE_GATE
            elif self._breaker.is_open(route.selected_expert):
                fallback_events.append("CB_OPEN")
                effective_reason_code = ReasonCode.CB_OPEN
                self._tracer.emit(
                    request_id,
                    "router_decision_override",
                    {
                        "reason_code": ReasonCode.CB_OPEN.value,
                        "expert": route.selected_expert.value,
                    },
                )
            else:
                selected_result = self._run_expert_with_retries(
                    request_id=request_id,
                    planner_output=planner_output,
                    expert_name=route.selected_expert,
                    user_input=user_input,
                    session_context=session_context,
                    tool_budget_state=tool_budget_state,
                )
                expert_latency_ms += selected_result.elapsed_ms

                if selected_result.status == ExpertStatus.OK:
                    self._breaker.record_success(route.selected_expert)
                    self._update_router_feedback(
                        expert_name=route.selected_expert,
                        status=selected_result.status,
                        elapsed_ms=selected_result.elapsed_ms,
                    )
                    used_path = f"expert:{route.selected_expert.value}"
                else:
                    self._breaker.record_failure(route.selected_expert)
                    self._update_router_feedback(
                        expert_name=route.selected_expert,
                        status=selected_result.status,
                        elapsed_ms=selected_result.elapsed_ms,
                    )
                    fallback_events.append(
                        f"expert_failed:{route.selected_expert.value}:{selected_result.status.value}"
                    )

                if selected_result.status != ExpertStatus.OK and route.fallback_expert:
                    if self._breaker.is_open(route.fallback_expert):
                        fallback_events.append("CB_OPEN_FALLBACK")
                    else:
                        fallback = self._run_expert_with_retries(
                            request_id=request_id,
                            planner_output=planner_output,
                            expert_name=route.fallback_expert,
                            user_input=user_input,
                            session_context=session_context,
                            tool_budget_state=tool_budget_state,
                        )
                        expert_latency_ms += fallback.elapsed_ms
                        if fallback.status == ExpertStatus.OK:
                            self._breaker.record_success(route.fallback_expert)
                            self._update_router_feedback(
                                expert_name=route.fallback_expert,
                                status=fallback.status,
                                elapsed_ms=fallback.elapsed_ms,
                            )
                            selected_result = fallback
                            used_path = f"expert:{route.fallback_expert.value}"
                            fallback_events.append(f"fallback_expert_used:{route.fallback_expert.value}")
                        else:
                            self._breaker.record_failure(route.fallback_expert)
                            self._update_router_feedback(
                                expert_name=route.fallback_expert,
                                status=fallback.status,
                                elapsed_ms=fallback.elapsed_ms,
                            )
                            fallback_events.append(
                                f"fallback_expert_failed:{route.fallback_expert.value}:{fallback.status.value}"
                            )
                elif planner_output.task_type == TaskType.MIXED and route.fallback_expert:
                    secondary_result = self._run_expert_with_retries(
                        request_id=request_id,
                        planner_output=planner_output,
                        expert_name=route.fallback_expert,
                        user_input=user_input,
                        session_context=session_context,
                        tool_budget_state=tool_budget_state,
                    )
                    expert_latency_ms += secondary_result.elapsed_ms
                    if secondary_result.status == ExpertStatus.OK:
                        self._breaker.record_success(route.fallback_expert)
                        self._update_router_feedback(
                            expert_name=route.fallback_expert,
                            status=secondary_result.status,
                            elapsed_ms=secondary_result.elapsed_ms,
                        )
                        fallback_events.append(f"secondary_expert_used:{route.fallback_expert.value}")
                    else:
                        self._breaker.record_failure(route.fallback_expert)
                        self._update_router_feedback(
                            expert_name=route.fallback_expert,
                            status=secondary_result.status,
                            elapsed_ms=secondary_result.elapsed_ms,
                        )
                        fallback_events.append(
                            f"secondary_expert_failed:{route.fallback_expert.value}:{secondary_result.status.value}"
                        )

        llm_started = time.perf_counter()
        llm_error: str | None = None
        if selected_result and selected_result.status == ExpertStatus.OK:
            if (
                secondary_result
                and secondary_result.status == ExpertStatus.OK
                and secondary_result.payload != selected_result.payload
            ):
                adjudication_prompt = self._build_adjudication_prompt(
                    user_input=user_input,
                    primary=selected_result,
                    secondary=secondary_result,
                )
                try:
                    final_text = self._generate_with_timeout(
                        prompt=adjudication_prompt,
                        system=None,
                    )
                except Exception as exc:  # noqa: BLE001
                    llm_error = str(exc)
                    final_text = self._safe_fallback_text(user_input, llm_error)
                used_path = (
                    "expert_adjudicated:"
                    f"{selected_result.expert_name.value}+{secondary_result.expert_name.value}"
                )
                fallback_events.append("expert_adjudication")
            else:
                synthesis_prompt = self._build_synthesis_prompt(
                    user_input,
                    selected_result,
                    memory_section=memory_prompt_section,
                )
                try:
                    final_text = self._generate_with_timeout(
                        prompt=synthesis_prompt,
                        system=None,
                    )
                except Exception as exc:  # noqa: BLE001
                    llm_error = str(exc)
                    final_text = self._safe_fallback_text(user_input, llm_error)
        else:
            try:
                language_instruction = self._language_instruction(user_input)
                prompt_pieces = []
                if memory_prompt_section:
                    prompt_pieces.append(memory_prompt_section)
                prompt_pieces.extend(
                    [
                        f"User request: {user_input}",
                        "Respond concisely and clearly.",
                        language_instruction,
                    ]
                )
                final_text = self._generate_with_timeout(
                    prompt="\n\n".join(prompt_pieces),
                    system="You are ImperaOS assistant in product mode.",
                )
            except Exception as exc:  # noqa: BLE001
                llm_error = str(exc)
                final_text = self._safe_fallback_text(user_input, llm_error)
            if use_router and route.selected_expert != ExpertName.LLM_ONLY:
                fallback_events.append("llm_only_synthesis")
        llm_elapsed = int((time.perf_counter() - llm_started) * 1000)

        memory_write = self._maybe_write_memory(
            request_id=request_id,
            session_id=session_id,
            task_type=str(planner_output.task_type),
            user_input=user_input,
            assistant_output=final_text,
            expert_payload=selected_result.payload if selected_result else None,
        )
        code_metrics = self._extract_code_verification_metrics(selected_result)

        total_elapsed = int((time.perf_counter() - started_total) * 1000)
        run_model_metadata = self._resolve_run_model_metadata(
            requested_model_metadata=requested_model_metadata,
            selected_provider=self._selected_provider_from_llm(),
        )
        metrics = {
            "planner_latency_ms": planner_run.elapsed_ms,
            "routing_latency_ms": routing_elapsed,
            "expert_latency_ms": expert_latency_ms,
            "llm_latency_ms": llm_elapsed,
            "total_latency_ms": total_elapsed,
            "planner_parse_failed": planner_run.parse_failed,
            "planner_reason_code": planner_run.reason_code.value,
            "planner_repair_applied": planner_run.reason_code == ReasonCode.PLANNER_REPAIR_APPLIED,
            "planner_repair_success": (
                planner_run.reason_code == ReasonCode.PLANNER_REPAIR_APPLIED
                and not planner_run.parse_failed
            ),
            "planner_schema_invalid": planner_run.reason_code == ReasonCode.PLANNER_SCHEMA_INVALID,
            "router_reason_code": effective_reason_code.value,
            "route_selected_expert": route.selected_expert.value,
            "memory_written": memory_write["written"],
            "memory_salience_score": memory_write["salience_score"],
            **self._memory_context_metrics(memory_context_pack),
            "memory_write_decision": memory_write["reason"],
            "llm_error": llm_error,
            "tool_calls_used": tool_budget_state["used"],
            "fast_path_taken": False,
            "fast_path_candidate_reason": "none",
            "fast_path_regret_flag": fast_path_regret_flag,
            "expert_needed_after_fast_path": expert_needed_after_fast_path,
            "followup_correction_rate": followup_rate,
            "active_router_choice": route.selected_expert.value,
            "shadow_router_choice": (
                shadow_decision.selected_expert.value if shadow_decision is not None else None
            ),
            "router_shadow_agreement": (
                shadow_decision.selected_expert == route.selected_expert
                if shadow_decision is not None
                else None
            ),
            "router_shadow_enabled": shadow_decision is not None,
            "expert_schema_invalid": (
                selected_result is not None
                and selected_result.error_code == ReasonCode.EXPERT_SCHEMA_INVALID.value
            ),
            "code_verification_stage_reached": code_metrics["stage_reached"],
            "code_retry_count": code_metrics["retry_count"],
            "code_failure_reason": code_metrics["failure_reason"],
            "governance_action": governance_decision.action.value if governance_decision else None,
            "governance_reason_code": (
                governance_decision.reason_code if governance_decision else None
            ),
            "policy_hash": governance_decision.policy_hash if governance_decision else None,
            "requested_provider": run_model_metadata["requested_provider"],
            "requested_fallback_provider": run_model_metadata["requested_fallback_provider"],
            "requested_model_name": run_model_metadata["requested_model_name"],
            "requested_hf_model_id": run_model_metadata["requested_hf_model_id"],
            "selected_provider": run_model_metadata["selected_provider"],
            "selected_model_name": run_model_metadata["selected_model_name"],
            "selected_hf_model_id": run_model_metadata["selected_hf_model_id"],
            "fallback_used": run_model_metadata["fallback_used"],
            "config_source_model_name": run_model_metadata["config_source_model_name"],
            "config_source_hf_model_id": run_model_metadata["config_source_hf_model_id"],
        }

        audit_artifact_path = None
        if self._governance_runtime is not None:
            audit_artifact_path = self._governance_runtime.finalize_run(
                run_id=request_id,
                router_reason_code=effective_reason_code.value,
                model_metadata=run_model_metadata,
            )
            if audit_artifact_path:
                self._tracer.emit(
                    request_id,
                    "audit_artifact",
                    {"path": audit_artifact_path},
                )
        metrics["audit_artifact_path"] = audit_artifact_path

        self._tracer.emit(
            request_id,
            "final_response",
            {"used_path": used_path, "metrics": metrics},
        )
        self._tracer.emit_router_sample(
            {
                "request_id": request_id,
                "task_type": planner_output.task_type.value,
                "planner_confidence": planner_output.confidence,
                "router_selected_expert": route.selected_expert.value,
                "router_reason_code": effective_reason_code.value,
                "used_path": used_path,
                "success": bool(final_text.strip()),
                "total_latency_ms": total_elapsed,
                "active_router_choice": route.selected_expert.value,
                "shadow_router_choice": (
                    shadow_decision.selected_expert.value if shadow_decision else None
                ),
                "shadow_agreement": (
                    bool(shadow_decision.selected_expert == route.selected_expert)
                    if shadow_decision
                    else None
                ),
                "fast_path_taken": False,
                "fast_path_regret_flag": fast_path_regret_flag,
                "code_verification_stage_reached": code_metrics["stage_reached"],
                "code_retry_count": code_metrics["retry_count"],
                "code_failure_reason": code_metrics["failure_reason"],
            }
        )
        return OrchestratorResult(
            final_text=final_text,
            used_path=used_path,
            fallback_events=fallback_events,
            trace_id=request_id,
            metrics=metrics,
        )

    def process_fast_chat(
        self,
        user_input: str,
        session_context: dict[str, str] | None = None,
        *,
        stream: bool = False,
        candidate_reason: str = "short_message",
        on_token: Callable[[str], None] | None = None,
    ) -> OrchestratorResult:
        started_total = time.perf_counter()
        request_id = str(uuid4())
        session_context = session_context or {}
        governance_run_id = str(session_context.get("governance_run_id") or request_id)
        requested_model_metadata = self._requested_model_metadata(session_context)
        session_id = str(session_context.get("session_id", request_id))
        session_state = self._ensure_session_state(session_id)
        session_state["turn"] += 1
        session_state["fast_path_count"] += 1
        session_state["last_fast_path_turn"] = session_state["turn"]
        fallback_events: list[str] = []

        self._tracer.emit(
            request_id,
            "request_received",
            {"input": user_input, "fast_path": True, "stream": stream},
        )

        governance_decision: GovernanceDecision | None = None
        if self._governance_runtime is not None:
            governance_decision, approval_ticket = self._governance_runtime.evaluate_task(
                run_id=governance_run_id,
                task_type=TaskType.CHAT.value,
                user_input=user_input,
                override_approval_id=session_context.get("governance_approval_id"),
                execution_contract_hash=session_context.get("governance_execution_contract_hash"),
                resume_token_ref=session_context.get("governance_resume_token_ref"),
                **(
                    {"workspace_id": session_context["governance_workspace_id"]}
                    if session_context.get("governance_workspace_id")
                    else {}
                ),
            )
            self._tracer.emit(
                request_id,
                "policy_decision",
                governance_decision.model_dump(mode="json"),
            )
            if governance_decision.action == GovernanceAction.DENY:
                fallback_events.append("policy_denied")
                return self._blocked_result(
                    request_id=request_id,
                    started_total=started_total,
                    user_input=user_input,
                    reason_code=governance_decision.reason_code,
                    fallback_events=fallback_events,
                    governance_decision=governance_decision,
                    governance_run_id=governance_run_id,
                    requested_model_metadata=requested_model_metadata,
                )
            if governance_decision.action == GovernanceAction.REQUIRE_APPROVAL:
                fallback_events.append("approval_pending")
                self._tracer.emit(
                    request_id,
                    "approval_pending",
                    {
                        "approval_id": approval_ticket.approval_id if approval_ticket else None,
                        "run_id": governance_run_id,
                        "task_type": TaskType.CHAT.value,
                    },
                )
                return self._pending_result(
                    request_id=request_id,
                    started_total=started_total,
                    user_input=user_input,
                    fallback_events=fallback_events,
                    governance_decision=governance_decision,
                    approval_id=approval_ticket.approval_id if approval_ticket else None,
                    governance_run_id=governance_run_id,
                    requested_model_metadata=requested_model_metadata,
                )

        memory_context_pack = self._retrieve_memory_context(
            request_id=request_id,
            user_input=user_input,
            session_context=session_context,
            requester_role="orchestrator_fast",
        )
        memory_prompt_section = MemoryPromptInjector.build_section(
            memory_context_pack,
            max_chars=self._config.memory.runtime.max_context_chars,
        )
        prompt = self._build_direct_prompt(
            user_input=user_input,
            session_context=session_context,
            memory_section=memory_prompt_section,
        )
        llm_started = time.perf_counter()
        llm_error: str | None = None
        used_path = "llm_only_fast"

        try:
            if stream and hasattr(self._llm, "generate_stream"):
                used_path = "llm_stream_fast"
                chunks: list[str] = []
                for token in self._llm.generate_stream(
                    prompt=prompt,
                    system="You are ImperaOS assistant in product mode.",
                    json_mode=False,
                ):
                    if not token:
                        continue
                    chunks.append(token)
                    if on_token is not None:
                        on_token(token)
                final_text = "".join(chunks).strip()
                if not final_text:
                    final_text = self._generate_with_timeout(
                        prompt=prompt,
                        system="You are ImperaOS assistant in product mode.",
                    )
            else:
                final_text = self._generate_with_timeout(
                    prompt=prompt,
                    system="You are ImperaOS assistant in product mode.",
                )
        except Exception as exc:  # noqa: BLE001
            llm_error = str(exc)
            final_text = self._safe_fallback_text(user_input, llm_error)
            fallback_events.append("llm_error_fast_path")

        llm_elapsed = int((time.perf_counter() - llm_started) * 1000)
        memory_write = self._maybe_write_memory(
            request_id=request_id,
            session_id=session_id,
            task_type=TaskType.CHAT.value,
            user_input=user_input,
            assistant_output=final_text,
            expert_payload=None,
        )
        total_elapsed = int((time.perf_counter() - started_total) * 1000)
        run_model_metadata = self._resolve_run_model_metadata(
            requested_model_metadata=requested_model_metadata,
            selected_provider=self._selected_provider_from_llm(),
        )

        metrics = {
            "planner_latency_ms": 0,
            "routing_latency_ms": 0,
            "expert_latency_ms": 0,
            "llm_latency_ms": llm_elapsed,
            "total_latency_ms": total_elapsed,
            "planner_parse_failed": False,
            "planner_reason_code": ReasonCode.PLANNER_OK.value,
            "planner_repair_applied": False,
            "planner_repair_success": False,
            "planner_schema_invalid": False,
            "router_reason_code": ReasonCode.BASELINE_A.value,
            "route_selected_expert": ExpertName.LLM_ONLY.value,
            "memory_written": memory_write["written"],
            "memory_salience_score": memory_write["salience_score"],
            **self._memory_context_metrics(memory_context_pack),
            "memory_write_decision": memory_write["reason"],
            "llm_error": llm_error,
            "tool_calls_used": 0,
            "fast_path": True,
            "stream": stream,
            "fast_path_taken": True,
            "fast_path_candidate_reason": candidate_reason,
            "fast_path_regret_flag": False,
            "expert_needed_after_fast_path": False,
            "followup_correction_rate": self._followup_correction_rate(session_state),
            "active_router_choice": ExpertName.LLM_ONLY.value,
            "shadow_router_choice": None,
            "router_shadow_agreement": None,
            "router_shadow_enabled": False,
            "expert_schema_invalid": False,
            "governance_action": governance_decision.action.value if governance_decision else None,
            "governance_reason_code": (
                governance_decision.reason_code if governance_decision else None
            ),
            "policy_hash": governance_decision.policy_hash if governance_decision else None,
            "requested_provider": run_model_metadata["requested_provider"],
            "requested_fallback_provider": run_model_metadata["requested_fallback_provider"],
            "requested_model_name": run_model_metadata["requested_model_name"],
            "requested_hf_model_id": run_model_metadata["requested_hf_model_id"],
            "selected_provider": run_model_metadata["selected_provider"],
            "selected_model_name": run_model_metadata["selected_model_name"],
            "selected_hf_model_id": run_model_metadata["selected_hf_model_id"],
            "fallback_used": run_model_metadata["fallback_used"],
            "config_source_model_name": run_model_metadata["config_source_model_name"],
            "config_source_hf_model_id": run_model_metadata["config_source_hf_model_id"],
        }
        audit_artifact_path = None
        if self._governance_runtime is not None:
            audit_artifact_path = self._governance_runtime.finalize_run(
                run_id=governance_run_id,
                router_reason_code=ReasonCode.BASELINE_A.value,
                model_metadata=run_model_metadata,
            )
            if audit_artifact_path:
                self._tracer.emit(
                    request_id,
                    "audit_artifact",
                    {"path": audit_artifact_path},
                )
        metrics["audit_artifact_path"] = audit_artifact_path
        self._tracer.emit(
            request_id,
            "final_response",
            {"used_path": used_path, "metrics": metrics},
        )
        self._tracer.emit_router_sample(
            {
                "request_id": request_id,
                "task_type": TaskType.CHAT.value,
                "planner_confidence": 1.0,
                "router_selected_expert": ExpertName.LLM_ONLY.value,
                "router_reason_code": ReasonCode.BASELINE_A.value,
                "used_path": used_path,
                "success": bool(final_text.strip()),
                "total_latency_ms": total_elapsed,
                "active_router_choice": ExpertName.LLM_ONLY.value,
                "shadow_router_choice": None,
                "shadow_agreement": None,
                "fast_path_taken": True,
                "fast_path_regret_flag": False,
            }
        )
        return OrchestratorResult(
            final_text=final_text,
            used_path=used_path,
            fallback_events=fallback_events,
            trace_id=request_id,
            metrics=metrics,
        )

    def _update_router_feedback(
        self,
        expert_name: ExpertName,
        status: ExpertStatus,
        elapsed_ms: int,
    ) -> None:
        updater = getattr(self._router, "update_feedback", None)
        if callable(updater):
            updater(expert_name=expert_name, status=status, elapsed_ms=elapsed_ms)

    @staticmethod
    def _safe_fallback_text(user_input: str, llm_error: str | None) -> str:
        reason = llm_error or "unknown_error"
        return (
            "Geçici model erişim hatası oluştu, güvenli fallback yanıtı veriliyor.\n"
            f"İstek özeti: {user_input}\n"
            f"Hata: {reason}"
        )

    def _generate_with_timeout(self, prompt: str, system: str | None) -> str:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._llm.generate, prompt, system, False)
        try:
            return future.result(timeout=self._config.limits.llm_timeout_ms / 1000)
        except TimeoutError as exc:
            future.cancel()
            raise TimeoutError("orchestrator llm timeout") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _maybe_write_memory(
        self,
        *,
        request_id: str,
        session_id: str,
        task_type: str,
        user_input: str,
        assistant_output: str,
        expert_payload: dict[str, object] | None,
    ) -> dict[str, object]:
        memory_write: dict[str, object] = {
            "written": False,
            "salience_score": 0.0,
            "reason": "memory_manager_missing",
            "record_id": None,
        }
        if (
            self._memory_runtime_bridge is not None
            and self._memory_runtime_bridge.enabled
            and self._config.memory.runtime.post_run_write_enabled
        ):
            result = self._memory_runtime_bridge.propose_post_run_write(
                run_id=request_id,
                actor_id=session_id,
                role="orchestrator",
                user_input=user_input,
                assistant_output=assistant_output,
            )
            memory_write = {
                "written": result.status == "written",
                "salience_score": 0.0,
                "reason": result.status,
                "record_id": result.memory_id,
                "proposal_id": result.proposal_id,
                "evidence_ref": result.evidence_ref,
                "conflict_detected": result.conflict_detected,
                "blocking_reasons": result.blocking_reasons,
            }
            self._tracer.emit(request_id, "memory_write_proposed", memory_write)
            return memory_write
        if self._memory_manager is None:
            return memory_write

        write_result = self._memory_manager.maybe_write(
            session_id=session_id,
            task_type=task_type,
            user_input=user_input,
            assistant_output=assistant_output,
            expert_payload=expert_payload,
        )
        memory_write = {
            "written": write_result.written,
            "salience_score": write_result.salience_score,
            "reason": write_result.reason,
            "record_id": write_result.record_id,
        }
        self._tracer.emit(request_id, "memory_write_decision", memory_write)
        return memory_write

    def _run_expert_with_retries(
        self,
        request_id: str,
        planner_output: PlannerOutput,
        expert_name: ExpertName,
        user_input: str,
        session_context: dict[str, str],
        tool_budget_state: dict[str, int],
    ) -> ExpertResult:
        result: ExpertResult | None = None
        attempts = self._config.limits.max_retries + 1
        for attempt in range(attempts):
            req = ExpertRequest(
                request_id=request_id,
                task_type=planner_output.task_type,
                intent=planner_output.intent,
                user_input=user_input,
                context=session_context,
                latency_budget_ms=planner_output.latency_budget_ms,
            )
            self._tracer.emit(
                request_id,
                "expert_start",
                {
                    "expert": expert_name.value,
                    "attempt": attempt + 1,
                },
            )
            result = self._invoke_expert(expert_name, req, tool_budget_state)
            result = self._normalize_expert_result(result)
            self._tracer.emit(
                request_id,
                "expert_call",
                {
                    "expert": expert_name.value,
                    "attempt": attempt + 1,
                    "status": result.status.value,
                    "elapsed_ms": result.elapsed_ms,
                    "error_code": result.error_code,
                    "schema_valid": result.error_code != ReasonCode.EXPERT_SCHEMA_INVALID.value,
                },
            )
            if result.status == ExpertStatus.OK:
                return result

        assert result is not None
        return result

    def _invoke_expert(
        self,
        expert_name: ExpertName,
        request: ExpertRequest,
        tool_budget_state: dict[str, int],
    ) -> ExpertResult:
        expert = self._experts.get(expert_name.value)
        if expert is None:
            return ExpertResult(
                expert_name=expert_name,
                status=ExpertStatus.ERROR,
                confidence=0.0,
                payload={},
                error_code=ReasonCode.EXPERT_NOT_FOUND.value,
                elapsed_ms=0,
            )

        required_tool_calls = max(0, int(getattr(expert, "estimated_tool_calls_per_run", 1)))
        projected = tool_budget_state["used"] + required_tool_calls
        if projected > self._config.limits.max_tool_calls:
            return ExpertResult(
                expert_name=expert_name,
                status=ExpertStatus.SKIPPED,
                confidence=0.0,
                payload={"reason": "tool_budget_exceeded"},
                error_code=ReasonCode.TOOL_BUDGET_EXCEEDED.value,
                elapsed_ms=0,
            )
        tool_budget_state["used"] = projected

        timeout_s = self._config.limits.expert_timeout_ms / 1000
        started = time.perf_counter()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(expert.run, request)
            try:
                result = future.result(timeout=timeout_s)
                elapsed = int((time.perf_counter() - started) * 1000)
                return result.model_copy(update={"elapsed_ms": max(result.elapsed_ms, elapsed)})
            except TimeoutError:
                future.cancel()
                elapsed = int((time.perf_counter() - started) * 1000)
                return ExpertResult(
                    expert_name=expert_name,
                    status=ExpertStatus.TIMEOUT,
                    confidence=0.0,
                    payload={},
                    error_code="TIMEOUT",
                    elapsed_ms=elapsed,
                )
            except Exception as exc:  # noqa: BLE001
                elapsed = int((time.perf_counter() - started) * 1000)
                return ExpertResult(
                    expert_name=expert_name,
                    status=ExpertStatus.ERROR,
                    confidence=0.0,
                    payload={},
                    error_code=f"EXCEPTION:{type(exc).__name__}",
                    elapsed_ms=elapsed,
                )

    def _normalize_expert_result(self, result: ExpertResult) -> ExpertResult:
        if result.status != ExpertStatus.OK:
            return result
        model = self._expert_payload_models.get(result.expert_name)
        if model is None:
            return result
        try:
            normalized_payload = model.model_validate(result.payload).model_dump(mode="json")
            return result.model_copy(update={"payload": normalized_payload})
        except ValidationError as exc:
            return result.model_copy(
                update={
                    "status": ExpertStatus.PARTIAL,
                    "confidence": min(result.confidence, 0.4),
                    "payload": {
                        "validation_error": str(exc),
                        "raw_payload": result.payload,
                    },
                    "error_code": ReasonCode.EXPERT_SCHEMA_INVALID.value,
                }
            )

    @staticmethod
    def _extract_code_verification_metrics(
        expert_result: ExpertResult | None,
    ) -> dict[str, object]:
        base = {
            "stage_reached": None,
            "retry_count": None,
            "failure_reason": None,
        }
        if expert_result is None or expert_result.expert_name != ExpertName.CODE:
            return base
        verification = expert_result.payload.get("verification")
        if not isinstance(verification, dict):
            return base
        return {
            "stage_reached": verification.get("stage_reached"),
            "retry_count": verification.get("retry_count"),
            "failure_reason": verification.get("failure_reason"),
        }

    @staticmethod
    def _build_synthesis_prompt(
        user_input: str,
        expert_result: ExpertResult,
        *,
        memory_section: str = "",
    ) -> str:
        evidence = json.dumps(expert_result.payload, ensure_ascii=False)
        pieces = []
        if memory_section:
            pieces.append(memory_section)
        pieces.append(
            "You are ImperaOS response synthesizer. "
            "Use the expert evidence to answer clearly and cite uncertainty when needed.\n"
            f"User input: {user_input}\n"
            f"Expert name: {expert_result.expert_name.value}\n"
            f"Expert payload JSON: {evidence}"
        )
        return "\n\n".join(pieces)

    @staticmethod
    def _build_adjudication_prompt(
        user_input: str,
        primary: ExpertResult,
        secondary: ExpertResult,
    ) -> str:
        primary_payload = json.dumps(primary.payload, ensure_ascii=False)
        secondary_payload = json.dumps(secondary.payload, ensure_ascii=False)
        return (
            "You are an evidence-first adjudicator.\n"
            "Resolve conflicts between two expert outputs.\n"
            f"User input: {user_input}\n"
            f"Primary expert ({primary.expert_name.value}): {primary_payload}\n"
            f"Secondary expert ({secondary.expert_name.value}): {secondary_payload}\n"
            "Respond with a single coherent answer and mention uncertainty explicitly when needed."
        )

    @staticmethod
    def _build_direct_prompt(
        user_input: str,
        session_context: dict[str, str],
        *,
        memory_section: str = "",
    ) -> str:
        summary = session_context.get("session_summary", "").strip()
        memory_hints = session_context.get("memory_hints", "").strip()
        pieces = []
        if summary:
            pieces.append(f"Session summary:\n{summary}")
        if memory_hints:
            pieces.append(f"Memory hints:\n{memory_hints}")
        if memory_section:
            pieces.append(memory_section)
        pieces.append(f"User request: {user_input}")
        pieces.append("Respond concisely and clearly.")
        pieces.append(Orchestrator._language_instruction(user_input))
        return "\n\n".join(pieces)

    def _retrieve_memory_context(
        self,
        *,
        request_id: str,
        user_input: str,
        session_context: dict[str, str],
        requester_role: str,
    ) -> MemoryContextPack:
        if self._memory_runtime_bridge is None:
            return empty_context_pack(
                run_id=request_id,
                query=user_input,
                status="disabled",
                degraded_reason="MEMORY_RUNTIME_BRIDGE_MISSING",
            )
        pack = self._memory_runtime_bridge.retrieve_context(
            RuntimeMemoryRequest(
                run_id=request_id,
                query=user_input,
                actor_id=str(
                    session_context.get("actor_id")
                    or session_context.get("session_id")
                    or "local-user"
                ),
                requester_role=requester_role,
                agent_id=session_context.get("agent_id"),
                team_id=session_context.get("team_id"),
                case_id=session_context.get("case_id"),
                project_id=session_context.get("project_id"),
            )
        )
        self._tracer.emit(
            request_id,
            "memory_context_pack",
            pack.model_dump(mode="json", by_alias=True),
        )
        return pack

    @staticmethod
    def _memory_context_metrics(pack: MemoryContextPack) -> dict[str, object]:
        return {
            "memory_runtime_enabled": pack.status not in {"disabled"},
            "memory_context_pack_id": pack.pack_id,
            "memory_context_hit_count": len(pack.hits),
            "memory_context_truncated": pack.truncated,
            "memory_context_status": pack.status,
            "memory_context_degraded_reason": pack.degraded_reason,
            "memory_context_evidence_ref": pack.evidence_ref,
        }

    @staticmethod
    def _language_instruction(user_input: str) -> str:
        text = user_input.lower()
        turkish_markers = (
            "ç",
            "ğ",
            "ı",
            "ö",
            "ş",
            "ü",
            "selam",
            "merhaba",
            "nasılsın",
            "bugün",
            "lütfen",
        )
        if any(marker in text for marker in turkish_markers):
            return "Respond in Turkish."
        return "Use the same language as the user."

    def _requested_model_metadata(self, session_context: dict[str, str]) -> dict[str, str]:
        return {
            "requested_provider": str(
                session_context.get("requested_provider", self._config.llm_provider)
            ),
            "requested_fallback_provider": str(
                session_context.get("requested_fallback_provider", self._config.fallback_provider)
            ),
            "requested_model_name": str(
                session_context.get("requested_model_name", self._config.model_name)
            ),
            "requested_hf_model_id": str(
                session_context.get("requested_hf_model_id", self._config.hf_model_id)
            ),
            "config_source_model_name": str(
                session_context.get("config_source_model_name", "profile")
            ),
            "config_source_hf_model_id": str(
                session_context.get("config_source_hf_model_id", "profile")
            ),
        }

    def _resolve_run_model_metadata(
        self,
        *,
        requested_model_metadata: dict[str, str] | None,
        selected_provider: str | None,
    ) -> dict[str, str | bool | None]:
        requested = requested_model_metadata or self._requested_model_metadata({})
        requested_provider = str(requested.get("requested_provider", self._config.llm_provider))
        requested_fallback_provider = str(
            requested.get("requested_fallback_provider", self._config.fallback_provider)
        )
        requested_model_name = str(requested.get("requested_model_name", self._config.model_name))
        requested_hf_model_id = str(
            requested.get("requested_hf_model_id", self._config.hf_model_id)
        )
        selected = self._normalize_provider_name(selected_provider)
        requested_norm = self._normalize_provider_name(requested_provider)
        requested_fallback_norm = self._normalize_provider_name(requested_fallback_provider)

        fallback_used = False
        if selected is not None:
            if requested_norm == "auto":
                fallback_used = selected == requested_fallback_norm
            else:
                fallback_used = selected != requested_norm

        return {
            "requested_provider": requested_provider,
            "requested_fallback_provider": requested_fallback_provider,
            "requested_model_name": requested_model_name,
            "requested_hf_model_id": requested_hf_model_id,
            "selected_provider": selected,
            "selected_model_name": requested_model_name if selected == "ollama" else None,
            "selected_hf_model_id": requested_hf_model_id if selected == "transformers" else None,
            "fallback_used": fallback_used,
            "config_source_model_name": str(requested.get("config_source_model_name", "profile")),
            "config_source_hf_model_id": str(
                requested.get("config_source_hf_model_id", "profile")
            ),
        }

    def _selected_provider_from_llm(self) -> str | None:
        chain_report = getattr(self._llm, "chain_report", None)
        if not callable(chain_report):
            return None
        report = chain_report()
        provider = getattr(report, "selected_provider", None)
        return self._normalize_provider_name(provider)

    @staticmethod
    def _normalize_provider_name(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if not normalized:
            return None
        if normalized in {"hf", "huggingface"}:
            return "transformers"
        return normalized

    def trace_events(self, request_id: str) -> list[dict[str, object]]:
        return [event.model_dump(mode="json") for event in self._tracer.events_for(request_id)]

    def _blocked_result(
        self,
        *,
        request_id: str,
        started_total: float,
        user_input: str,
        reason_code: str,
        fallback_events: list[str],
        governance_decision: GovernanceDecision,
        governance_run_id: str,
        requested_model_metadata: dict[str, str] | None = None,
    ) -> OrchestratorResult:
        total_elapsed = int((time.perf_counter() - started_total) * 1000)
        final_text = (
            "Bu istek governance policy tarafından engellendi.\n"
            f"İstek özeti: {user_input}\n"
            f"Neden: {reason_code}"
        )
        run_model_metadata = self._resolve_run_model_metadata(
            requested_model_metadata=requested_model_metadata,
            selected_provider=None,
        )
        metrics = {
            "total_latency_ms": total_elapsed,
            "router_reason_code": reason_code,
            "governance_action": governance_decision.action.value,
            "governance_reason_code": governance_decision.reason_code,
            "governance_target": governance_decision.target,
            "policy_hash": governance_decision.policy_hash,
            "requested_provider": run_model_metadata["requested_provider"],
            "requested_fallback_provider": run_model_metadata["requested_fallback_provider"],
            "requested_model_name": run_model_metadata["requested_model_name"],
            "requested_hf_model_id": run_model_metadata["requested_hf_model_id"],
            "selected_provider": run_model_metadata["selected_provider"],
            "selected_model_name": run_model_metadata["selected_model_name"],
            "selected_hf_model_id": run_model_metadata["selected_hf_model_id"],
            "fallback_used": run_model_metadata["fallback_used"],
            "config_source_model_name": run_model_metadata["config_source_model_name"],
            "config_source_hf_model_id": run_model_metadata["config_source_hf_model_id"],
            "fast_path_regret_flag": False,
            "followup_correction_rate": 0.0,
            "audit_artifact_path": None,
        }
        if self._governance_runtime is not None:
            audit_artifact = self._governance_runtime.finalize_run(
                run_id=governance_run_id,
                router_reason_code=reason_code,
                model_metadata=run_model_metadata,
            )
            metrics["audit_artifact_path"] = audit_artifact
            if audit_artifact:
                self._tracer.emit(request_id, "audit_artifact", {"path": audit_artifact})
        return OrchestratorResult(
            final_text=final_text,
            used_path="governance_blocked",
            fallback_events=fallback_events,
            trace_id=request_id,
            metrics=metrics,
        )

    def _pending_result(
        self,
        *,
        request_id: str,
        started_total: float,
        user_input: str,
        fallback_events: list[str],
        governance_decision: GovernanceDecision,
        approval_id: str | None,
        governance_run_id: str,
        requested_model_metadata: dict[str, str] | None = None,
    ) -> OrchestratorResult:
        total_elapsed = int((time.perf_counter() - started_total) * 1000)
        final_text = (
            "Bu istek operator onayı gerektiriyor.\n"
            f"Approval ID: {approval_id or 'unknown'}"
        )
        run_model_metadata = self._resolve_run_model_metadata(
            requested_model_metadata=requested_model_metadata,
            selected_provider=None,
        )
        metrics = {
            "total_latency_ms": total_elapsed,
            "router_reason_code": ReasonCode.APPROVAL_PENDING.value,
            "governance_action": governance_decision.action.value,
            "governance_reason_code": governance_decision.reason_code,
            "governance_target": governance_decision.target,
            "policy_hash": governance_decision.policy_hash,
            "approval_id": approval_id,
            "requested_provider": run_model_metadata["requested_provider"],
            "requested_fallback_provider": run_model_metadata["requested_fallback_provider"],
            "requested_model_name": run_model_metadata["requested_model_name"],
            "requested_hf_model_id": run_model_metadata["requested_hf_model_id"],
            "selected_provider": run_model_metadata["selected_provider"],
            "selected_model_name": run_model_metadata["selected_model_name"],
            "selected_hf_model_id": run_model_metadata["selected_hf_model_id"],
            "fallback_used": run_model_metadata["fallback_used"],
            "config_source_model_name": run_model_metadata["config_source_model_name"],
            "config_source_hf_model_id": run_model_metadata["config_source_hf_model_id"],
            "fast_path_regret_flag": False,
            "followup_correction_rate": 0.0,
            "audit_artifact_path": None,
        }
        if self._governance_runtime is not None:
            audit_artifact = self._governance_runtime.finalize_run(
                run_id=governance_run_id,
                router_reason_code=ReasonCode.APPROVAL_PENDING.value,
                model_metadata=run_model_metadata,
            )
            metrics["audit_artifact_path"] = audit_artifact
            if audit_artifact:
                self._tracer.emit(request_id, "audit_artifact", {"path": audit_artifact})
        return OrchestratorResult(
            final_text=final_text,
            used_path="governance_pending",
            fallback_events=fallback_events,
            trace_id=request_id,
            metrics=metrics,
        )

    @staticmethod
    def _ensure_session_state_data(state: dict[str, int]) -> dict[str, int]:
        state.setdefault("turn", 0)
        state.setdefault("fast_path_count", 0)
        state.setdefault("regret_count", 0)
        state.setdefault("last_fast_path_turn", -1000)
        return state

    def _ensure_session_state(self, session_id: str) -> dict[str, int]:
        state = self._fast_path_sessions.setdefault(session_id, {})
        return self._ensure_session_state_data(state)

    def _followup_correction_rate(self, session_state: dict[str, int]) -> float:
        fast_count = max(session_state.get("fast_path_count", 0), 0)
        if fast_count == 0:
            return 0.0
        regret_count = max(session_state.get("regret_count", 0), 0)
        return round(regret_count / fast_count, 4)

    def _is_expert_needed_after_fast_path(
        self,
        *,
        session_state: dict[str, int],
        planner_output: PlannerOutput,
    ) -> bool:
        if not planner_output.needs_expert:
            return False
        window = self._config.fast_path_regret_window
        since_last_fast = session_state["turn"] - session_state["last_fast_path_turn"]
        return since_last_fast <= window
