from __future__ import annotations

import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from imperaos.core.llm_ollama import OllamaLLM
from imperaos.core.orchestrator import Orchestrator
from imperaos.core.planner import Planner
from imperaos.experts.code_expert import CodeExpert
from imperaos.experts.memory_plan_expert import MemoryPlanExpert
from imperaos.experts.research_expert import ResearchExpert
from imperaos.memory.manager import MemoryManager
from imperaos.memory.persistent_store import PersistentMemoryStore
from imperaos.memory.salience_gate import SalienceGate
from imperaos.router.rule_router import RuleRouter
from imperaos.router.sltc_router import SLTCRouter
from imperaos.runtime.config import RuntimeConfig
from imperaos.schemas.models import ExpertName
from imperaos.schemas.reason_codes import ReasonCode
from imperaos.telemetry.tracer import Tracer


def run_smoke_benchmark(
    profile: str = "lite",
    mode: str = "both",
    suite: str = "smoke",
    output_path: str | None = None,
    task_limit: int | None = None,
    provider: str | None = None,
    fallback_provider: str | None = None,
    model: str | None = None,
    hf_model_id: str | None = None,
) -> dict[str, Any]:
    selected_modes = _resolve_modes(mode)
    tasks = _load_tasks(
        _resolve_tasks_path(suite),
        task_limit=task_limit,
    )

    config = RuntimeConfig.from_profile(profile)
    result: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "profile": profile,
        "mode": mode,
        "suite": suite,
        "results": {},
    }

    for mode_name in selected_modes:
        run_result = _run_mode(
            tasks=tasks,
            config=config,
            mode_name=mode_name,
            provider=provider,
            fallback_provider=fallback_provider,
            model=model,
            hf_model_id=hf_model_id,
        )
        result["results"][mode_name] = run_result

    destination = Path(output_path) if output_path else _default_output_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    result["output_path"] = str(destination)
    return result


def _run_mode(
    tasks: list[dict[str, str]],
    config: RuntimeConfig,
    mode_name: str,
    provider: str | None = None,
    fallback_provider: str | None = None,
    model: str | None = None,
    hf_model_id: str | None = None,
) -> dict[str, Any]:
    answer_llm = _build_llm(
        config=config,
        temperature=config.answer_temperature,
        provider=provider,
        fallback_provider=fallback_provider,
        model=model,
        hf_model_id=hf_model_id,
    )
    planner_llm = _build_llm(
        config=config,
        temperature=config.planner_temperature,
        provider=provider,
        fallback_provider=fallback_provider,
        model=model,
        hf_model_id=hf_model_id,
    )
    planner = Planner(
        planner_llm,
        default_latency_budget_ms=config.latency_budget_ms,
        llm_timeout_ms=config.limits.llm_timeout_ms,
        repair_enabled=config.planner_tuning.repair_enabled,
        repair_max_attempts=config.planner_tuning.repair_max_attempts,
        prompt_variant=config.planner_tuning.prompt_variant,
    )
    router, use_router, memory_enabled = _build_mode_runtime(mode_name=mode_name, config=config)
    shadow_router = _build_shadow_router(config=config, active_router=router, use_router=use_router)

    experts = {
        ExpertName.CODE.value: CodeExpert(workspace=Path.cwd(), verify_config=config.code_verify),
        ExpertName.RESEARCH.value: ResearchExpert(workspace=Path.cwd()),
        ExpertName.PLAN.value: MemoryPlanExpert(),
    }
    tracer = Tracer(
        debug_mode=False,
        privacy_mode=True,
        trace_dir=config.trace_dir,
        router_dataset_path=config.router_dataset_path,
    )
    memory_manager = _build_memory_manager(config=config, enabled=memory_enabled)

    orchestrator = Orchestrator(
        planner=planner,
        llm=answer_llm,
        router=router,
        experts=experts,
        tracer=tracer,
        config=config,
        memory_manager=memory_manager,
        shadow_router=shadow_router,
    )

    latencies: list[int] = []
    successes = 0
    fallbacks = 0
    wrong_routes = 0
    route_checks = 0
    expert_calls = 0
    memory_writes = 0
    planner_parse_failures = 0
    planner_fallbacks = 0
    planner_repair_applied = 0
    planner_repair_success = 0
    planner_schema_invalid = 0
    router_low_confidence = 0
    expert_schema_invalid = 0
    expert_timeouts = 0
    fallback_activations = 0
    fast_path_usage = 0
    fast_path_regret = 0
    shadow_agreements = 0
    shadow_disagreements: dict[str, int] = {}
    shadow_total = 0
    peak_rss = 0
    process = psutil.Process()

    for task in tasks:
        output = orchestrator.process(task["input"], session_context={}, use_router=use_router)
        latencies.append(int(output.metrics.get("total_latency_ms", 0)))
        if output.final_text.strip():
            successes += 1
        if output.fallback_events:
            fallbacks += 1
            fallback_activations += 1
        if output.used_path.startswith("expert"):
            expert_calls += 1
        if bool(output.metrics.get("memory_written", False)):
            memory_writes += 1
        if bool(output.metrics.get("planner_parse_failed", False)):
            planner_parse_failures += 1
            planner_fallbacks += 1
        planner_reason = str(output.metrics.get("planner_reason_code", ""))
        if planner_reason == ReasonCode.PLANNER_REPAIR_APPLIED.value:
            planner_repair_applied += 1
            planner_repair_success += 1
        if planner_reason == ReasonCode.PLANNER_SCHEMA_INVALID.value:
            planner_schema_invalid += 1
        if any("router_low_confidence" in item for item in output.fallback_events):
            router_low_confidence += 1
        if bool(output.metrics.get("expert_schema_invalid", False)):
            expert_schema_invalid += 1
        if any(":timeout" in item for item in output.fallback_events):
            expert_timeouts += 1
        if bool(output.metrics.get("fast_path_taken", False)):
            fast_path_usage += 1
        if bool(output.metrics.get("fast_path_regret_flag", False)):
            fast_path_regret += 1
        shadow_agreement = output.metrics.get("router_shadow_agreement")
        if shadow_agreement is not None:
            shadow_total += 1
            if bool(shadow_agreement):
                shadow_agreements += 1
            else:
                bucket = (
                    f"{output.metrics.get('active_router_choice')}->"
                    f"{output.metrics.get('shadow_router_choice')}"
                )
                shadow_disagreements[bucket] = shadow_disagreements.get(bucket, 0) + 1

        if use_router:
            route_checks += 1
            expected = _expected_route(task["task_type"])
            actual = str(output.metrics.get("route_selected_expert", ExpertName.LLM_ONLY.value))
            if expected != actual:
                wrong_routes += 1

        peak_rss = max(peak_rss, process.memory_info().rss)

    total_latency_ms = sum(latencies)
    memory_stats = memory_manager.stats() if memory_manager is not None else {}
    return {
        "task_count": len(tasks),
        "success_rate": round(successes / max(len(tasks), 1), 4),
        "p50_latency_ms": _percentile(latencies, 50),
        "p95_latency_ms": _percentile(latencies, 95),
        "peak_ram_mb": round(peak_rss / (1024 * 1024), 2),
        "fallback_rate": round(fallbacks / max(len(tasks), 1), 4),
        "wrong_route_rate": round(wrong_routes / max(route_checks, 1), 4) if use_router else 0.0,
        "expert_call_rate": round(expert_calls / max(len(tasks), 1), 4),
        "memory_write_rate": round(memory_writes / max(len(tasks), 1), 4),
        "planner_parse_fail_rate": round(planner_parse_failures / max(len(tasks), 1), 4),
        "planner_repair_applied_rate": round(planner_repair_applied / max(len(tasks), 1), 4),
        "planner_repair_success_rate": round(planner_repair_success / max(len(tasks), 1), 4),
        "planner_schema_invalid_rate": round(planner_schema_invalid / max(len(tasks), 1), 4),
        "planner_fallback_rate": round(planner_fallbacks / max(len(tasks), 1), 4),
        "router_low_confidence_rate": round(router_low_confidence / max(len(tasks), 1), 4),
        "router_shadow_agreement_rate": (
            round(shadow_agreements / max(shadow_total, 1), 4) if shadow_total else None
        ),
        "expert_schema_invalid_rate": round(expert_schema_invalid / max(len(tasks), 1), 4),
        "expert_timeout_rate": round(expert_timeouts / max(len(tasks), 1), 4),
        "fallback_activation_rate": round(fallback_activations / max(len(tasks), 1), 4),
        "fast_path_usage_rate": round(fast_path_usage / max(len(tasks), 1), 4),
        "fast_path_regret_rate": round(fast_path_regret / max(len(tasks), 1), 4),
        "memory_retrieval_usefulness_rate": memory_stats.get("retrieval_usefulness_rate"),
        "memory_dedup_hit_rate": memory_stats.get("dedup_hit_rate"),
        "memory_retrieval_hit_rate": memory_stats.get("retrieval_hit_rate"),
        "memory_stale_retrieval_ratio": memory_stats.get("stale_retrieval_ratio"),
        "energy_estimate_wh": round(_estimate_energy_wh(total_latency_ms, peak_rss), 5),
        "router_kind": type(router).__name__ if use_router else "None",
        "shadow_router_kind": type(shadow_router).__name__ if shadow_router is not None else None,
        "router_shadow_disagreement_buckets": shadow_disagreements,
    }


def _build_llm(
    config: RuntimeConfig,
    temperature: float,
    provider: str | None = None,
    fallback_provider: str | None = None,
    model: str | None = None,
    hf_model_id: str | None = None,
) -> OllamaLLM:
    return OllamaLLM(
        model_name=(model or config.model_name),
        temperature=temperature,
        provider_name=(provider or config.llm_provider),
        fallback_provider=(fallback_provider or config.fallback_provider),
        fallback_enabled=config.fallback_enabled,
        hf_model_id=(hf_model_id or config.hf_model_id),
        device=config.device,
    )


def _build_mode_runtime(
    mode_name: str,
    config: RuntimeConfig,
) -> tuple[RuleRouter | SLTCRouter, bool, bool]:
    if mode_name == "A":
        return RuleRouter(confidence_threshold=config.router_confidence_threshold), False, False
    if mode_name == "B":
        return RuleRouter(confidence_threshold=config.router_confidence_threshold), True, False
    if mode_name == "C":
        return (
            SLTCRouter(
                confidence_threshold=config.sltc.confidence_threshold,
                decay=config.sltc.decay,
                spike_threshold=config.sltc.spike_threshold,
                failure_penalty_weight=config.sltc.failure_penalty_weight,
                latency_penalty_weight=config.sltc.latency_penalty_weight,
                need_bonus=config.sltc.need_bonus,
                conf_bonus=config.sltc.conf_bonus,
                task_bias_overrides=config.sltc.task_bias_overrides,
            ),
            True,
            False,
        )
    if mode_name == "D":
        return (
            SLTCRouter(
                confidence_threshold=config.sltc.confidence_threshold,
                decay=config.sltc.decay,
                spike_threshold=config.sltc.spike_threshold,
                failure_penalty_weight=config.sltc.failure_penalty_weight,
                latency_penalty_weight=config.sltc.latency_penalty_weight,
                need_bonus=config.sltc.need_bonus,
                conf_bonus=config.sltc.conf_bonus,
                task_bias_overrides=config.sltc.task_bias_overrides,
            ),
            True,
            True,
        )
    raise ValueError(f"Unsupported mode: {mode_name}")


def _build_memory_manager(config: RuntimeConfig, enabled: bool) -> MemoryManager:
    store = PersistentMemoryStore(db_path=config.memory.db_path) if enabled else None
    gate = SalienceGate(
        threshold=config.memory.salience_threshold,
        decay=config.memory.salience_decay,
        task_bonus=config.memory.task_bonus,
        expert_bonus=config.memory.expert_bonus,
        spike_reduction=config.memory.spike_reduction,
        keyword_weights=config.memory.keyword_weights,
    )
    return MemoryManager(
        enabled=enabled,
        store=store,
        gate=gate,
        max_rows=config.memory.max_rows,
        ttl_days=config.memory_ttl_days,
        rank_salience_weight=config.memory.rank_salience_weight,
        rank_recency_weight=config.memory.rank_recency_weight,
    )


def _build_shadow_router(
    *,
    config: RuntimeConfig,
    active_router: RuleRouter | SLTCRouter,
    use_router: bool,
) -> RuleRouter | SLTCRouter | None:
    if not use_router or not config.shadow_router_enabled:
        return None
    if config.sltc.router_mode.lower() == "off":
        return None
    active_mode = "sltc" if isinstance(active_router, SLTCRouter) else "rule"
    shadow_mode = config.shadow_router_mode.lower()
    if shadow_mode == active_mode:
        shadow_mode = "rule" if active_mode == "sltc" else "sltc"
    if shadow_mode == "sltc":
        return SLTCRouter(
            confidence_threshold=config.sltc.confidence_threshold,
            decay=config.sltc.decay,
            spike_threshold=config.sltc.spike_threshold,
            failure_penalty_weight=config.sltc.failure_penalty_weight,
            latency_penalty_weight=config.sltc.latency_penalty_weight,
            need_bonus=config.sltc.need_bonus,
            conf_bonus=config.sltc.conf_bonus,
            task_bias_overrides=config.sltc.task_bias_overrides,
        )
    return RuleRouter(confidence_threshold=config.router_confidence_threshold)


def _resolve_modes(mode: str) -> list[str]:
    normalized = mode.strip().upper()
    if normalized in {"A", "B", "C", "D"}:
        return [normalized]
    if normalized == "BOTH":
        return ["A", "B"]
    if normalized == "ALL":
        return ["A", "B", "C", "D"]
    raise ValueError("mode must be one of: A, B, C, D, both, all")


def _load_tasks(path: Path, task_limit: int | None = None) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        tasks.append(json.loads(line))
        if task_limit is not None and task_limit > 0 and len(tasks) >= task_limit:
            break
    return tasks


def _resolve_tasks_path(suite: str) -> Path:
    normalized = suite.strip().lower()
    root = Path(__file__).resolve().parent / "tasks"
    if normalized == "smoke":
        return root / "smoke_tasks.jsonl"
    if normalized == "quality":
        return root / "quality" / "quality_tasks.jsonl"
    raise ValueError("suite must be one of: smoke, quality")


def _expected_route(task_type: str) -> str:
    mapping = {
        "chat": ExpertName.LLM_ONLY.value,
        "plan": ExpertName.PLAN.value,
        "research": ExpertName.RESEARCH.value,
        "code": ExpertName.CODE.value,
        "mixed": ExpertName.RESEARCH.value,
    }
    return mapping.get(task_type, ExpertName.LLM_ONLY.value)


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return values[0]

    sorted_values = sorted(values)
    if percentile == 50:
        return int(statistics.median(sorted_values))

    index = int(round((percentile / 100) * (len(sorted_values) - 1)))
    return int(sorted_values[index])


def _estimate_energy_wh(total_latency_ms: int, peak_rss_bytes: int) -> float:
    elapsed_h = max(total_latency_ms / 3_600_000, 0.000001)
    rss_gb = peak_rss_bytes / (1024**3)
    assumed_watts = 6.5 + (rss_gb * 1.3)
    return assumed_watts * elapsed_h


def _default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("benchmarks") / "results" / f"smoke_{timestamp}.json"


if __name__ == "__main__":
    payload = run_smoke_benchmark(mode="all")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
