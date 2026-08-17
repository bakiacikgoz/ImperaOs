# Cross-Platform Release Gate Runbook

This runbook is the operator entrypoint for RC evidence gates on Windows, macOS, and Linux.

## Official Command

```bash
uv run python scripts/run_rc_evidence_orchestrator_gate.py --profile enterprise --json
```

The script runs backend tests, regenerates release and Control Plane schemas, plans and runs `mainline-rc` gates, verifies and exports the evidence ledger, reads the Control Plane release-gate snapshot, runs targeted Operator Panel tests, and checks `git diff --check`.

## Optional Make Wrapper

```bash
make rc-evidence-orchestrator-gate
```

Use this only where `make` is available. The Python script remains the canonical cross-platform path.

## Manual Breakdown

```bash
uv run --extra dev python -m pytest -q tests/test_release_gate_models.py tests/test_release_gate_plan.py tests/test_release_gate_runner.py tests/test_release_gate_verifier.py tests/test_release_gate_contracts.py tests/test_rc_freeze_backfill.py tests/test_release_gate_cli.py tests/test_rc_freeze_manifest.py tests/test_control_plane_snapshot_rc_gate_evidence.py
uv run python scripts/generate_release_gate_contract_schemas.py
uv run python scripts/generate_control_plane_contract_schemas.py
uv run imperaos release gates run --target mainline-rc --profile enterprise --mode rc-focused --output-root artifacts/release-gates/mainline-rc --json
uv run imperaos release gates verify --ledger artifacts/release-gates/mainline-rc/gate_evidence_ledger.json --json
uv run imperaos release gates export --ledger artifacts/release-gates/mainline-rc/gate_evidence_ledger.json --output-root artifacts/release-gates/mainline-rc --json
uv run imperaos control-plane release gates snapshot --profile enterprise --evidence-root artifacts/release-gates/mainline-rc --json
corepack pnpm --dir apps/operator-panel exec vitest run src/rc-gate-evidence/RcGateEvidenceView.test.tsx src/rc-gate-evidence/rcGateEvidenceMappers.test.ts src/routeRegistry.test.ts src/control-plane/controlPlaneSnapshot.test.ts
corepack pnpm --dir apps/operator-panel exec playwright test e2e/rc-gate-evidence.spec.ts --pass-with-no-tests
git diff --check
```

## Failure Handling

- `blocked`: stop and fix the listed blocker.
- `conditional`: inspect the missing gate or artifact list before RC freeze promotion.
- `ready`: evidence is locally complete and can be used by the RC freeze verifier, subject to human review and remote CI.

Never bypass a raw/secret scan failure by editing the ledger manually. Regenerate evidence from the gate runner.
