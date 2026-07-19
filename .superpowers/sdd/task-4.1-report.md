# Task 4.1 verification report

## Outcome

Task 4.1 moved the two product-owned runtime kinds to the canonical ImperaOS
namespace. The enum exposes only `IMPERAOS_CORE` and `IMPERAOS_TEAM` for those
product runtimes, serialized as `imperaos_core` and `imperaos_team`. The former
serialized values are rejected, and no alias, fallback, coercion, or dual-read
path was added. Generic runtime kinds remain unchanged.

Implementation commit:

`aecba0c138d32f8dbf7647a68383eb7c110f570c` —
`refactor: namespace runtime kinds under ImperaOS`

## Changed paths

- `imperaos/control_plane/models.py`
- `tests/test_control_plane_models.py`
- `examples/control_plane/agent_governed_ops.yaml`
- `examples/control_plane/agent_provider_governed_ops.yaml`
- `examples/control_plane/team_governed_ops.yaml`
- `apps/operator-panel/src/controlPlaneMappers.test.ts`
- `apps/operator-panel/src/control-plane/controlPlaneSnapshot.test.ts`
- `apps/operator-panel/src/previewFixtures.ts`
- `apps/operator-panel/src/previewFixtures.test.ts`
- `contracts/operator_panel/fixtures/control_plane_snapshot_preview.json`
- `.superpowers/sdd/task-4.1-brief.md`

No generated JSON schema, dependency manifest, or lock file was edited.

## TDD evidence

Tests were changed before production code.

### RED — Python contract

```text
.venv/Scripts/python.exe -m pytest -q tests/test_control_plane_models.py --basetemp C:\p41red
exit 1
```

Three expected failures proved the contract was not yet implemented:

- the canonical core enum member did not exist;
- the former core serialized value was still accepted;
- the former team serialized value was still accepted.

The negative cases construct the former namespace at runtime so active test
source does not reintroduce a forbidden product token.

### RED — Operator Panel preview

```text
corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run \
  src/controlPlaneMappers.test.ts \
  src/previewFixtures.test.ts \
  src/control-plane/controlPlaneSnapshot.test.ts
exit 1
```

The new preview assertion failed because the first internal agent still emitted
the former team runtime kind. The mapper and snapshot tests already passed with
their new expectations, isolating the missing production change to the preview
fixture.

### GREEN — focused contracts

```text
.venv/Scripts/python.exe -m pytest -q \
  tests/test_control_plane_models.py \
  tests/test_control_plane_registry.py \
  tests/test_agent_registry_v2.py \
  tests/test_control_plane_snapshot.py \
  --basetemp C:\p41green
14 passed
```

```text
corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run \
  src/controlPlaneMappers.test.ts \
  src/previewFixtures.test.ts \
  src/control-plane/controlPlaneSnapshot.test.ts
3 files passed; 7 tests passed
```

All four `examples/control_plane/*.yaml` agent specifications also parsed
successfully through `load_agent_spec`.

## Broad verification

```text
.venv/Scripts/python.exe -m pytest -q --basetemp C:\p41full
exit 0; 900 tests collected; 9 skipped
```

```text
corepack pnpm@10.29.2 --dir apps/operator-panel test
64 files passed; 201 tests passed
```

```text
.venv/Scripts/python.exe -m ruff check \
  imperaos/control_plane/models.py tests/test_control_plane_models.py
All checks passed!
```

```text
corepack pnpm@10.29.2 --dir apps/operator-panel build
exit 0
```

The frontend build retains its existing non-blocking large-chunk warning.

```text
git diff --check
pass

git diff --name-only -- '*lock*' pyproject.toml package.json Cargo.toml
no output
```

## Generated-schema deferral

Task 4.3 owns generated schema regeneration. No generated schema was edited in
this task.

An in-memory `AgentSpec.model_json_schema()` comparison shows the current model
emits the two canonical ImperaOS product values while the tracked generated
schemas retain the two former values. The static former-runtime scan reports
exactly four lines, all confined to:

- `contracts/control_plane/agent_spec.schema.json` (two enum entries);
- `contracts/control_plane/agent_record.schema.json` (two enum entries).

No former runtime-kind literal remains in active Python, frontend source,
examples, active tests, or the tracked Operator Panel preview fixture.

## Brand inventory delta

The final tracked Task 3.2 baseline was 1,074 findings. Task 4.1 inventory mode
reports:

| Metric | Baseline | Task 4.1 state | Delta |
|---|---:|---:|---:|
| Legacy content matches | 1,052 | 1,041 | -11 |
| Legacy path matches | 3 | 3 | 0 |
| Binary metadata matches | 19 | 19 | 0 |
| Built artifact matches | 0 | 0 | 0 |
| Total findings | 1,074 | 1,063 | -11 |

Inventory mode intentionally remains `status=fail` because later plan phases
own the remaining product, contract, desktop, observability, evidence, and
documentation identities.

## Scope boundaries preserved

- Schema identity/version strings and contract field names were not changed.
- Provider metadata, structured-output names, team/session identifiers, metrics,
  Tauri identity, state paths, and environment paths were not changed.
- Historical reports, signed evidence, release records, RFCs, and archived
  artifacts were not edited.
- No dependency or lock-file drift was introduced.
