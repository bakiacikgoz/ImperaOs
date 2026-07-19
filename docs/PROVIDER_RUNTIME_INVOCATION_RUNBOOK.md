# Provider Runtime Invocation Runbook

Provider runtime invocation starts with dry-run evidence, not live API calls.

Run a dry-run invocation:

```bash
uv run imperaos provider invoke \
  --provider openai_responses \
  --model gpt-placeholder \
  --profile enterprise \
  --mode dry-run \
  --once "Inspect service alerts and draft read-only triage summary" \
  --json
```

Run the read-only workflow proof:

```bash
uv run python scripts/run_provider_runtime_workflow_proof.py \
  --profile enterprise \
  --provider openai_responses \
  --mode dry-run \
  --output-root artifacts/provider-runtime/workflow-proof \
  --json
```

Operational rules:

- `dry_run` never performs an external provider API call.
- `canary_live` requires `IMPERAOS_PROVIDER_LIVE_CANARY_OPT_IN=1` plus the
  matching provider credential, and remains blocked in CI.
- Evidence artifacts contain hashes, policy decision metadata, tool policy, and
  reason codes only.
- Raw prompts, raw responses, API keys, bearer tokens, and full request bodies
  must not appear in stdout, artifacts, support bundles, or Operator Panel
  primary surfaces.
- Mutating actions are converted to proposal-only workflow entries and require
  approval lifecycle handling before any future execution path can exist.
