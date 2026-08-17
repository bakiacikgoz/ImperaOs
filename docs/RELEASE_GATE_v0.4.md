# RELEASE_GATE_v0.4

## 1. Code Quality

```bash
uv run ruff check .
uv run pytest -q
```

## 2. Runtime Health

```bash
uv run imperaos doctor --profile balanced
```

## 3. Benchmarks

```bash
uv run imperaos benchmark smoke --mode all --profile balanced
uv run imperaos benchmark team --profile restricted --suite smoke --spec team.yaml --deterministic-mock
uv run imperaos benchmark team --profile balanced --suite smoke --spec team.yaml
uv run imperaos benchmark ablation --mode all --profile balanced --suite quality
uv run imperaos benchmark energy --profile balanced --energy-mode measured
```

Measured energy command may fail due permission; failure payload must remain deterministic and schema-valid.

## 4. Research Repro

```bash
uv run imperaos research train-router --dataset .imperaos/research/router_dataset.jsonl
uv run imperaos research eval-router --dataset .imperaos/research/router_dataset.jsonl
```

## 5. Artifacts

Required files under `artifacts/`:

- `status.json`
- `test_summary.json`
- `benchmark_summary.json`
- `router_shadow_summary.json`
- `research_summary.json`
- `governance_summary.json`
- `team_summary.json`

All files must be valid JSON with `artifact/generated_at/status/data` envelope.

## 6. Governance + Team Regression

```bash
uv run pytest -q tests/test_governance_policy.py
uv run pytest -q tests/test_policy_fail_closed.py
uv run pytest -q tests/test_approval_flow.py
uv run pytest -q tests/test_sandbox_governance.py
uv run pytest -q tests/test_audit_artifacts.py
uv run pytest -q tests/test_team_*.py
uv run pytest -q tests/test_memory_concurrency.py
uv run pytest -q tests/test_team_checkpoint_concurrency.py
```

Expected controls:

- policy load fail -> fail-closed (`POLICY_UNAVAILABLE`)
- approval state transitions + replay/idempotency checks
- redaction regression (no raw sensitive strings in audit artifacts)
- sandbox governance deny/approval enforcement
- team resume path only proceeds with executed and not yet consumed approvals
- SQLite write path remains stable under parallel memory writes
- checkpoint writes remain stable under concurrent updates
- when `IMPERAOS_AUDIT_SIGNING_KEY` is set, `audit_envelope.integrity.signature` must be populated

## 7. Pre-Production Field Validation

The deterministic mock benchmark is required in CI.

Before production rollout, run one live provider team E2E in target environment:

```bash
uv run imperaos team run --spec team.yaml --once "production-readiness live check" --profile restricted --provider ollama --json
```

This live run is the final field validation and remains provider/model dependent.
