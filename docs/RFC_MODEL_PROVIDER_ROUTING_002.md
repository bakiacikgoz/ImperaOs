# RFC 002: Policy-Aware Provider Routing Shadow Mode

Status: experimental shadow mode.

This RFC introduces policy-aware provider recommendations without changing actual
execution provider selection. The router evaluates task type, data class, required
capabilities, provider policy, data boundary, and fallback priority, then emits a
shadow-only recommendation.

The CLI surface is:

```bash
uv run python -m imperaos provider route simulate \
  --profile enterprise \
  --data-class confidential \
  --json
```

Key constraints:

- `shadow_only` is always `true`.
- The decision never overrides `llm_provider`, `provider_id`, or runtime execution path.
- Public cloud providers remain blocked for confidential and higher-risk data classes.
- Required capabilities filter candidates before scoring.
- Local providers score highest, then internal/private cloud, then public cloud.

The output includes allowed providers, blocked providers, recommended provider,
fallback candidate, policy reason, and optional evidence path when `--write-evidence`
is used.

Enforcement is out of scope for this sprint. `IMPERAOS_PROVIDER_ROUTER_ENFORCE` remains
unused and must default off.
