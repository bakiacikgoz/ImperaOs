# First Real Use Workflow

Use this workflow for a local enterprise smoke:

```bash
uv run imperaos setup first-run --profile enterprise --mode local-enterprise --json
uv run imperaos product demo run-governed-workflow --profile enterprise --mode dry-run --json
uv run imperaos product demo memory-smoke --profile enterprise --workspace-id pilot-workspace --json
```

The default governed workflow mode is deterministic dry-run. Real provider mode
must be selected explicitly and remains governed by provider policy.
