# RFC: Anthropic Messages Native Adapter V2.1

Status: offline vertical slice implemented for preview and canary evidence only.

## Goals

- Add `anthropic_messages` as a second native provider kind.
- Exercise native adapter semantics that differ from OpenAI Responses: content blocks, `tool_use`, stop reasons, and server/client tool boundaries.
- Keep all Anthropic behavior canary-only, disabled by default, and hash-only for evidence.
- Treat every provider-returned tool request as governance evidence, not local execution.

## Non-Goals

- No production Anthropic routing approval.
- No streaming Messages implementation.
- No Anthropic server-side web search, web fetch, code execution, computer-use, bash, or text editor execution.
- No `tool_result` loop execution in this slice.
- No prompt caching, extended thinking, batch API, or live traffic in CI.

## Contract

Schemas are generated from:

- `AnthropicMessagesRequest`
- `AnthropicMessagesResult`
- `ProviderContentBlock`
- `ProviderStopReason`
- existing native policy and proposal models

Generated schema files:

- `contracts/model_providers/anthropic_messages_request.schema.json`
- `contracts/model_providers/anthropic_messages_result.schema.json`
- `contracts/model_providers/provider_content_block.schema.json`
- `contracts/model_providers/provider_stop_reason.schema.json`

## Policy Defaults

- `canary_only = true`
- raw payload persistence is rejected
- evidence stores hashes and normalized summaries only
- server tools are denied by default
- custom and client tools are proposal-only
- `tool_result` loops fail closed with `ANTHROPIC_TOOL_RESULT_LOOP_NOT_IMPLEMENTED`
- `pause_turn`, `refusal`, `model_context_window_exceeded`, unknown stop reasons, and incomplete tool blocks fail closed

## Adapter Inventory

| Provider family | Status |
| --- | --- |
| OpenAI Responses | disabled-by-default offline vertical slice |
| Anthropic Messages | disabled-by-default offline vertical slice |
| Gemini native | RFC only |
| DeepSeek | OpenAI-compatible recipe only |

## Gate

Run the aggregate native adapter gate:

```bash
uv run python scripts/run_provider_native_adapter_gate.py --profile enterprise --json
```

Run only the Anthropic conformance matrix:

```bash
uv run python -m imperaos provider native conformance run \
  --profile enterprise \
  --provider-kind anthropic_messages \
  --offline \
  --json
```

Verify the Anthropic evidence:

```bash
uv run python -m imperaos provider native conformance verify \
  --input artifacts/model-provider-governance/native-v2/anthropic_messages_native_adapter_report.json \
  --json
```

The Anthropic matrix must include successful text/tool proposal normalization and expected-blocked cases for server tools, tool-result loops, live canary default denial, raw persistence attempts, incomplete tool blocks, and secret-like output.
