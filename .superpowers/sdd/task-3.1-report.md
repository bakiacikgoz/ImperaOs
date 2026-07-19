# Task 3.1 Implementation Report

## Outcome

Runtime state defaults now use the canonical `.imperaos` root. Production Python resolves
paths through `imperaos.runtime.paths`, enterprise profile state stays beneath
`.imperaos/enterprise`, and the Prometheus textfile is named `imperaos.prom` without
changing metric names.

The implementation commit is `553dd1ebc56a6f5066ae6bbf92b6c1fe726b4f9a` with exact
subject `refactor: move runtime state paths to .imperaos`.

No state migration, copy, activation, or user-state deletion was implemented. Test-created
state roots inside the isolated worktree were verified by absolute path and removed after
the suite; the main checkout and user/AppData state were not touched.

## TDD evidence

1. Initial RED: `tests/test_runtime_paths.py` failed because
   `imperaos.runtime.paths` did not exist (1 expected assertion failure).
2. Minimal module GREEN: the module-existence test passed.
3. API/default RED: 31 expected failures proved the missing constants/helpers/guards,
   old `RuntimeConfig` defaults, shipped profile defaults, and enterprise placement.
4. Helper GREEN: 24 selected helper/guard cases passed.
5. Final focused GREEN: 32 runtime-path tests passed.

The guard matrix covers safe nesting and separator normalization plus POSIX absolute,
Windows drive-absolute, UNC, drive-relative, forward-slash traversal, backslash traversal,
later-part root reset, and NUL rejection. Unsafe inputs raise `ValueError`; they are never
resolved or normalized into the approved root.

## Changed surfaces

- Added `DEFAULT_STATE_ROOT`, `state_path()`, `enterprise_state_path()`, shared
  control-plane/enterprise/team/memory/trace/research constants, and validation guards.
- Centralized Python defaults in runtime config, CLI, control-plane, memory, team,
  enterprise signing/observability, and telemetry.
- Updated all shipped profile TOML files and the tracked research router config.
- Moved enterprise trace/research, memory/workspace, governance/team, identity/keys,
  observability, and maintenance defaults below the enterprise state root.
- Updated active scripts, Makefile/CI cleanup, operator-panel defaults, examples, fixtures,
  and tests. `.gitignore` preserves the legacy safeguard and also ignores `.imperaos/`.

## Verification

| Check | Result |
|---|---|
| Focused required suite with `--basetemp C:\p31r` | 63 passed |
| Changed/affected tests with `--basetemp C:\p31a` | 65 passed |
| Complete Python suite with `--basetemp C:\p31` | 887 passed, 9 skipped; exit 0 in 87.9s |
| Changed operator-panel Vitest selection | 39 passed |
| Rust bridge `cargo test -q` | 25 passed |
| Ruff on every changed Python file | all checks passed |
| `git diff --check` | exit 0 |
| RuntimeConfig plus six shipped profile JSON payloads | no legacy state root; pass |
| Active state-path guard | pass; no legacy state path in scoped active surfaces |
| Worktree state-root presence after cleanup | false |

One initial enterprise qualification run used pytest's long default Windows temp path.
Its 264-character atomic status-file path failed with `Errno 2`, which made the workload
status fail. Fixture keys and identity paths were verified to match enterprise config.
The brief-required short basetemp removed the environmental path-length failure; the exact
focused rerun passed 63 tests without changing expectations or production behavior.

## Deferred-token preservation

The staged zero-context diff guard proved these explicit identifiers unchanged: `IMPERAOS_*`, `IMPERAOS_*`, `env_prefix`, `imperaos-runtime`, `imperaos_version`, schema IDs, runtime kinds, team IDs, provider metadata keys, metric names/prefixes, frontend storage keys, bundle IDs, and the preserved qualification service label.

No signed or historical evidence files changed. The negative config regression constructs
the legacy state spelling at runtime so active test fixtures contain no legacy path literal.

## Brand inventory delta

Inventory mode intentionally remains `status=fail` for later rebrand work.

| Metric | Baseline | Final tracked state | Delta |
|---|---:|---:|---:|
| Total findings | 1,542 | 1,270 | -272 |
| Legacy content matches | 1,520 | 1,248 | -272 |
| Legacy path matches | 3 | 3 | 0 |
| Binary metadata matches | 19 | 19 | 0 |
| Built artifact matches | 0 | 0 | 0 |
| Scanned files | 1,509 | 1,512 | +3 |

The implementation commit alone had 1,269 findings and 1,247 content matches; the single
deferred-token documentation line above is inventory-visible in this report.

## Review remediation

Review follow-up commit `4bbbae47ce564808ccbaa4b6721b1e97b6c91391` updates the two
active Operator Panel preview fixtures to the canonical state root and makes integration
gate repository copies exclude both the retired and current state-root directories.

The fixes were test-driven:

1. The new Vitest serialization regression first failed because preview payloads still
   contained the retired root. After the fixture update, the focused test passed and also
   proved a custom team root is substituted into run summary/detail payloads.
2. The Python copy sentinel first failed because the retired state directory was copied.
   After extending the ignore set, the selected copy test passed; the retired spelling is
   assembled from parts in both production and test code.

Review verification:

| Check | Result |
|---|---|
| Operator Panel preview/settings/bridge/app/control-plane Vitest selection | 40 passed |
| Runtime/config/platform/integration/contracts Python selection | 56 passed |
| Complete Python suite with `--basetemp C:\\p31rev` | 886 passed, 9 skipped; exit 0 in 80.46s |
| Ruff on the changed Python script and test | all checks passed |
| Rust | not rerun; no Rust source or manifest changed |
| `git diff --check` and staged deferred-token guard | pass |
| Active state-path guard including contract fixtures | pass |
| Worktree state-root presence after scoped cleanup | false |

The committed review inventory is 1,254 total findings: 1,232 content, 3 path,
19 binary metadata, 0 built artifacts, across 1,513 scanned files. Relative to the
pre-review Task 3.1 state, this is 16 fewer total/content findings and one additional
scanned regression-test file; relative to the 1,542 baseline it is a reduction of 288.

## Final repository state

After the report commit, `git status --short` produced no output. Both worktree state-root
directories were absent. The repository-local commit identity used was
`Codex <codex@openai.com>`.
