# RFC: Model Provider Governance v1

## Status

Accepted for implementation as a guarded vertical slice.

## Product Boundary

ImperaOS remains local-first and private by default. Remote model providers are
disabled unless an operator explicitly enables provider registry entries,
configures secret references through environment variables, and passes provider
policy checks.

The product is provider-agnostic by design: local, internal, OpenAI-compatible,
and selected cloud providers can be represented by the same registry, policy,
redaction, evidence, and Operator Panel surfaces.

## Initial Scope

- Provider registry and policy contracts.
- Synthetic local providers for current Ollama and Transformers flows.
- Config-file based registry with env-var secret references only.
- OpenAI-compatible adapter for internal gateways and compatible remote APIs.
- Policy simulation, doctor, model discovery, redaction, and evidence envelopes.

## Non Goals

- Storing raw API keys in config or UI.
- Enabling public cloud providers by default.
- Native provider-specific SDKs.
- Direct execution of provider-returned tool calls.
- Multi-tenant hosted control plane.

## Security Defaults

- `remote_providers_enabled=false`.
- Public cloud providers only receive `public` data by default.
- `secret`, `credential`, `payment`, and `raw_pii` classes always block egress.
- Provider tool calls are proposal-only.
- Remote provider evidence envelopes never include raw prompts, raw responses,
  authorization headers, or API key values.

## Rollback

Disable `remote_providers_enabled`, remove provider registry config, and fall
back to legacy `llm_provider` and `fallback_provider` fields.
