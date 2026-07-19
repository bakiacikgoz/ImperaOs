# Memory Runtime Policy Enforcement

Agent Memory Policy Enforcement v1 adds an in-process gateway around runtime memory reads and post-run writes.

Defaults remain closed:

- `memory.runtime.policy_enforcement_enabled = false`
- `memory.runtime.semantic_runtime_mode = "disabled"`
- semantic runtime injection remains disabled unless both semantic memory and runtime injection are explicitly enabled.

When enabled, runtime memory calls resolve a principal and workspace scope before any retrieval path runs. Enterprise and restricted profiles fail closed when the principal, workspace, membership, or scope set is missing or ambiguous.

## Read Path

The gateway resolves operator, session, agent, team-agent, and external-agent identities into a workspace principal. It derives allowed scopes such as `personal:<principal>`, `agent:<agent>`, `team:<team>`, `case:<case>`, and `project:<project>`.

Semantic runtime modes:

- `disabled`: existing workspace authority retrieval is used.
- `shadow`: semantic retrieval runs for hash-only comparison evidence, but prompt context does not change.
- `enforced`: semantic retrieval is used only after workspace, principal, scope, and ACL checks produce an allowed candidate set.

## Write Path

Post-run writes are denied when runtime writes are disabled, when secret-like content is detected, or when the principal/scope cannot be resolved. Shared team/project/case writes follow workspace authority policy and remain proposal-only. Organization writes require approval.

## Evidence And Privacy

Policy events are written under `artifacts/memory-runtime-policy/events/`.

Events contain hashes, status, action, reason codes, and counters only. They do not persist raw prompt, response, query, memory content, summaries, PII, secrets, API keys, tokens, or private keys.

## CLI

```bash
uv run imperaos memory runtime policy doctor --profile balanced
uv run imperaos memory runtime policy simulate --operation read --query "provider governance"
uv run imperaos memory runtime policy evaluate \
  --suite benchmarks/tasks/memory/runtime_policy_cases.jsonl \
  --output artifacts/memory-runtime-policy/evaluation.json \
  --profile enterprise
```

## Gate

```bash
make memory-runtime-policy-gate
```
