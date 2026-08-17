# Task 4.3 — ImperaOS contract schema regeneration report

## Outcome

The three canonical schema generators were run against the Task 4.1 and Task 4.2
source models. The resulting implementation is committed as
`e57977f6c12c0c4909cb6a50db8cdb7d605b9d85` with the required subject:

`chore: regenerate ImperaOS contract schemas`

The implementation contains the force-tracked Task 4.3 brief plus 22 generated
JSON changes. No source model, dependency, lockfile, historical evidence, signed
artifact, or immutable fixture changed.

## RED evidence

Before regeneration, HEAD was
`9873cdb200b265d877b1ae0cd4e9cb618a39d0bf` and the worktree had no tracked
changes.

The focused pre-regeneration pytest command produced two failures:

- `test_operator_capabilities_payload_matches_contract` rejected the emitted
  `3.0` payload because the checked-in schema still required `2.0`.
- `test_operator_panel_schemas_are_generated_from_contract_models` reported all
  19 migrated Operator Panel schemas as drifted.

An independent in-memory parity check over the current control-plane generator
reported exactly three stale tracked schemas: `agent_spec`, `agent_record`, and
`operator_attestation_binding`.

## Canonical generation and exact diff

Only these existing scripts were used, in this order:

1. `scripts/generate_control_plane_contract_schemas.py`
2. `scripts/generate_operator_contract_schemas.py`
3. `scripts/generate_model_provider_contract_schemas.py`

The control-plane generator changed:

- `contracts/control_plane/agent_record.schema.json`
- `contracts/control_plane/agent_spec.schema.json`
- `contracts/control_plane/operator_attestation_binding.schema.json`

The Operator Panel generator changed:

- `contracts/operator_panel/schemas/approval_detail.schema.json`
- `contracts/operator_panel/schemas/approval_pending.schema.json`
- `contracts/operator_panel/schemas/assistant_start_turn.schema.json`
- `contracts/operator_panel/schemas/assistant_stream_event.schema.json`
- `contracts/operator_panel/schemas/auth_check.schema.json`
- `contracts/operator_panel/schemas/auth_whoami.schema.json`
- `contracts/operator_panel/schemas/bridge_handshake.schema.json`
- `contracts/operator_panel/schemas/config_resolve.schema.json`
- `contracts/operator_panel/schemas/key_status.schema.json`
- `contracts/operator_panel/schemas/operator_capabilities.schema.json`
- `contracts/operator_panel/schemas/preview_fixture_bundle.schema.json`
- `contracts/operator_panel/schemas/read_artifact.schema.json`
- `contracts/operator_panel/schemas/run_replay.schema.json`
- `contracts/operator_panel/schemas/run_summary.schema.json`
- `contracts/operator_panel/schemas/security_baseline.schema.json`
- `contracts/operator_panel/schemas/spawned_run.schema.json`
- `contracts/operator_panel/schemas/support_bundle_export.schema.json`
- `contracts/operator_panel/schemas/tail_events.schema.json`
- `contracts/operator_panel/schemas/team_status_artifact.schema.json`

The model-provider generator produced no diff. Dependency inspection and the
resulting diff showed no affected memory or release contract, so their generators
were intentionally not run.

The schema-only diff is 43 insertions and 43 deletions. It contains only the
expected current runtime enum values, the ImperaOS operator-attestation `/v2`
identity, and Operator Panel `3.0` constants.

## Idempotence

After the first generation pass, SHA-256 snapshots were taken across all 126
schema files under the three required output roots. The same three generators
were run a second time. The before/after snapshots were byte-identical:

`second_run_hashes_identical=True`

No additional file or diff appeared.

## GREEN verification

Focused pytest verification:

- command scope: the capabilities/schema parity regression, all Operator Panel
  generation tests, and native model-provider contract tests;
- result: 4 passed, exit 0.

Full control-plane generator parity verification:

- 79 generated models compared byte-for-byte with their tracked schemas;
- zero mismatches, exit 0.

Full Python suite:

- 918 tests collected;
- full run exit 0;
- 9 skipped and 909 executed tests passed.

The generated output roots were scanned for both former runtime enum values, the
former attestation identity, and stale Operator Panel `2.0` constants. Every
task-specific residual count was zero.

`git diff --check` and the staged equivalent both exited 0. UI and Rust suites
were not rerun because this task changed only canonical-generator output; their
source contracts and cross-language `3.0` parity were verified in Task 4.2.

## Brand inventory

Fresh inventory evidence at the Task 4.2 base was:

| Metric | Before |
|---|---:|
| Legacy content matches | 977 |
| Legacy path matches | 3 |
| Binary metadata matches | 19 |
| Built artifact matches | 0 |
| Total findings | 999 |

After implementation commit `e57977f`, the inventory was:

| Metric | After | Delta |
|---|---:|---:|
| Legacy content matches | 972 | -5 |
| Legacy path matches | 3 | 0 |
| Binary metadata matches | 19 | 0 |
| Built artifact matches | 0 | 0 |
| Total findings | 994 | -5 |

Six generated-schema findings were removed. The force-tracked brief contributes
one self-referential inventory finding, producing the net reduction of five.
Inventory status remains intentionally failing because later rename phases own
the remaining product surfaces.

## Boundary audit

- Generated JSON was not hand-edited.
- No source contract model changed.
- No dependency manifest or lockfile changed.
- No history, signed evidence, immutable artifact, or migration fixture changed.
- No external state was mutated and no artifact was deleted.
