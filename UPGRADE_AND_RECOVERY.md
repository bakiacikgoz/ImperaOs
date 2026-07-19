# Upgrade And Recovery

## Compatibility Contract

- Supported upgrade path: `N -> N+1`
- Mixed-version binaries on the same store are unsupported
- Reverse migrations are not supported
- Rollback is performed by restoring a verified backup created before upgrade

## Covered State

- memory store
- approval store
- checkpoint store
- audit and team artifact manifests
- policy/config bundle
- trusted key manifest

## Upgrade Sequence

1. Resolve config and verify enterprise baseline.
2. Enter maintenance mode.
3. Create and verify a backup.
4. Run migration plan dry-run.
5. Apply migrations.
6. Verify store schema versions and replay sample checks.
7. Resume runtime traffic.

## Migration Expectations

Each sqlite-backed store must expose a schema version metadata record.
Migration tooling must support:

- `imperaos migrate plan --dry-run`
- `imperaos migrate apply --dry-run`
- `imperaos migrate apply --no-dry-run`

## Backup Contract

Backup includes:

- sqlite store copies
- audit directory snapshot
- team artifact snapshot
- policy bundle snapshot
- key manifest snapshot
- signed backup manifest

## Restore Verification

Restore verification must validate:

- sqlite `integrity_check`
- policy/config hash continuity
- key manifest presence
- replay verification on a representative sample

## Commands

```bash
uv run imperaos migrate plan --profile enterprise --json
uv run imperaos migrate apply --profile enterprise --dry-run --json
uv run imperaos backup create --profile enterprise --json
uv run imperaos restore verify --profile enterprise --backup-dir .imperaos/enterprise/backups/<backup-id> --json
```

## Mandatory Drills Before GA

- forward migration pass
- partial upgrade abort plus restore pass
- schema mismatch negative test
- stale config manifest reject
