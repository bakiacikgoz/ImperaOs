# Model Provider Live Canary Runbook

Live canary is an operator-mediated diagnostic, not a CI default.

## Default

- CI and local validation use offline fixtures.
- `PROVIDER_LIVE_CANARY_DISABLED` is the expected default reason.
- Missing provider secrets must produce skipped or denied evidence, not failure.

## Preconditions

1. Select a non-production profile and a single provider id.
2. Confirm the provider registry has `enabled = true`.
3. Confirm the provider policy allows only the intended data classes.
4. Confirm `allowed_hosts` matches the provider base URL host.
5. Confirm canary budget is greater than zero.
6. Set the required secret through the configured `api_key_env`; never write a raw secret into TOML or artifacts.
7. Set the live-canary opt-in environment variable required by the CLI surface.

## Commands

```powershell
uv run --extra dev python -m imperaos provider canary run --profile enterprise --provider openai-public --json
uv run --extra dev python -m imperaos provider canary verify --evidence-root artifacts/model-provider-governance/canary --json
```

## Evidence Rules

- Persist request and response hashes only.
- Persist status code class, latency, retry count, policy decision, network decision, and budget decision.
- Do not persist message text, provider payloads, headers, secrets, or raw response bodies.

## Abort Conditions

- Provider host is not allowlisted.
- Public cloud provider receives confidential, regulated, secret, credential, payment, raw PII, or unredacted PII data.
- Server-side tools are requested.
- Canary budget is zero or exhausted.
- Evidence verification reports a forbidden marker.
