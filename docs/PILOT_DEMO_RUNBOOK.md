# Pilot Demo Runbook

This runbook is for deterministic design-partner demos of the constrained
self-hosted Agent Control Plane pilot.

## Preflight

Run:

```bash
make pilot-readiness-gate
```

Then inspect:

```text
artifacts/pilot-readiness/PILOT_READINESS_REPORT.md
artifacts/pilot-readiness/claim-guard-matrix.json
artifacts/operator-panel-ui/tauri-smoke/TAURI_LAUNCHED_SMOKE.md
```

All checks in the readiness report must pass. Computer-use must remain blocked
unless a separate signed qualification scope explicitly unlocks it.

## CLI Baseline

```bash
uv run imperaos control-plane snapshot --json
uv run imperaos control-plane claims verify --profile enterprise --json
uv run python scripts/run_control_plane_demo.py --profile enterprise --json
```

Optional evidence verification:

```bash
uv run imperaos control-plane evidence verify \
  --path artifacts/control-plane/evidence/<run-id>/manifest.json \
  --profile enterprise \
  --json
```

## Operator Panel Flow

1. Open Dashboard and confirm policy, approvals, and evidence summary cards.
2. Open Agents and confirm `Governed Ops Agent`.
3. Open Policy Simulation and confirm a risky action returns
   `require_approval`.
4. Open Runs and confirm `run_20260308_0910`.
5. Open Approvals and confirm `Approve` is enabled.
6. Click `Approve`, then confirm `Approve OK`.
7. Click `Execute`, then confirm `Execute OK`.
8. Open Signed Evidence and confirm `evp-preview-run`.
9. Click `Verify latest` and confirm evidence verification completed.
10. Open Reports and confirm evidence and support bundle entries.
11. Open Operations, choose Support, and export the support bundle.
12. Open Execution Surfaces and confirm computer-use is blocked and live start
    is disabled.

This flow is covered by:

```bash
corepack pnpm --dir apps/operator-panel test:e2e -- pilot-readiness.spec.ts
```

## Speaking Boundaries

Say:

- "This is a constrained self-hosted Agent Control Plane pilot."
- "Preview fixture data is clearly labeled and is used for deterministic UI
  proof."
- "Policy, approval, audit, replay, evidence, and claim guard flows are covered
  by the gate."

Do not say:

- "Live computer-use is available."
- "The public desktop installer is ready."
- "Preview fixture output is customer live evidence."
- "Enterprise Hat A is ready without fresh signed qualification evidence from
  the target environment."
