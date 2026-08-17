# Model Provider Governance

ImperaOS / ImperaOS can represent local, internal, and remote model providers
behind one governance layer. Remote calls are opt-in and fail closed.

## No-Ship Conditions

- A raw API key, bearer token, or authorization header appears in logs,
  artifacts, UI payloads, support bundles, or errors.
- Public cloud providers can receive `internal`, `confidential`, `regulated`,
  `raw_pii`, `secret`, `credential`, or `payment` data under default policy.
- A disabled provider can be called.
- A remote provider can be called while `remote_providers_enabled=false`.
- A provider tool call executes directly instead of entering proposal or
  approval flow.
- Provider call envelopes contain raw prompt or raw response text.

## Data Boundary Defaults

| Boundary | Default allowed data |
|---|---|
| local | public, internal, confidential, regulated, pii_redacted |
| internal | public, internal |
| private_cloud | public, internal |
| public_cloud | public |
| aggregator | public |
| unknown | none |

## Secret Handling

Provider config stores only secret references such as `api_key_env`. Operators
set the actual value outside the repo. Doctor reports whether the referenced env
var is present without printing the value.
