# TECHNICAL_SPEC_v2.0

## Product Path

- LLM generation is provider-agnostic through `OllamaLLM` chain
- Primary provider: `auto` (Ollama first), fallback provider optional
- Planner output is strict typed schema (`PlannerOutput`)
- Router output is strict typed schema (`RouterDecision` with `ReasonCode` enum)
- Experts expose structured payload contracts (code/research/plan)
- Orchestrator enforces timeout, retries, fallback, circuit-breaker, tool budget, recursion depth
- Governance engine enforces task/tool policy (`allow|deny|require_approval`)
- Async approval queue stores operator decisions with replay/idempotency guards
- Per-run privacy-safe audit artifact is emitted under `.imperaos/audit/`
- Team runtime supports DAG task orchestration with governed handoffs and scoped memory writes
- Team run artifacts are emitted under `.imperaos/team/jobs/<job_id>/`

## Memory Path

- SQLite-backed store with dedup (`content_hash`)
- TTL-aware records (`expires_at`)
- Salience-driven write gate
- Ranked retrieval based on salience + recency

## Research Path

- Router telemetry samples can be persisted as JSONL
- Offline scripts:
  - `research/sltc_experiments/train_router.py`
  - `research/sltc_experiments/eval_router.py`
- Research path is isolated from product runtime

## CLI Surface

- `doctor`
- `chat`
- `team init|validate|run|status|logs|replay|artifacts`
- `benchmark smoke|ablation|energy`
- `benchmark team`
- `memory stats`
- `research train-router|eval-router`
- `approval pending|decide|execute`
- `operator panel`
