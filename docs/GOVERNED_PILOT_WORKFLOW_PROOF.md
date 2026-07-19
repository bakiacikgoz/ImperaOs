# Governed Pilot Workflow Proof

The governed pilot workflow is the release-closure proof that the local Agent Control Plane can run a design-partner style workflow without live provider calls, live computer-use, destructive mutation, raw memory persistence, or raw prompt/response evidence.

## Scope

- Memory runtime policy is exercised through the deterministic workspace fixture.
- Provider execution uses the existing provider dry-run coordinator.
- Approval-sensitive work remains proposal-only; executed mutations must stay at `0`.
- Evidence is hash-only. Reports expose hashes, paths, statuses, reason codes, and counts only.
- Unsupported live claims remain blocked by Claim Guard.

Out of scope:

- Target customer environment execution.
- Public desktop installer claims.
- Live macOS, Windows, or Linux computer-use claims.
- Multi-tenant cloud control-plane claims.

## Commands

```bash
uv run imperaos pilot workflow validate \
  --spec examples/pilot_workflows/enterprise_governed_memory_provider.yaml

uv run imperaos pilot workflow run \
  --spec examples/pilot_workflows/enterprise_governed_memory_provider.yaml \
  --profile enterprise \
  --output-root artifacts/governed-pilot-workflow

uv run imperaos pilot workflow verify \
  --report artifacts/governed-pilot-workflow/latest/report.json

make governed-pilot-workflow-gate
```

The same commands are also available under `control-plane pilot workflow`.

## Artifacts

- `artifacts/governed-pilot-workflow/<run-id>/report.json`
- `artifacts/governed-pilot-workflow/<run-id>/REPORT.md`
- `artifacts/governed-pilot-workflow/<run-id>/evidence_manifest.json`
- `artifacts/governed-pilot-workflow/<run-id>/verification.json`
- `artifacts/governed-pilot-workflow/latest/*`

The Control Plane snapshot exposes the latest result as `governedPilotWorkflow`.

## Acceptance Criteria

- Workflow validation passes.
- Workflow report status is `pass` or explicitly `conditional`.
- Verifier status is `pass`.
- `rawPersistence` is `false`.
- `rawLeakDetected` is `false`.
- Provider runtime mode is `dry_run`.
- Approval evidence reports `executedMutations=0`.
- Unsupported claims are not allowed.
