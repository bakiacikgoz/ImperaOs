# Design Partner Pilot Field Runbook

This runbook is for a governed pilot rehearsal. It does not authorize target-customer execution or live computer-use.

## Preflight

1. Confirm the branch has passed `make governed-pilot-workflow-gate`.
2. Confirm `make memory-runtime-policy-gate` and provider runtime gates are still green.
3. Confirm the operator understands that the workflow is deterministic dry-run evidence only.
4. Confirm no live provider credentials or live computer-use flags are required.

## Run

```bash
uv run imperaos pilot workflow run \
  --spec examples/pilot_workflows/enterprise_governed_memory_provider.yaml \
  --profile enterprise \
  --output-root artifacts/governed-pilot-workflow
```

Then verify:

```bash
uv run imperaos pilot workflow verify \
  --report artifacts/governed-pilot-workflow/latest/report.json
```

## Operator Panel

Open the Operator Panel preview and use the `Governed Pilot Workflow` navigation item. The page should show:

- workflow id and run id,
- `hash_only` evidence mode,
- `rawPersistence=false`,
- Claim Guard status,
- verifier status,
- blocked live/public claims.

## Stop Conditions

Stop the pilot rehearsal if any of these appear:

- verifier status is `fail`,
- raw leak is detected,
- provider mode is not `dry_run`,
- an unsupported claim is allowed,
- any mutation has executed.

Target evidence collection must use the separate target-evidence closure process.
