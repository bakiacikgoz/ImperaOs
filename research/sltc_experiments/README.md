# sLTC Router Experiments

This folder contains reproducible offline experiments for router calibration.

## Inputs

- Dataset JSONL: `.imperaos/research/router_dataset.jsonl`
- Each row should include: `task_type`, `router_selected_expert`, `success`, `total_latency_ms`

## Train

```bash
uv run imperaos research train-router \
  --dataset .imperaos/research/router_dataset.jsonl \
  --output-dir research/sltc_experiments/artifacts \
  --seed 42
```

## Eval

```bash
uv run imperaos research eval-router \
  --dataset .imperaos/research/router_dataset.jsonl \
  --model research/sltc_experiments/artifacts/router_model.json \
  --output-dir research/sltc_experiments/artifacts
```

## Outputs

- `router_model.json`
- `train_metrics.json`, `train_report.md`
- `eval_metrics.json`, `eval_report.md`
