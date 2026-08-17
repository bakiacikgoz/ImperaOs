# Model Provider Native Adapter V2.1 Closure Report

Status: completed as an offline Anthropic Messages vertical slice.

## Scope Delivered

- Added the `anthropic_messages` provider kind.
- Added Anthropic Messages request/result contracts and generated schemas.
- Added normalized content block and stop reason models.
- Added an Anthropic Messages payload builder that stores only prompt hashes and rejects raw payload persistence.
- Added response normalization for text output and `tool_use` proposal blocks.
- Added fail-closed handling for server tools, high-risk client tools, `tool_result` loops, incomplete tool blocks, unsupported content blocks, unsupported stop reasons, and secret-like output.
- Added 17 Anthropic offline conformance fixtures.
- Added Anthropic support to the native conformance CLI, native adapter gate, Makefile, and CI workflows.
- Added Operator Panel V4 trust metadata for Anthropic native preview.

## Default Runtime Boundary

- Anthropic native adapter remains disabled by default.
- The preview row is canary-only.
- No production routing is enabled.
- No live canary is run by default.
- CI stays offline.

## Conformance Result

Latest local Anthropic matrix result:

- total cases: 17
- passing cases: 4
- expected-blocked cases: 13
- unexpected failures: 0
- live canary attempted: false
- evidence verification: pass

Latest aggregate native gate result:

- total cases: 28
- passing cases: 7
- expected-blocked cases: 21
- unexpected failures: 0
- live canary attempted: false
- evidence verification: pass

## Evidence Paths

- Aggregate gate JSON: `artifacts/model-provider-governance/native-v2/provider_native_adapter_gate.json`
- OpenAI native conformance JSON: `artifacts/model-provider-governance/native-v2/openai_responses_native_adapter_report.json`
- Anthropic native conformance JSON: `artifacts/model-provider-governance/native-v2/anthropic_messages_native_adapter_report.json`

## Required Validation Commands

```bash
uv run --extra dev ruff check .
uv run --extra dev python -m pytest -q
uv run python scripts/run_provider_governance_gate.py --profile enterprise --json
uv run python scripts/run_provider_native_adapter_gate.py --profile enterprise --json
uv run python -m imperaos provider native conformance run --profile enterprise --provider-kind anthropic_messages --offline --json
uv run python -m imperaos provider native conformance verify --input artifacts/model-provider-governance/native-v2/anthropic_messages_native_adapter_report.json --json
corepack pnpm --dir apps/operator-panel test
corepack pnpm --dir apps/operator-panel lint
corepack pnpm --dir apps/operator-panel build
cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml --target-dir apps/operator-panel/src-tauri/target-codex-test
git diff --check
```

## Non-Claims

- This slice does not certify live Anthropic production routing.
- This slice does not enable Anthropic server-side tools.
- This slice does not execute client/custom tool proposals.
- This slice does not implement `tool_result` continuation loops.
- This slice does not approve Gemini or other native adapters.
