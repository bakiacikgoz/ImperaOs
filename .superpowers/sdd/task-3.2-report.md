# Task 3.2 verification report

## Outcome

Task 3.2 moved the active, project-owned environment contract to the canonical
ImperaOS namespace. The old project prefixes are not read or forwarded, and no
compatibility fallback or dual-read path was added. Provider-standard variables
remain supported unchanged.

Implementation commit:

`2f15345e` — `refactor: adopt IMPERAOS environment namespace`

## Implemented surfaces

- Runtime configuration now derives its canonical environment prefix from
  `PRODUCT_IDENTITY.env_prefix`; the model constrains the value to the canonical
  literal.
- All six shipped TOML profiles declare the canonical prefix.
- Python environment lookups were updated across provider invocation, provider
  canary, computer-use qualification, audit signing/redaction, enterprise
  identity, CLI help, and integration helpers.
- The Operator Panel TypeScript bridge emits canonical project variables.
- The Rust bridge injects bundled-runtime variables under the canonical prefix,
  accepts only that project prefix, and continues to permit the four approved
  provider-standard API-key variables.
- Active CI, bundled-runtime scripts, operator documentation, runbooks, examples,
  and tests were updated.
- Local bundled-runtime build variables were renamed without changing deferred
  manifest field names.

## TDD evidence

Tests were changed before implementation.

- Python configuration contracts produced 5 expected failures before the
  resolver/default/config-root changes.
- The Operator Panel bridge contract produced 1 expected Vitest failure before
  the TypeScript environment map changed.
- The Rust allow-list contract covers acceptance of the canonical project
  prefix, rejection of both former project prefixes, retention of approved
  provider-standard keys, and rejection of unrelated variables.
- The Python negative contracts construct former names at runtime so the active
  tracked tree does not reintroduce them as usable configuration examples.
- Redaction coverage verifies that a secret-bearing canonical environment key is
  masked and its fixture value is absent from the redacted representation.

## Verification

All commands below were rerun from the clean implementation commit.

### Python

```text
.venv/Scripts/python.exe -m pytest -q --basetemp C:\\p32
exit 0; 897 tests collected; 9 skipped during the full run
```

The implementation run also executed the focused environment/config/provider/
computer-use/enterprise selection: 57 passed.

Changed Python files:

```text
.venv/Scripts/python.exe -m ruff check <changed Python paths>
All checks passed!
```

Repository-wide Ruff still reports one pre-existing, unrelated E501 at
`imperaos/model_providers/registry.py:59`. That file is outside this commit.

### Operator Panel and Rust bridge

```text
corepack pnpm@10.29.2 test
64 files passed; 200 tests passed

corepack pnpm@10.29.2 build
exit 0; TypeScript and Vite production build passed

cargo test --locked
26 passed; 0 failed
```

The Vite build retains its non-blocking large-chunk warning. Rust compilation
also displays the still-deferred legacy crate identity, which is explicitly
owned by the Operator Panel/Tauri identity phase rather than this environment
namespace task.

### Static and dependency checks

```text
git diff --check 4a797b4..2f15345
pass

git diff --name-only 4a797b4..2f15345 -- '*lock*' pyproject.toml package.json Cargo.toml
no output
```

No dependency or lock-file changes were made.

The tracked raw legacy-environment scan was reproduced without adding another
literal legacy token to this report:

```powershell
$first = 'BIN' + 'LIQUID_'
$second = 'AE' + 'GIS' + 'OS_'
git grep -n -I -E "$first|$second" HEAD --
```

It returns 57 classified lines containing 62 occurrences:

- 44 are immutable historical RFC, release-gate, sprint, or system-state
  records, including two historical UI/status reports;
- 4 are prior task verification reports that record the earlier phase
  boundaries;
- 7 are boundary and negative-contract examples in the tracked Task-3.2 brief;
- 2 are Task-4 domain enum identifiers and serialized runtime-kind values;

There are no raw legacy project-prefix matches in active runtime source,
configuration profiles, workflows, scripts, current operator guides, or active
tests. The negative tests construct former names at runtime and confirm they are
ignored/rejected.

## Brand inventory delta

The baseline at Task 3.1 completion was 1,254 findings. The final tracked Task
3.2 state, including the task brief, reports:

```text
legacy content: 1,052
legacy paths:       3
binary metadata:   19
total:           1,074
```

Net delta: **-180 findings**.

The inventory remains intentionally failing because later plan phases own the
remaining product, domain, panel/Tauri, bundled-runtime, evidence, fixture, and
documentation identities.

## Scope boundaries preserved

- No state migration or activation was performed.
- No state-root, runtime-kind, team identifier, metric, event, schema, generated
  contract, or bundled-manifest field was renamed outside this task.
- No signed evidence, historical report, RFC, release record, or archived
  artifact was edited.
- No compatibility alias or legacy environment fallback was added.
