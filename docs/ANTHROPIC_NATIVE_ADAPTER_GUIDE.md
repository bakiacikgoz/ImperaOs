# Anthropic Native Adapter Operator Guide

Scope: Anthropic Messages native adapter V2.1 preview.

## Status

- Adapter kind: `anthropic_messages`
- Runtime status: `canary_only`
- Default config state: disabled
- Live provider calls: disabled unless all live canary controls are explicitly enabled
- Evidence mode: offline fixture or canary evidence only

This guide does not approve production routing. It documents the preview surface operators can inspect before a future graduation review.

## Safety Defaults

- Storage policy is `hash_only/raw_disabled`.
- Raw prompt, raw response, headers, and provider payload persistence are rejected.
- Anthropic server tools and high-risk client tools are denied by default.
- Custom/client tool requests are normalized to `ProviderToolProposal` only.
- The adapter does not execute proposed tools and does not continue a `tool_result` loop.
- CI and Makefile gates run offline by default.

## Operator Panel Trust Fields

The provider registry payload uses `contractVersion="operator-panel.assistant-provider-models/v4"`.

Expected Anthropic preview row:

- `kind: anthropic_messages`
- `native: anthropic_messages: canary_only`
- `storage: hash_only/raw_disabled`
- `server_tools: denied`
- `custom_tools: proposal_only`
- `client_tools: proposal_only`
- `tool_result_loop: not_implemented`
- `stop_reason: fail_closed`
- `live_canary: false`

Operators should treat missing native metadata as not approved for native routing.

## Live Canary Boundary

Do not run a live Anthropic canary unless all of these are true:

- CLI intent is explicit for the run.
- `IMPERAOS_PROVIDER_LIVE_CANARY=1` is set.
- `IMPERAOS_ANTHROPIC_LIVE_CANARY=1` is set.
- `ANTHROPIC_API_KEY` exists only as an environment variable reference.
- host allowlist and budget checks pass.
- output is isolated as canary evidence, not production approval.

## Blockers

Block release or rollout if any of these occur:

- raw Anthropic payloads are persisted
- a server-side Anthropic tool is accepted
- a provider-returned tool request is executed locally by the adapter
- `pause_turn`, incomplete `tool_use`, unknown content blocks, or unknown stop reasons are accepted as success
- native conformance reports an unexpected failure
- evidence verification finds secret-like or raw content markers
