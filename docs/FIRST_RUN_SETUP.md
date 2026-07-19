# First-Run Setup

Run safe diagnostics:

```bash
uv run imperaos setup first-run --profile enterprise --mode local-enterprise --json
```

The command performs no destructive mutation unless a future explicit `--apply`
flow is implemented and reviewed. Current output reports checks, blocking
reasons, and next actions.
