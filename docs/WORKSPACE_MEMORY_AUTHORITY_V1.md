# Workspace Memory Authority v1

Workspace Memory Authority v1 is a local-only, opt-in authority layer for workspace-scoped memory.
It keeps legacy memory v3 available while adding typed workspaces, principals, memberships, ACLs,
CAS writes, sync v2 packs, and migration dry-run planning.

## Configuration

All shipped profiles include the disabled default:

```toml
[memory.workspace_authority]
enabled = false
mode = "local"
default_workspace_id = "default"
default_principal_id = "agent-local"
db_path = ".imperaos/workspace_memory.sqlite3"
raw_content_persistence = false
network_listener_enabled = false
migration_apply_enabled = false
```

The authority does not start a network listener, does not require TurboVec, and does not allow
migration apply. Runtime bridge integration is active only when both `memory.runtime.enabled`
and `memory.workspace_authority.enabled` are true.

## CLI

```bash
uv run imperaos memory workspace init --workspace-id default --owner-principal-id agent-local
uv run imperaos memory principal add --principal-id agent-a --principal-type agent
uv run imperaos memory workspace grant --workspace-id default --principal-id agent-a --role agent
uv run imperaos memory scope grant --workspace-id default --scope-type team --scope-id platform --principal-id agent-a --permission memory.write.team
uv run imperaos memory authority propose-write --summary "Remember this." --workspace-id default --principal-id agent-local --scope-type personal --scope-id agent-local
uv run imperaos memory authority query --workspace-id default --principal-id agent-local --scope-type personal --scope-id agent-local --query remember
uv run imperaos memory workspace sync export --workspace-id default --output artifacts/memory/workspace_pack.json
uv run imperaos memory workspace sync verify --input artifacts/memory/workspace_pack.json
uv run imperaos memory workspace sync import --input artifacts/memory/workspace_pack.json
uv run imperaos memory workspace sync apply --input artifacts/memory/workspace_pack.json --approval-id approved-local
uv run imperaos memory workspace conflicts list --workspace-id default
uv run imperaos memory workspace migrate legacy-dry-run --legacy-db-path .imperaos/memory.sqlite3 --workspace-id default
```

## Gates

```bash
make workspace-memory-authority-gate
make memory-rbac-gate
make memory-workspace-sync-gate
make memory-migration-dry-run-gate
make memory-authority-operator-gate
```

`make workspace-memory-authority-gate` runs the focused Python tests, generates workspace memory
JSON schemas under `contracts/memory/workspace`, and invokes the subordinate gates.
