# Task 4.3 — ImperaOS contract schema regeneration

## Goal

Regenerate the checked-in contract schemas deterministically after the Task 4.1 runtime-kind and Task 4.2 serialized-contract migrations.

## Required generators

Use the repository's existing canonical generators only:

- `scripts/generate_control_plane_contract_schemas.py`
- `scripts/generate_operator_contract_schemas.py`
- `scripts/generate_model_provider_contract_schemas.py`

Do not invent a new generation command or hand-edit generated JSON. Run memory or release schema generators only if source/dependency inspection proves those contracts are affected.

## TDD and verification

1. Confirm the worktree starts clean at `9873cdb`.
2. Record RED evidence before regeneration:
   - the two known operator-schema parity tests fail only because tracked schemas still declare contract `2.0`;
   - add or run a focused control-plane parity check showing tracked runtime-kind/attestation schemas are stale relative to current models.
3. Run all three required generators.
4. Inspect the diff. It must contain only expected generated-schema changes:
   - `imperaos_core` / `imperaos_team` to `imperaos_core` / `imperaos_team` in current control-plane runtime schemas;
   - old operator-attestation identity to its ImperaOS `/v2` identity;
   - Operator Panel contract schema values from `2.0` to `3.0`;
   - model-provider output may legitimately have no diff.
5. Prove idempotence by running the same three generators a second time and showing no additional diff/hash change.
6. Run focused schema-generation/parity tests, then the full Python suite. Run relevant UI/Rust contract tests if needed to verify cross-language parity.
7. Scan the generated schema sets for the former runtime values, former attestation identity, and stale Operator Panel `2.0` values; expected count is zero for the migrated current contracts.
8. Record the legacy-name inventory delta.

## Boundaries

- Do not change source contract models in this task.
- Do not edit historical, signed, immutable, migration-fixture, or compatibility evidence.
- Do not change dependencies or lockfiles.
- Do not delete artifacts or mutate external state.
- Keep generated JSON formatting and ordering exactly as emitted by the canonical scripts.

## Deliverables

- Implementation commit with exact subject: `chore: regenerate ImperaOS contract schemas`
- Verification report: `.superpowers/sdd/task-4.3-report.md`
- Report commit may be separate and should describe RED/GREEN, exact generated files, idempotence, test results, and inventory evidence.
