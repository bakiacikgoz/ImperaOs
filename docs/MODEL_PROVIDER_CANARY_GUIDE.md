# Model Provider Canary Guide

Model provider canaries are controlled readiness checks for configured providers. They are
fail-closed by default and do not make live network calls unless both controls are present:

```bash
IMPERAOS_PROVIDER_LIVE_CANARY=1 uv run python -m imperaos provider canary run \
  --provider-id openai-public \
  --profile balanced \
  --data-class public \
  --allow-live \
  --json
```

Without `--allow-live` and `IMPERAOS_PROVIDER_LIVE_CANARY=1`, the command returns
`status=skipped` with `reason_code=PROVIDER_LIVE_CANARY_DISABLED`.

Evidence is written under:

```text
artifacts/model-provider-governance/canary
```

Evidence contains provider id, provider kind, boundary, risk tier, policy decision,
redaction summary, request/response hashes, latency, usage, budget decision, retry count
and error class. It must not contain raw prompt, raw response, API keys, bearer tokens,
authorization headers, PII, or confidential fixture content.

Verify evidence with:

```bash
uv run python -m imperaos provider canary verify \
  --evidence-root artifacts/model-provider-governance/canary \
  --json
```

Offline CI fixtures use:

```bash
uv run python scripts/run_provider_canary_fixture.py --profile enterprise --json
uv run python scripts/generate_provider_canary_evidence.py --profile enterprise --json
```

Public cloud canaries are limited to `public` data class. Confidential, regulated,
secret, credential, payment, and raw PII classes are denied before adapter execution.
