# Agent Memory Policy Enforcement Handoff

Status: implemented behind disabled-by-default feature flags.

Branch contents:

- Runtime policy gateway: `imperaos/memory/runtime_policy.py`
- Principal resolver: `imperaos/memory/principal_resolver.py`
- Semantic runtime adapter: `imperaos/memory/semantic/runtime_adapter.py`
- Control Plane snapshot: `imperaos/memory/runtime_policy_snapshot.py`
- Contract schemas and fixtures: `contracts/memory/`
- Gate suite: `benchmarks/tasks/memory/runtime_policy_cases.jsonl`
- CLI: `memory runtime policy doctor|simulate|evaluate`
- Operator panel card: `apps/operator-panel/src/memory-runtime/MemoryRuntimePolicyView.tsx`

Operational notes:

- Keep `policy_enforcement_enabled=false` outside pilot profiles until workspace authority identity and membership seeding are explicit.
- Use `semantic_runtime_mode=shadow` before `enforced` when validating live retrieval drift.
- Do not treat semantic retrieval as an authorization source. Workspace/scope/RBAC candidate selection must stay ahead of ranking.
- Evidence must stay hash-only. New policy event fields must avoid raw query, prompt, response, summary, memory text, tokens, private keys, and API keys.

Recommended validation before release:

```bash
make memory-runtime-policy-gate
make semantic-memory-index-gate
make memory-runtime-gate
make control-plane-gate
```
