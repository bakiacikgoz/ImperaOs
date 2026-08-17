# Provider Governance

Provider Governance V1 keeps external model providers behind the Agent Control
Plane trust boundary. External providers start canary-only, use offline
conformance by default, and never persist raw prompts, raw responses, API keys or
Authorization headers in evidence artifacts.

## Contract

The snapshot section is `providerGovernance` with contract version
`control-plane.provider-governance/v1`.

Provider entries expose:

- `providerKind`
- `displayName`
- `status`
- `credentialState`
- `canaryOnly`
- `serverToolsPolicy`
- `customToolsPolicy`
- `retentionPolicy`
- `lastConformanceStatus`
- `blockingReasons`

External providers use these defaults:

- `canaryOnly=true`
- `serverToolsPolicy=denied`
- `customToolsPolicy=proposal_only`
- `retentionPolicy=hash_only_store_false`

## OpenAI Responses Closure

`openai_responses` is implemented as a native offline conformance slice. The
request builder enforces `store=false`, `parallel_tool_calls=false`, hash-only
evidence metadata, server tool denial, and custom tool proposal-only mode.

The adapter does not call the OpenAI API in CI. Conformance fixtures exercise the
native request shape and policy evaluator before any outbound call would be
allowed.

## Anthropic Messages Slice

`anthropic_messages` is implemented as a second native adapter over the shared
provider governance envelope. It builds the Messages request shape, retains
provider-specific metadata, and shares the same fail-closed policy defaults as
OpenAI.

The Anthropic slice is offline-only in this phase. Missing credentials are
reported as `blocked_external_credentials` without exposing secret values.

## CLI

```bash
uv run imperaos provider registry --profile enterprise --json
uv run imperaos provider inspect --provider openai_responses --profile enterprise --json
uv run imperaos provider native conformance --provider openai_responses --profile enterprise --offline --json
uv run imperaos provider native conformance --provider anthropic_messages --profile enterprise --offline --json
uv run python scripts/run_provider_native_adapter_gate.py --profile enterprise --json
```

## Gates

```bash
make provider-native-gate
make design-partner-rc-gate
make pilot-readiness-gate
```

`make provider-native-gate` writes hash-only conformance reports under
`artifacts/provider-native/`. Design Partner RC pack generation writes provider
governance conformance reports under
`artifacts/design-partner-rc/provider-governance/`.

## Boundaries

This phase does not enable live computer-use, a public desktop installer release,
unrestricted external provider execution, or irreversible mutation execution.
Custom tools remain proposals until a separate approval/runtime gate executes
them.
