# Model Provider Operator Guide

## Inspect Providers

```bash
uv run imperaos provider registry list --profile balanced --json
uv run imperaos provider doctor --profile balanced --provider-id local-ollama --json
uv run imperaos provider models --profile balanced --provider all --json
```

## Simulate Policy

```bash
uv run imperaos provider policy simulate \
  --profile enterprise \
  --provider-id openai-public \
  --data-class confidential \
  --json
```

Expected default result: `PROVIDER_DATA_BOUNDARY_DENIED`.

## Enable A Remote Provider

1. Add a provider record to `config/providers.toml`.
2. Store only `api_key_env`, never the key value.
3. Set the referenced environment variable outside the repository.
4. Set `remote_providers_enabled=true` only after policy simulation passes.
5. Run `provider doctor` and a dry-run provider call.

## Incident Response

If egress policy, fallback policy, or secret handling is suspected to be unsafe:

1. Set `remote_providers_enabled=false`.
2. Disable the provider record.
3. Preserve artifacts for review.
4. Rotate any possibly exposed credentials.
5. Re-run `make provider-governance-gate`.
