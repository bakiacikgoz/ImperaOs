# ARCHITECTURE (v0.4)

## Product Path (Default)

1. User input is accepted by CLI.
2. Fast-path classifier optionally routes short/greeting inputs directly to `process_fast_chat`.
3. Normal path calls planner (strict JSON contract).
4. Active router selects expert path (`rule` in balanced by default).
5. Shadow router runs in parallel for telemetry-only comparison.
6. Expert execution is guarded by timeout, retries, tool budget, recursion limit, and circuit breaker.
7. LLM synthesizes final response.
8. Memory gate decides whether to persist memory candidate.
9. Tracer emits local telemetry (privacy-gated).

## Research Path

- Router telemetry dataset JSONL can be used to train/eval router calibration scripts.
- Research scripts are isolated under `research/sltc_experiments/`.
- Product runtime is not destabilized by research scripts.

## Core Components

- `imperaos/core/planner.py`: strict planner + deterministic fallback.
- `imperaos/core/orchestrator.py`: fallback logic, guardrails, synthesis, shadow metrics.
- `imperaos/governance/*`: policy engine, approval queue, audit/redaction pipeline.
- `imperaos/team/*`: team supervisor, DAG scheduler, handoff protocol, replay/export artifacts.
- `imperaos/router/rule_router.py`: deterministic active routing baseline.
- `imperaos/router/sltc_router.py`: temporal/spiking-inspired router.
- `imperaos/experts/*`: typed expert payload producers.
- `imperaos/memory/*`: salience gate + store + retrieval ranking.
- `imperaos/telemetry/tracer.py`: trace events and router samples.

## Team Runtime Path

1. `team run` resolves spec and creates `case_id` + `job_id`.
2. Supervisor builds task graph (spec-defined DAG or deterministic auto-decomposition).
3. Parallel scheduler executes runnable tasks with dependency tracking.
4. Inter-task handoffs pass governance + redaction checks.
5. Scoped memory writes pass governance checks (`session|team|case`).
6. Team audit envelope is emitted with hash-chain integrity metadata.

## Active vs Experimental

- Active (default): rule routing + sLTC shadow in balanced profile.
- Experimental: direct sLTC active routing in research profile.
- Deferred: desktop UI thin-shell.

## Vision-First Computer-Use Foundation

The existing bounded computer-use pilot remains the default runtime. A new additive package, `imperaos/computer_use/vision_runtime/`, introduces typed ports and contracts for a future vision-first desktop/web/file action loop.

The foundation is structured around:

```text
observe -> interpret -> decide -> policy -> approval -> execute -> verify -> checkpoint
```

Production defaults keep this path fail-closed: `runtime_mode="legacy_pilot"`, `vision_enabled=false`, raw screenshot retention disabled, terminal control denied, and platform qualification required.

The operator panel receives an additive `computerUseVisionRuntime` capability next to the existing `computerUsePilot` field, allowing the UI to surface readiness without enabling live execution.
## Vision-First Computer-Use Phase 2

The vision-first runtime lives under `imperaos/computer_use/vision_runtime/`. Phase 2 adds macOS-specific readiness, screenshot capture, guarded input execution, an Ollama-compatible strict JSON vision interpreter, approval snapshot validation, replay verification, and qualification reporting. These components are additive to the legacy Safari/Finder/TextEdit pilot and do not enable Windows or Linux live execution.

Default architecture remains fail-closed:

- `vision_provider="none"` blocks runtime execution.
- `macos_input_backend="disabled"` blocks OS input.
- `raw_screenshot_max_count=0` prevents raw screenshot persistence.
- operator panel reads the additive `computerUseVisionRuntime` capability.
