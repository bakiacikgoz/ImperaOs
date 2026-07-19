# BENCHMARK_PROTOCOL (v0.2)

## Command Layers

### Smoke (health)

```bash
uv run imperaos benchmark smoke --mode all --profile balanced
```

### Ablation (quality)

```bash
uv run imperaos benchmark ablation --mode all --profile balanced --suite quality
```

### Energy

```bash
uv run imperaos benchmark energy --profile balanced --energy-mode measured
uv run imperaos benchmark energy --profile balanced --energy-mode estimated
```

## Suites

- `smoke`: hızlı sağlık kontrolü
- `quality`: 120 görev minimum set

Quality dağılımı:

- chat: 30
- code: 30
- research: 20
- plan: 20
- mixed: 20

## Ablation Modes

- `A`: LLM-only baseline
- `B`: LLM + rule router
- `C`: LLM + sLTC router
- `D`: LLM + sLTC router + memory writes

## Reported Metrics

- `success_rate`
- `p50_latency_ms`
- `p95_latency_ms`
- `peak_ram_mb`
- `fallback_rate`
- `wrong_route_rate`
- `expert_call_rate`
- `memory_write_rate`
- `planner_parse_fail_rate`
- `planner_fallback_rate`
- `router_low_confidence_rate`
- `router_shadow_agreement_rate`
- `expert_schema_invalid_rate`
- `expert_timeout_rate`
- `fallback_activation_rate`
- `fast_path_usage_rate`
- `fast_path_regret_rate`
- `energy_estimate_wh`

## Energy Schema

Root fields include:

- `measurement_mode`
- `energy_mode` (compat)
- `estimated_wh`
- `fallback_estimation_method`
- `platform_info`
- `measured.*`

Measured payload fields include:

- `measurement_mode`
- `is_privileged`
- `sampling_window_s`
- `tool_name`
- `confidence`
- `error_reason`
- `fallback_estimation_method`
- `platform_info`
- `notes`

## Outputs

- JSON: `benchmarks/results/*.json`
- Markdown: ablation report (`*.md`)
- Artifacts: `artifacts/benchmark_summary.json`
