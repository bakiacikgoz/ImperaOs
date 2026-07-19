# Memory Runtime Operator Runbook

Useful commands:

```bash
uv run imperaos memory runtime doctor --profile balanced
uv run imperaos memory runtime context --profile balanced --query "release notes"
uv run imperaos memory sync export --profile balanced --output artifacts/memory-sync/pack.json --source-environment local
uv run imperaos memory sync verify --input artifacts/memory-sync/pack.json
uv run imperaos memory sync import --profile balanced --input artifacts/memory-sync/pack.json
```

Default state is disabled. Enable runtime memory only in a profile that also enables Memory v3. For apply, use an approval id and keep cross-environment import disabled unless the operator has reviewed the dry-run report.

No operator workflow should expose raw memory text in the primary UI.
