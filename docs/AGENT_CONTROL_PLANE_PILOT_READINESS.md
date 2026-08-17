# Agent Control Plane Pilot Readiness

This document records the v1.0 pilot-readiness release candidate for the
self-hosted Agent Control Plane Console.

## Status

The local pilot-readiness gate passed on 2026-06-01.

```bash
make pilot-readiness-gate
```

The generated release-pack summary is:

```text
artifacts/pilot-readiness/PILOT_READINESS_REPORT.md
artifacts/pilot-readiness/control-plane-snapshot.json
artifacts/pilot-readiness/claim-guard-matrix.json
artifacts/pilot-readiness/reports/operator-panel-productized-pages.json
artifacts/pilot-readiness/tauri-smoke/report.json
```

## Scope Completed

- Runtime truth and snapshot contracts distinguish `preview_fixture`,
  `tauri_live`, `cli_live`, `stale_cache`, and `error`.
- Operator Panel pages load from the shared `ControlPlaneSnapshot` contract.
- Primary user surfaces use cards, lists, timelines, and decision copy instead
  of raw JSON dumps.
- Raw JSON remains available only through advanced/debug surfaces.
- Operations, Logs, Reports, Alerts, Plans, Users, Roles, and Policy Packs have
  pilot-oriented read-only governance models.
- Reason codes have localized human explanations for English and Turkish.
- Evidence packs can be verified from the Operator Panel and by CLI.
- The pilot demo flow is covered by Playwright E2E.
- Tauri bridge contract smoke and Rust bridge tests are included in the gate.
- The release pack writes a claim-guard matrix and readiness report.

## Claim Boundaries

The supported claim is narrow:

> ImperaOS can be shown as a constrained self-hosted Agent Control Plane pilot
> for policy, approval, identity, audit, replay, and signed evidence workflows.

The following claims remain blocked or conditional:

| Claim | Status | Boundary |
|---|---|---|
| Self-hosted Agent Control Plane pilot | conditional/allowed when current gates and signed evidence pass | Use only for the scoped enterprise pilot environment. |
| Live computer-use execution | blocked | Must remain qualification-gated and fail-closed. |
| Public desktop installer release | blocked | Requires signing, notarization, and clean-machine evidence. |
| Enterprise Hat A readiness | conditional unless target-environment signed qualification evidence is present | Do not convert preview fixture evidence into a live claim. |
| Multi-tenant SaaS | deferred | Out of scope for this release candidate. |

The latest generated claim guard artifact is:

```text
artifacts/pilot-readiness/claim-guard-matrix.json
```

It records `computer-use` as `blocked` with reason code `MACOS_LIVE_DISABLED`.

## Pilot Readiness Checklist

- [x] Runtime truth snapshot contract exists.
- [x] Browser preview data is explicitly marked as preview data.
- [x] Silent fallback is represented by `isSilentFallback` and fails gates when
  live data is expected.
- [x] Agent registry shows the governed ops agent.
- [x] Policy simulation shows `require_approval`.
- [x] Approval-heavy run is visible without live computer-use.
- [x] Approve and execute UI states are covered by deterministic E2E.
- [x] Evidence pack verify passes in UI and gate coverage.
- [x] Support bundle export is represented without exposing secrets.
- [x] Primary UI raw JSON gate passes.
- [x] i18n dictionary and reason-code parity gates pass.
- [x] Productized pages manifest includes screenshot-backed coverage for all
  visible routes.
- [x] Tauri bridge smoke report is generated.
- [x] `make pilot-readiness-gate` passes.
- [ ] Target customer environment has fresh signed enterprise qualification
  evidence.
- [ ] Public desktop installer has signing/notarization/clean-machine evidence.

## Required Gates

Run the full gate before every pilot handoff:

```bash
make pilot-readiness-gate
```

The full gate covers:

- Python lint, tests, compile, and snapshot CLI.
- Operator Panel unit tests, lint, build, E2E, productized pages, no-primary-raw
  JSON, and i18n coverage.
- Rust bridge tests.
- Agent Control Plane v1 gate.
- Tauri smoke report.
- Pilot readiness artifact assertion.
- Evidence pack gate.
- `git diff --check`.

Focused gates are also available:

```bash
make control-plane-snapshot-gate
make evidence-pack-gate
make operator-panel-tauri-smoke
corepack pnpm --dir apps/operator-panel pilot:assert
```

## Release Pack Contents

The pilot readiness artifact root is intentionally ignored by git and must be
regenerated for each release candidate:

```text
artifacts/pilot-readiness/
  PILOT_READINESS_REPORT.md
  control-plane-snapshot.json
  claim-guard-matrix.json
  evidence/
  reports/
  screenshots/
  support-bundle/
  tauri-smoke/
```

The release-pack support artifacts are:

```text
artifacts/release-pack/control-plane-v1/
  control_plane_claim_matrix.json
  control_plane_readiness_report.json
  ga_readiness_report.json
  security_posture.json
  support_bundle_manifest.json
```

## Demo Flow

The deterministic UI demo is documented in
`docs/PILOT_DEMO_RUNBOOK.md`. The short version is:

1. Open Dashboard.
2. Open Agents and confirm the governed ops agent.
3. Open Policy Simulation and confirm `require_approval`.
4. Open Runs and confirm the governed run.
5. Open Approvals, approve, and execute.
6. Open Signed Evidence and verify the latest evidence pack.
7. Open Reports and confirm evidence/support outputs.
8. Open Operations and export the support bundle.
9. Open Execution Surfaces and confirm computer-use remains blocked.

## Operating Rules

- Never label `preview_fixture` output as live pilot evidence.
- Never enable live computer-use from this release candidate.
- Keep destructive operations disabled or dry-run unless a later audited scope
  explicitly enables them.
- Treat missing metrics, missing signatures, stale snapshots, and silent fallback
  as readiness blockers.
- Regenerate artifacts and rerun `make pilot-readiness-gate` after any code or
  fixture change that affects the Operator Panel, control-plane snapshot,
  evidence, claims, i18n, or Tauri bridge.
# Governed Pilot Workflow Closure

Design-partner pilot readiness must include a passing governed pilot workflow report before target evidence is treated as release closure evidence. The workflow is deterministic and dry-run only; target customer execution, public desktop installer claims, live computer-use claims, and multi-tenant cloud claims remain out of scope unless separate signed evidence exists.

Primary command:

```bash
make governed-pilot-workflow-gate
```
