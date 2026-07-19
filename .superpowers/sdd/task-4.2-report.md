# Task 4.2 verification report

## Outcome

Task 4.2 completed the strict serialized-contract migration to ImperaOS. Active
producers and consumers now use:

- `imperaos_version`, `imperaos_retention`, and
  `imperaos_provider_response`;
- `imperaos-team`, `imperaos-computer-use`, and `imperaos_session`;
- the three canonical `imperaos-.../v2` drill/attestation identities;
- Operator Panel contract version `3.0` across Python, TypeScript, Rust, CLI,
  fixtures, and current contract documentation.

No alias, fallback read, compatibility shim, or dual-version acceptance path
was introduced. The former attestation identity and former Operator Panel
handshake version are explicitly rejected.

Implementation commit:

`22f1f186449d4e91b3b9556aa66278b2eddf433f` —
`refactor: migrate serialized contracts to ImperaOS`

Post-review hardening commit:

`a3e6ae2c3e32a5fb3c1823c4747061ebf32f907f` —
`fix: harden serialized contract validation`

Portable manifest validation commit:

`5c72d35003c5c0398c9dae65fb6ffe036c1ac98b` -
`fix: validate bundled runtime manifests portably`

## Post-review hardening

Review found two fail-open edges, both corrected with behavior-first tests:

- Windows release-gate manifests now reject duplicate, unknown, extra, blank,
  and former version keys through an exact allowed-key set. Windows and macOS
  platform verifiers enforce their exact platform-specific key sets and compare
  the manifest `imperaos_version` with the actual bundled
  `python -m imperaos --version` output.
- Assistant stream normalization no longer defaults a missing contract version.
  Missing or non-`3.0` events normalize to `null`; the mapper returns the exact
  previous state object before cloning or mutation.

Review RED evidence:

```text
uv run pytest \
  tests/test_windows_release_gate.py::test_runtime_manifest_rejects_extra_former_version_key \
  tests/test_windows_release_gate.py::test_runtime_manifest_rejects_duplicate_canonical_key \
  tests/test_serialized_contract_identity.py::test_platform_verifiers_enforce_exact_keys_and_runtime_version_match -q
3 failed

corepack pnpm@10.29.2 exec vitest run src/assistant/assistantMappers.test.ts
5 passed; 2 failed
```

The release gate accepted both invalid manifests. The mapper converted a
missing version to `3.0` and accepted the dynamically constructed former
version.

Review GREEN evidence:

```text
uv run pytest tests/test_windows_release_gate.py \
  tests/test_serialized_contract_identity.py -q
38 passed

corepack pnpm@10.29.2 exec vitest run \
  src/assistant/assistantMappers.test.ts \
  src/assistant/useAssistantSession.test.tsx \
  src/bridge.test.ts src/bridge.tauri.test.ts
4 files passed; 36 tests passed

corepack pnpm@10.29.2 build
exit 0

PowerShell AST parse and function-definition-before-invocation guard
pass
```

Changed Python Ruff, focused ESLint, and `git diff --check` also pass.

## Portable manifest validation follow-up

A second review identified that the platform-verifier evidence above depended
on source assertions for duplicated PowerShell and shell implementations. The
platform-specific exact-key and runtime-identity contract now has one portable,
standard-library-only implementation:

- `apps/operator-panel/scripts/validate_runtime_manifest.py` defines the exact
  Windows and macOS key sets, rejects duplicate, blank, unexpected/former, and
  missing keys, validates platform and architecture, and compares the canonical
  manifest version with the actual bundled-runtime version supplied by the
  caller;
- both platform verifiers run that helper with their bundled Python executable
  and the version returned by `python -m imperaos --version`;
- the duplicated inline exact-key and version-comparison implementations were
  removed, while platform-specific path, digest, and bundle checks remain.

Follow-up RED evidence:

```text
uv run pytest tests/test_runtime_manifest_validator.py -q \
  --basetemp C:\p42helperred
10 failed
```

The valid Windows/macOS subprocess cases failed because the helper did not
exist; invalid-case error assertions and both verifier-integration assertions
also failed.

Follow-up GREEN evidence:

```text
uv run pytest \
  tests/test_runtime_manifest_validator.py \
  tests/test_serialized_contract_identity.py \
  tests/test_windows_release_gate.py -q \
  --basetemp C:\p42helpergreen2
48 passed

uv run ruff check \
  apps/operator-panel/scripts/validate_runtime_manifest.py \
  tests/test_runtime_manifest_validator.py \
  tests/test_serialized_contract_identity.py
All checks passed!

PowerShell AST parse
pass

git diff --check
pass
```

The subprocess matrix covers valid Windows and macOS manifests plus duplicate,
dynamically constructed former/extra, missing, blank, version-mismatch,
platform-mismatch, and architecture-mismatch cases. Static ordering assertions
remain supplemental and verify that each script captures the actual runtime
version before invoking the helper.

This environment has no bundled Windows runtime directory to exercise and is
not macOS, so no claim is made that either complete platform bundle was launched
by this follow-up. Git Bash is also unavailable; macOS shell validation remains
covered by the focused source guard and the helper's subprocess behavior.

## TDD evidence

Tests were changed before production code.

### RED — Python fields, identities, and runtime manifests

```text
uv run pytest \
  tests/test_provider_native_anthropic_messages.py::test_anthropic_messages_request_builder_uses_messages_contract_without_raw_persistence \
  tests/test_openai_responses_adapter.py::test_openai_responses_structured_output_uses_imperaos_name_only \
  tests/test_operator_attestation_field_binding.py::test_operator_attestation_accepts_only_imperaos_v2_identity \
  tests/test_windows_release_gate.py tests/test_macos_local_trial_gate.py -q
exit 1
```

Expected failures proved that the canonical retention key, structured-output
name, `/v2` attestation identity, and `imperaos_version` manifest field were not
implemented. A second RED run of `tests/test_serialized_contract_identity.py`
failed all three tests on the former drill identities, Operator Panel `2.0`,
former team defaults, and former runtime-manifest field.

### RED — TypeScript handshake

```text
corepack pnpm@10.29.2 exec vitest run src/capabilities.test.ts
exit 1; 13 passed, 2 failed
```

The canonical `3.0` handshake was rejected and the dynamically constructed
former `2.0` value was accepted.

### RED — Rust contract constant

```text
cargo test operator_panel_contract_version_is_3_0 --lib
exit 1
```

The assertion reported `left: "2.0"`, `right: "3.0"`.

### GREEN — focused contracts

```text
uv run pytest \
  tests/test_serialized_contract_identity.py \
  tests/test_provider_native_anthropic_messages.py::test_anthropic_messages_request_builder_uses_messages_contract_without_raw_persistence \
  tests/test_openai_responses_adapter.py::test_openai_responses_structured_output_uses_imperaos_name_only \
  tests/test_operator_attestation_field_binding.py \
  tests/test_windows_release_gate.py tests/test_macos_local_trial_gate.py -q
44 passed
```

```text
corepack pnpm@10.29.2 exec vitest run \
  src/capabilities.test.ts src/bridge.test.ts src/bridge.tauri.test.ts \
  src/assistant/assistantMappers.test.ts \
  src/assistant/useAssistantSession.test.tsx \
  src/missionMappers.test.ts src/workspace.test.ts
7 files passed; 64 tests passed
```

```text
cargo test operator_panel_contract_version_is_3_0 --lib
1 passed
```

## Broad verification

The suite collects 905 Python tests.

```text
uv run pytest -q --basetemp C:\p42full
894 passed; 9 skipped; 2 failed
```

Both failures are the precise Task 4.3 generated-schema deferral:

- `test_operator_capabilities_payload_matches_contract` sees tracked schema
  `2.0` against the active `3.0` payload;
- `test_operator_panel_schemas_are_generated_from_contract_models` lists the
  19 expected stale Operator Panel schemas.

All non-deferred Python tests pass:

```text
uv run pytest -q --basetemp C:\p42nodefer \
  -k 'not test_operator_capabilities_payload_matches_contract and not test_operator_panel_schemas_are_generated_from_contract_models'
exit 0; 894 passed; 9 skipped; 2 deselected
```

```text
corepack pnpm@10.29.2 test -- --run
64 files passed; 202 tests passed

cargo test --lib
27 passed

corepack pnpm@10.29.2 build
exit 0

corepack pnpm@10.29.2 lint
exit 0

uv run ruff check <changed Python files>
All checks passed!

git diff --check
pass
```

The frontend build retains its existing non-blocking large-chunk warning.
`cargo fmt --check` could not run because the installed Rust toolchain does not
include the `rustfmt` component; no environment or dependency change was made.

Both changed PowerShell runtime scripts parse through the PowerShell AST
parser. The three active JSON fixtures/templates parse successfully. Git Bash
is not present in the portable MinGit installation, so macOS shell syntax is
covered by the focused static manifest identity guard rather than `bash -n`.

## Generated-schema deferral

No generated JSON schema was edited. Task 4.3 owns deterministic regeneration.

- 19 Operator Panel schema files contain 37 stale `const: "2.0"` entries.
- `contracts/control_plane/operator_attestation_binding.schema.json` contains
  the two stale former attestation identity entries (`const` and `default`).

These exact stale values explain the two full-suite failures above. Active
Python models, TypeScript/Rust contracts, scripts, fixtures, templates, and
tests contain no former branded serialized field, team/session ID, or schema
identity.

## Remaining `2.0` classification

Unrelated generic `2.0` values were deliberately preserved:

- audit envelopes remain `contract_version="2.0"`; they are now explicitly
  decoupled from the Operator Panel constant and retain envelope/event/handoff
  schema version `3`;
- governance approval-store, memory persistent-store, and generic schema-model
  versions remain `2.0`;
- numeric runtime bounds, qualification scale factors, wait-action text, model
  output-size fixtures, package versions, and lock-file dependency versions are
  not Operator Panel contracts.

## Historical preservation and scans

The preflight task-specific inventory contained 217 candidate lines across 68
files. That scan and the final residual scan explicitly exclude
`.superpowers/sdd/**` prior task briefs/reports to avoid classifying immutable,
self-referential process records as active product contracts. Within the
operational tracked tree, the final former branded-contract scan has seven
residual lines in five files only:

- two generated attestation-schema lines assigned to Task 4.3;
- five immutable Windows release/finalization/signed evidence report lines.

The active-code/fixture/template scan has zero former branded contract tokens.
The sole remaining branded team/session match is a historical commit subject in
`docs/SYSTEM_STATE_REPORT_2026-03-03_FINAL_v0.4.1.txt`.

The general brand inventory moved from the Task 4.1 state of 1,063 findings to:

| Metric | Task 4.1 state | Task 4.2 state | Delta |
|---|---:|---:|---:|
| Legacy content matches | 1,041 | 977 | -64 |
| Legacy path matches | 3 | 3 | 0 |
| Binary metadata matches | 19 | 19 | 0 |
| Built artifact matches | 0 | 0 | 0 |
| Total findings | 1,063 | 999 | -64 |

Inventory mode remains `status=fail` because later plan phases own desktop,
observability, evidence, package, service, documentation, and repository
identities.

## Scope boundaries preserved

- No generated JSON schema, signed evidence, historical release report, RFC,
  archive, or prior task report was edited.
- No bundled-runtime directory, Tauri crate/package/binary/bundle identity, npm
  package, UI product copy, metric, service label, domain, repository URL, or
  later-phase storage identity was changed.
- No dependency manifest or lock-file drift was introduced.
