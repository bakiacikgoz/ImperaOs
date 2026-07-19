# Task 4.1 — Namespace runtime kinds under ImperaOS

## Goal

Move the two product-owned `RuntimeKind` enum members and serialized values to
the canonical ImperaOS namespace, then update every active code, example,
frontend mapper, and fixture consumer in this task's scope.

## Canonical contract

- Enum members: `IMPERAOS_CORE`, `IMPERAOS_TEAM`.
- Serialized values: `imperaos_core`, `imperaos_team`.
- The two former product runtime-kind values must be rejected; no enum aliases,
  `_missing_` fallback, coercion shim, or dual-read behavior is allowed.
- Generic runtime kinds remain byte-for-byte unchanged.

## Scope

- `imperaos/control_plane/models.py`.
- Control-plane registry/snapshot/mappers where a product runtime-kind literal
  or member is consumed.
- `examples/control_plane/*.yaml` agent specifications.
- Operator Panel preview fixtures, control-plane mappers, and their tests.
- The tracked Operator Panel control-plane preview JSON fixture.
- Python validation tests proving canonical values are accepted and former
  values are rejected.

## Explicit boundaries

- Do not hand-edit generated JSON schemas. Task 4.3 owns regeneration after all
  serialized contract changes are complete.
- Do not change schema identity/version strings, contract field names, manifest
  fields, provider metadata, structured-output names, team/session IDs,
  metrics, Tauri identity, storage keys, or environment/state paths.
- Do not edit prior task reports, historical/signed evidence, release records,
  RFCs, or archived artifacts.
- Do not add dependencies or modify lock files.

## TDD requirements

Write failing tests first for:

1. Both canonical member names and serialized values.
2. Validation rejection of both former serialized values. Construct former
   literals at runtime so the active test tree does not reintroduce them.
3. Frontend mapper/preview expectations using the canonical team runtime kind.

Record the RED commands and failure reasons before implementation.

## Verification

- Focused Python control-plane model/registry/snapshot tests.
- Focused Operator Panel mapper/preview tests.
- YAML/example parsing or existing example validation tests.
- Full Python and Vitest suites if generated-schema deferral does not create an
  expected Task-4.3 drift failure; otherwise classify each exact failure.
- Static scan: former runtime-kind literals may remain only in generated schemas
  assigned to Task 4.3 and immutable prior task records.
- `git diff --check`, changed-file lint, no dependency/lock drift, brand
  inventory delta.

## Commit

Use the exact implementation commit subject:

`refactor: namespace runtime kinds under ImperaOS`

Create a separate verification/report commit if needed.
