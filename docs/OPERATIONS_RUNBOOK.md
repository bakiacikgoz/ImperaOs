# OPERATIONS_RUNBOOK

## 1. Resolve Config

```bash
uv run imperaos config resolve --profile balanced --json
```

## 2. Health Check

```bash
uv run imperaos doctor --profile balanced
uv run imperaos doctor --profile balanced --provider auto --model qwen3.5:4b --hf-model-id Qwen/Qwen3.5-4B-Instruct
```

## 3. Functional Smoke

```bash
uv run imperaos chat --profile balanced --once "selam" --stream --fast-path
uv run imperaos chat --profile balanced --provider ollama --model qwen3.5:4b --once "uzun plan çıkar"
uv run imperaos benchmark smoke --mode all --profile balanced
```

## 4. Quality Ablation

```bash
uv run imperaos benchmark ablation --mode all --profile balanced --suite quality
```

## 5. Energy Check

```bash
uv run imperaos benchmark energy --profile balanced --energy-mode measured
uv run imperaos benchmark energy --profile balanced --energy-mode measured --provider auto --model qwen3.5:4b --hf-model-id Qwen/Qwen3.5-4B-Instruct
```

If measured mode cannot run due permissions, confirm deterministic `error_reason` in JSON output.

## 6. Research Calibration

```bash
uv run imperaos research train-router --dataset .imperaos/research/router_dataset.jsonl
uv run imperaos research eval-router --dataset .imperaos/research/router_dataset.jsonl
```

## 7. Artifact Verification

Check that all files exist:

- `artifacts/status.json`
- `artifacts/test_summary.json`
- `artifacts/benchmark_summary.json`
- `artifacts/router_shadow_summary.json`
- `artifacts/research_summary.json`

## 8. Operator Panel Compatibility Check

```bash
uv run imperaos --version
uv run imperaos operator capabilities --json
uv run imperaos team list --root-dir .imperaos/team/jobs --json
```

If capabilities contract or command flags are missing, keep UI mutations disabled.

## 8.1 Operator Validation Dry-Run

Run the operator-facing validation drill before asking an independent
non-developer operator for sign-off:

```bash
uv run python scripts/run_operator_validation_drill.py \
  --output-root artifacts/readiness/2026-05-13/operator_validation_drill
```

The drill writes `operator_validation_report.json` and
`OPERATOR_VALIDATION_REPORT.md`. Without `--operator-attestation`, this is only
an automated proxy validation and must not be described as independent
non-developer operator attestation.

For the human sign-off flow, copy
`docs/templates/non_developer_operator_attestation.template.json` to the
readiness evidence directory, have an independent non-developer operator fill it
out, then rerun:

```bash
uv run python scripts/run_operator_validation_drill.py \
  --output-root artifacts/readiness/2026-05-13/operator_validation_drill_attested \
  --operator-attestation artifacts/readiness/2026-05-13/operator_validation_attestation.json
```

The attested report may claim
`validation_scope=non_developer_operator_attested` only if the template is fully
filled by that operator and the command/evidence checks still pass. See
`docs/NON_DEVELOPER_OPERATOR_ATTESTATION.md` for the exact rules.

## 8.2 Resilient Long Soak Launch

For long final soak windows, launch from an isolated `/private/tmp` workspace
instead of the interactive project directory:

```bash
scripts/launch_resilient_qualification_soak.sh \
  --hours 72 \
  --valid-hours 96 \
  --run-id final72h-YYYYMMDDTHHMMSSZ
```

The launcher copies the runtime-critical workspace files, refreshes the local
enterprise identity assertion inside the isolated workspace, runs a supervisor
dry-run, submits the actual soak through macOS `launchd`, and waits for a fresh
heartbeat before reporting success.

Live monitor:

```bash
scripts/watch_qualification_soak.sh \
  --run-dir /private/tmp/imperaos_soak_final72h-YYYYMMDDTHHMMSSZ/artifacts/qualification/supervisor/final72h-YYYYMMDDTHHMMSSZ
```

Do not claim final-GA pass until the long soak completes and the resulting
qualification report, signature verification, and GA readiness addendum are
published.

## 9. Incident Hints

- Planner fallback spikes: inspect `planner_parse_fail_rate` and `planner_fallback_rate`.
- Router drift: inspect `router_shadow_agreement_rate` and disagreement samples.
- Fast-path quality drift: inspect `fast_path_regret_rate`.
- Unexpected memory growth: verify `memory_ttl_days`, dedup hits, prune behavior.

## 10. Team Runtime Pilot Runbook

### Preflight

Run the release-blocking gate before any controlled pilot:

```bash
uv run ruff check .
uv run pytest -q \
  tests/test_team_governance.py \
  tests/test_team_memory_fail_closed.py \
  tests/test_team_audit_envelope.py \
  tests/test_team_cli.py \
  tests/test_team_pilot_gate.py
uv run imperaos team validate --spec examples/team/restricted_pilot.yaml --json
uv run imperaos team pilot-check \
  --spec examples/team/restricted_pilot.yaml \
  --profile restricted \
  --mode deterministic \
  --report artifacts/team_pilot_report.json \
  --json
```

Gate outcome requirements:

- `team pilot-check` exits `0`.
- `artifacts/team_pilot_report.json` exists and reports `overall_status=pass`.
- clean `team replay --verify` passes for the smoke artifacts.
- tamper probe fails verification.
- approval reuse probe is blocked.
- scope isolation probe fails closed.
- bounded-concurrency checks report `stale_approval_count=0` and `memory_conflict_count=0`.

Approval lifecycle for Team Runtime is `pending -> approved -> executed -> consumed`.
`approved` alone is not sufficient for resume or override use.
Approval-gated resume is bound to a frozen execution contract. If memory view or canonical task input drifts, resume must stop with `STALE_APPROVAL_SNAPSHOT`.
Shared `memory_target` writes use optimistic version checks and reject on conflict; there is no last-write-wins fallback in restricted pilot mode.

### Live Pilot Rehearsal

Before a real restricted pilot, run one live-provider rehearsal in the target environment:

```bash
uv run imperaos team pilot-check \
  --spec examples/team/restricted_pilot_live.yaml \
  --profile restricted \
  --mode live-provider \
  --provider auto \
  --report artifacts/team_pilot_live_report.json \
  --json
```

Use the same spec, profile, and artifact retention path that will be used for the pilot window.

### Artifact Retention

Retain these artifacts for every pilot check and pilot rehearsal:

- `artifacts/team_pilot_report.json`
- `artifacts/team_pilot_live_report.json` when a live rehearsal is run
- `.imperaos/team/jobs/<job_id>/status.json`
- `.imperaos/team/jobs/<job_id>/events.jsonl`
- `.imperaos/team/jobs/<job_id>/tasks.json`
- `.imperaos/team/jobs/<job_id>/handoffs.json`
- `.imperaos/team/jobs/<job_id>/audit_envelope.json`
- `artifacts/team_summary.json`
- `uv run imperaos config resolve --profile restricted --json` output
- approval store snapshot or the approval summary embedded in the pilot report

### Incident Response

- Replay verify fails:
  - stop the pilot immediately
  - export the affected job artifacts
  - preserve the failing `team replay --verify` output
  - open a root-cause item before any rerun
- Approval mismatch or approval reuse attempt succeeds:
  - mark the pilot `No-Go`
  - invalidate outstanding approvals for the affected run set
  - do not reuse the blocked source jobs
- Audit inconsistency or missing causal refs:
  - stop the pilot
  - copy artifacts to immutable storage
  - treat the release candidate as invalid until fixed
- Scope violation or unexpected memory write succeeds:
  - disable Team Runtime immediately
  - revert to the core single-agent path only

### Rollback And Kill-Switch

The supported hard stop for this slice is disabling Team Runtime entirely:

```bash
IMPERAOS_TEAM_ENABLED=false uv run imperaos team run --spec examples/team/restricted_pilot.yaml --once "pilot disable check" --profile restricted --json
```

Expected result: the command fails with Team Runtime disabled and no new team delegation starts.

Operational fallback for this slice is the core single-agent runtime, not a degraded team mode.
`IMPERAOS_TEAM_MAX_PARALLEL_TASKS=1` may help diagnosis, but it is not a rollback mechanism.
If bounded concurrency repeatedly falls back to serialized execution, treat that as a pilot warning. If drift/conflict repeats in the same workload, force serial diagnosis first; if it persists, disable Team Runtime entirely.

### Stop Conditions

Do not start or continue a pilot if any of the following occur:

- any deterministic `team pilot-check` failure
- nondeterministic smoke behavior across repeated deterministic runs
- replay or audit inconsistency
- approval reuse or consumed-state bypass
- scope isolation bypass

## 11. Enterprise Deployment Runbook

### Preflight

```bash
uv run python scripts/prepare_enterprise_fixture.py --root .
uv run imperaos security baseline --profile enterprise --json
uv run imperaos auth whoami --profile enterprise --json
uv run imperaos auth check --profile enterprise --permission runtime.run --json
uv run imperaos metrics snapshot --profile enterprise --json
uv run imperaos qualification run --profile enterprise --mode mixed --soak-hours 6 --output-root artifacts/qualification --json
uv run imperaos ga readiness --profile enterprise --report artifacts/ga_readiness_report.json --json
```

### Required Operator Drills

- `uv run imperaos keys status --profile enterprise --json`
- `uv run imperaos keys rotate-plan --profile enterprise --json`
- `uv run imperaos migrate plan --profile enterprise --json`
- `uv run imperaos backup create --profile enterprise --json`
- `uv run imperaos restore verify --profile enterprise --backup-dir <backup_dir> --json`
- `uv run imperaos support bundle export --profile enterprise --json`
- `uv run imperaos qualification run --profile enterprise --mode mixed --soak-hours 6 --output-root artifacts/qualification --json`

### Evidence To Retain

- `artifacts/security_posture.json`
- `artifacts/metrics_snapshot.json`
- `artifacts/qualification_report.json`
- `artifacts/QUALIFICATION_REPORT.md`
- `artifacts/ga_readiness_report.json`
- `artifacts/GA_READINESS_REPORT.md`
- backup manifest generated by `backup create`
- signed support bundle manifest
- key status and rotation plan outputs

### Incident Guidance

- signature verify failure:
  - treat as `SEV0`
  - stop export-driven workflows
  - rotate or revoke the affected key only after preserving evidence
- unauthorized mutation or RBAC deny mismatch:
  - treat as `SEV0`
  - disable enterprise mutation paths until identity enforcement is revalidated
- restore verification failure:
  - treat as `SEV1`
  - block upgrade or rollback completion
- high fallback/conflict/serialization rate:
  - treat as `SEV2`
  - reduce workload, review qualification envelope, rerun qualification if the support boundary is unclear, and rerun metrics snapshot

### Kill-Switch And Safe Fallback

- disable Team Runtime entirely with `IMPERAOS_TEAM_ENABLED=false`
- keep enterprise CLI controls read-only until identity and signing checks return to `pass`
- do not claim GA readiness while `ga readiness` is `yellow` or `red`
- do not promote enterprise deployment claims without a signed `qualification_report.json`

## 12. Vision-First Computer-Use Operations

### Default Posture

The `[computer_use]` profile block defaults to:

```toml
runtime_mode = "legacy_pilot"
vision_enabled = false
raw_screenshot_retention = "disabled"
terminal_control = "deny"
platform_qualification_required = true
```

### Operator Checks

```bash
uv run imperaos operator capabilities --json
uv run imperaos computer-use run --once "read current screen" --runtime vision-first --json
```

Expected result without a configured vision provider: fail-closed with `VISION_RUNTIME_NOT_CONFIGURED` or `VISION_PROVIDER_UNAVAILABLE`; no raw screenshots are persisted.

### Stop Conditions

- raw screenshots appear without explicit debug opt-in
- Windows reports live execution enabled without signed qualification
- terminal control is enabled outside a reviewed policy change
- sensitive surface detection does not stop execution
- replay hash-chain verification fails
## Supervised macOS Vision Pilot

Use the vision-first runtime only as a supervised macOS pilot. Start with deterministic qualification:

```bash
uv run imperaos computer-use qualify --runtime vision-first --suite smoke --mode deterministic --json
```

Before any live macOS run, inspect readiness:

```bash
uv run imperaos computer-use vision doctor --profile balanced --json
```

Do not automate macOS Screen Recording or Accessibility permission grants. If readiness reports missing permissions, the operator must grant them manually in macOS Privacy & Security. Windows live computer-use remains disabled with `WINDOWS_COMPUTER_USE_NOT_QUALIFIED`.
