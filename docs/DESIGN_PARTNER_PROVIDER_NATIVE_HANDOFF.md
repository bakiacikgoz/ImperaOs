# Design Partner Provider Native Handoff

This handoff demonstrates provider governance without expanding the product
claim boundary.

## Demo Workflow

Read-only workflow:

1. Summarize recent operational errors.
2. Draft a remediation plan.
3. If an action is needed, propose a ticket only.
4. Keep mutation execution behind the existing approval lifecycle.

The external provider may produce a summary or plan. It must not execute a
server-side provider tool, desktop action, ticket mutation, deployment, or other
irreversible operation in this phase.

## Evidence Pack

The demo evidence pack should include:

- provider registry snapshot,
- provider native conformance reports,
- policy decision reason codes,
- hash-only request identifiers,
- redaction result,
- operator decision chain,
- claim guard matrix.

Raw prompts, raw responses, API keys, Authorization headers and customer PII are
not valid evidence artifacts.

## Operator Panel

The dashboard Provider Trust card is the primary operator-facing surface. It
shows provider status, credential state, conformance status and trust badges:

- `canary_only`
- `hash_only`
- `server_tools_denied`
- `proposal_only`
- `credential_missing`

Raw JSON remains a debug/advanced surface and is not the primary trust signal.

## Runbook

1. Run `make provider-native-gate`.
2. Run `uv run imperaos control-plane snapshot --profile enterprise --json`.
3. Generate the Design Partner RC pack.
4. Review `providerGovernance` in `artifacts/design-partner-rc/manifest.json`.
5. Confirm computer-use live execution and public desktop installer boundaries
   remain blocked.
6. Publish only if secret/raw-data scans pass and claim guard has no safety
   boundary failure.

## Backlog

Gemini and DeepSeek native adapters remain backlog items. They should use the
same shared provider governance envelope and must start offline/canary-only.
