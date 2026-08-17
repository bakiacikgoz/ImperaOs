# Model Provider Native Adapter V2 Operator Guide

Scope: OpenAI Responses native adapter vertical slice, plus the V2.1 Anthropic Messages preview.

## Status

- Adapter kinds: `openai_responses`, `anthropic_messages`
- Runtime status: `canary_only`
- Default config state: disabled
- Live provider calls: disabled unless an operator explicitly opts in through the live canary controls
- Evidence mode: fixture or preview evidence only by default

This guide does not approve production routing for the native adapter. It describes the preview surface and the checks operators must see before a future graduation review.

## Safety Defaults

- OpenAI Responses storage policy is `hash_only/store=false`.
- Anthropic Messages storage policy is `hash_only/raw_disabled`.
- Raw prompt and raw response persistence is disabled.
- Provider-hosted tools, built-in tools, MCP tools, file search, web search, web fetch, code execution, computer-use, bash, and text editor tools are denied by default.
- Custom function and client tools are normalized as proposals only. The adapter must not execute proposed tools.
- Anthropic `tool_result` continuation loops are not implemented in V2.1 and fail closed.
- Parallel tool calls are disabled in the native request payload.
- Live canary execution requires the existing double opt-in controls used by provider governance.

## Operator Panel Trust Fields

The provider registry payload uses `contractVersion="operator-panel.assistant-provider-models/v4"` for the native trust surface.

Expected OpenAI Responses preview row:

- `kind: openai_responses`
- `native: openai_responses: canary_only`
- `storage: hash_only/store=false`
- `server_tools: denied`
- `custom_tools: proposal_only`
- `source: fixture` or `source: preview`

Expected Anthropic Messages preview row:

- `kind: anthropic_messages`
- `native: anthropic_messages: canary_only`
- `storage: hash_only/raw_disabled`
- `server_tools: denied`
- `custom_tools: proposal_only`
- `client_tools: proposal_only`
- `tool_result_loop: not_implemented`
- `stop_reason: fail_closed`
- `live_canary: false`

Operators should treat any missing native metadata as not approved for native routing.

## CLI Checks

Run the offline native conformance matrix:

```bash
uv run python -m imperaos provider native conformance run \
  --profile enterprise \
  --provider-kind all \
  --offline \
  --json
```

Verify the saved native evidence:

```bash
uv run python -m imperaos provider native conformance verify \
  --input artifacts/model-provider-governance/native-v2/anthropic_messages_native_adapter_report.json \
  --json
```

Run the full native adapter gate:

```bash
uv run python scripts/run_provider_native_adapter_gate.py --profile enterprise --json
```

The gate must report:

- `status=pass`
- at least 20 total conformance cases across OpenAI and Anthropic
- no unexpected failures
- no live canary attempt by default
- evidence verification passed

## Live Canary Boundary

Do not run a live OpenAI Responses canary unless all of these are true:

- operator intent is explicit for this run
- live canary flags are set deliberately
- budget and host allowlist checks pass
- evidence output path is isolated for review
- the result is treated as canary evidence, not production approval

Do not run a live Anthropic Messages canary unless `IMPERAOS_PROVIDER_LIVE_CANARY=1`,
`IMPERAOS_ANTHROPIC_LIVE_CANARY=1`, explicit CLI live intent, budget checks, and host
allowlist checks all pass.

## Blockers

Block release or rollout if any of these occur:

- `store=false` is not present in generated native payloads
- raw prompt or raw response content appears in evidence
- built-in, MCP, server-side, web search, file search, or computer-use tools are accepted
- custom function tool proposals are executed locally by the adapter
- Anthropic `tool_result` loops, `pause_turn`, unknown stop reasons, or incomplete `tool_use` blocks are accepted as success
- secret-like output is persisted or returned as a successful case
- native conformance reports any unexpected failure
