# External Agent Gateway Guide

Register the sample external stdio agent:

```bash
uv run imperaos control-plane agent register \
  --spec examples/control_plane/agent_external_gateway.yaml \
  --profile lite \
  --json
```

Submit governed requests with `control-plane gateway submit-action --input <json>`.
Read-only requests can be accepted. External writes require approval. Destructive
and credential-sensitive requests are denied by default.

Contract fixtures live in `contracts/control_plane/fixtures/external_agent_*.json`.

## v1.1 pilot contract

Gateway v1.1 adds workflow-aware action lists, idempotency keys and replay
verification. The pilot examples live in `examples/external_agents/v1_1/`.

```bash
uv run imperaos control-plane gateway submit-v1-1 \
  --input examples/external_agents/v1_1/read_only_inspector.json \
  --profile enterprise \
  --json

uv run imperaos control-plane gateway replay-v1-1 \
  --request-id v1-1-read-only-inspector \
  --expected-request-hash <requestHash> \
  --profile enterprise \
  --json
```

`make external-agent-v1-1-gate` covers the read-only, approval-required,
destructive denied, duplicate idempotency and replay mismatch paths.
