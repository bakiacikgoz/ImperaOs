# Model Provider Governance PR Readiness

Status: staged and ready for review grouping.

## Staged Diff Summary

- Branch: `feature/model-provider-governance-v1`
- Scope: provider governance V1, V1.1 canary/routing/conformance, Native Adapter V2 foundation, Operator Panel trust surface, docs and gates.
- Current staged diff: 100+ files, backend + frontend + schemas + docs + tests.
- Staged patch backup:
  - `artifacts/model-provider-governance/v1_1/git/staged_provider_v1_1.patch`
  - `artifacts/model-provider-governance/v1_1/git/staged_provider_v1_1_name_status.txt`
- Secret/raw payload scan:
  - `artifacts/model-provider-governance/v1_1/security/staged_secret_scan.json`
  - Final staged scan status: `pass`
  - Unsafe matches: `0`

## Commit Groups

| Group | Scope | Targeted validation |
| --- | --- | --- |
| V1 closure | registry, policy, redaction, envelope, docs | `tests/test_model_provider_registry.py`, `tests/test_model_provider_policy.py`, `tests/test_model_provider_envelope.py` |
| V1.1 canary backend | canary, budget, network, evidence verifier | `tests/test_model_provider_canary.py`, `tests/test_model_provider_budget.py`, `tests/test_model_provider_network_guard.py` |
| Router shadow | shadow recommendation and evidence | `tests/test_model_provider_router_shadow.py` |
| Conformance and native skeleton | conformance matrix, V2 RFC, disabled OpenAI Responses skeleton | `tests/test_provider_conformance_matrix.py`, `tests/test_provider_native_adapter_contract.py` |
| Operator Panel trust surface | provider discovery, registry UI, preview fixtures | `tests/test_operator_provider_models.py`, `corepack pnpm --dir apps/operator-panel test -- AssistantModelPicker` |
| Docs and CI gates | Makefile, CI, closure scripts, operator/security docs | `scripts/run_provider_governance_gate.py`, `scripts/verify_provider_release_closure.py` |

## Rollback Boundary

- Do not use `git reset --hard`.
- The staged backup patch can restore the review snapshot if commit grouping needs to be redone.
- Native Adapter V2 files are isolated under `imperaos/model_providers/native/` and can be reverted without changing legacy `ollama`, `transformers`, or `openai_compatible` paths.

## Review Notes

- Live provider canary was not run and is not required for merge readiness.
- Public cloud providers remain disabled by default.
- Router decisions remain shadow-only.
- Native provider server-side tools remain default deny.
