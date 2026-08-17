# ImperaOS AI v0.2.x Focused Tuning Update (2026-03-01)

## Scope
This update implements the focused v0.2.x package without LoRA/UI expansion:

1. Planner prompt/repair tuning
2. Code expert verification loop strengthening
3. sLTC router calibration pipeline
4. Memory salience tuning

## Implementation Summary

### 1) Planner Prompt/Repair Tuning
- `imperaos/core/planner.py`
  - Added strict prompt variants: `strict_v1|strict_v2|strict_v3`
  - Added controlled repair controls:
    - `repair_enabled`
    - `repair_max_attempts`
  - Hardened parse path into explicit failure classes:
    - JSON extraction failure
    - repair failure
    - schema invalid
  - Deterministic fallback preserved for all planner failures.
- `imperaos/schemas/reason_codes.py`
  - Added/used planner-specific reason codes:
    - `PLANNER_JSON_EXTRACT_FAILED`
    - `PLANNER_REPAIR_FAILED`
    - `PLANNER_REPAIR_APPLIED`
    - `PLANNER_SCHEMA_INVALID`
- Added corpus-driven regression:
  - `benchmarks/tasks/planner_failures/planner_failure_cases.jsonl`
  - `tests/test_planner_failure_corpus.py`

Planner metrics now available in benchmark outputs:
- `planner_parse_fail_rate`
- `planner_repair_applied_rate`
- `planner_repair_success_rate`
- `planner_schema_invalid_rate`
- `planner_fallback_rate`

### 2) Code Expert Verification Loop Strengthening
- `imperaos/tools/code_verify.py`
  - Staged verification pipeline:
    - Stage 1: AST parse
    - Stage 2: compile/lint checks
    - Stage 3: pytest collect
    - Stage 4: targeted tests (config-driven)
    - Stage 5: full success state
  - Added normalized failure classification (`SYNTAX_INVALID`, `IMPORT_PARSE_FAIL`, `TEST_COLLECT_FAILED`, timeout/allowlist classes).
- `imperaos/experts/code_expert.py`
  - Added failure-aware retry loop (`retry_max`, `retry_strategy`)
  - Strategy adapts by failure category (`minimal_patch`, `explain_only`, etc.)
  - Returns `partial` when verification is incomplete/failing, instead of crashing.
- `imperaos/schemas/expert_payloads.py`
  - Verification payload expanded with:
    - `stage_reached`
    - `failure_reason`
    - `retry_count`
    - `retry_strategy`
- Added tests:
  - `tests/test_code_verification_loop.py`

### 3) sLTC Router Calibration Pipeline
- `research/sltc_experiments/train_router.py`
  - Added calibration sweep API:
    - `calibrate_router_params(...)`
  - Deterministic split + candidate evaluation + holdout metrics
  - Outputs:
    - `router_calibration_candidates.json`
    - `router_calibration_report.json`
    - `router_calibration_report.md`
- `imperaos/cli.py`
  - New command: `imperaos research calibrate-router`
- `imperaos/router/sltc_router.py`
  - Exposed calibration tunables in runtime path:
    - `failure_penalty_weight`
    - `latency_penalty_weight`
    - `need_bonus`
    - `conf_bonus`
    - `task_bias_overrides`
- Added reproducibility test:
  - `tests/test_router_calibration.py`

### 4) Memory Salience Tuning
- `imperaos/memory/salience_gate.py`
  - Tunables now configurable:
    - `task_bonus`
    - `expert_bonus`
    - `spike_reduction`
    - `keyword_weights`
- `imperaos/memory/retrieval_ranker.py`
  - Weighted ranking: `score = a*salience + b*recency`
- `imperaos/memory/manager.py`
  - Added metrics counters for write/retrieval usefulness path
  - Added ranking weight controls in manager constructor
  - Exposes tuning metrics in `stats()` payload
- `imperaos/memory/persistent_store.py`
  - Added `write_with_status` with dedup-aware return payload
- Added metrics test:
  - `tests/test_memory_tuning_metrics.py`

## Config Surface Added/Updated
- `imperaos/runtime/config.py`
  - New typed config sections:
    - `planner_tuning`
    - `code_verify`
  - Expanded `sltc` and `memory` tuning fields
  - `resolve_runtime_config` merges new sections from profile/env/CLI
- Profile TOMLs updated:
  - `config/default.toml`
  - `config/lite.toml`
  - `config/balanced.toml`
  - `config/research.toml`

## Runtime Wiring
- `imperaos/cli.py`
  - Orchestrator builder now wires:
    - planner tuning config
    - code verify config
    - memory tuning weights
    - sLTC runtime mode (`active|shadow|off`)
- `imperaos/core/orchestrator.py`
  - Exposes planner/code verification telemetry fields in request metrics

## Flow / Algorithm (Updated)
1. User input enters orchestrator.
2. Planner generates strict JSON plan using selected prompt variant.
3. Planner output goes through extraction -> optional repair -> strict schema validation.
4. Router decision is made (rule or sLTC active) while optional shadow router logs counterfactual.
5. Code tasks run through staged verification loop with bounded failure-aware retries.
6. Memory writes are salience-gated and dedup-aware; retrieval uses weighted salience/recency ranking.
7. Telemetry and benchmark summaries include planner, routing, code verification, and memory tuning metrics.

## Validation Run (Current)
- `uv run ruff check .` -> passed
- `uv run pytest -q` -> passed
- `uv run imperaos doctor --profile balanced` -> healthy provider chain
- `uv run imperaos benchmark smoke --mode all --profile balanced --provider transformers --fallback-provider transformers` -> passed
- `uv run imperaos benchmark ablation --mode all --profile balanced --suite quality --provider transformers --fallback-provider transformers` -> passed (120 tasks)
- `uv run imperaos benchmark energy --profile balanced --energy-mode measured --provider transformers --fallback-provider transformers` -> deterministic measured-fail payload (no superuser) + estimated fallback metadata
- `uv run imperaos research train-router ...` -> artifacts generated
- `uv run imperaos research eval-router ...` -> artifacts generated
- `uv run imperaos research calibrate-router ...` -> calibration artifacts generated

## Artifacts Generated in This Update
- `benchmarks/results/smoke_*.json`
- `benchmarks/results/smoke_*.md`
- `benchmarks/results/energy_*.json`
- `research/sltc_experiments/artifacts/router_model.json`
- `research/sltc_experiments/artifacts/train_metrics.json`
- `research/sltc_experiments/artifacts/train_report.md`
- `research/sltc_experiments/artifacts/eval_metrics.json`
- `research/sltc_experiments/artifacts/eval_report.md`
- `research/sltc_experiments/artifacts/router_calibration_candidates.json`
- `research/sltc_experiments/artifacts/router_calibration_report.json`
- `research/sltc_experiments/artifacts/router_calibration_report.md`

## Notes
- Product path remains stable: no LoRA, no new expert class, no UI expansion.
- Changes are config-gated and can be tuned per profile.
- Privacy defaults remain intact; persistent router dataset writing still requires debug mode + privacy disabled.
