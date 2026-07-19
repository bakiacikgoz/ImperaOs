# Local Enterprise Setup

Developer baseline:

```bash
uv sync --python 3.11 --extra dev
corepack pnpm --dir apps/operator-panel install --frozen-lockfile
uv run imperaos setup first-run --profile enterprise --mode local-enterprise --json
```

Use `product demo` commands for deterministic first-use smoke before connecting a
real provider.
