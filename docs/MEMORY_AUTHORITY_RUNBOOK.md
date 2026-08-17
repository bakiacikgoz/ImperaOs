# Memory Authority Runbook

Use `uv run imperaos memory doctor --profile balanced` to inspect the current authority snapshot.

Common checks:

- `authorityStatus=disabled` is expected while `memory.v3_enabled=false`.
- `rawPromptPersistence=false`, `rawResponsePersistence=false`, and `primaryUiRawContent=false` must remain false.
- `memory propose --scope organization` should return `approval_required`.
- Candidate text containing secret markers such as `sk-...` should return `denied`.

Recovery:

- If SQLite reports a lock, stop concurrent gate runs and rerun the target sequentially.
- If `memoryGovernance.index.status` is `error`, run `make memory-index-gate`.
- If evidence writing fails, inspect `artifacts/memory-governance/latest.json`; it must not contain raw prompt, raw response, candidate text, or secrets.

Do not manually edit `memory_records_v3` rows except in disposable development databases.
