# Task 2.1 Implementation Report

## Scope completed

- Renamed the tracked legacy Python package directory to `imperaos/` with `git mv`.
- Updated Python imports and module-path references under `imperaos/`, `tests/`,
  `scripts/`, `benchmarks/`, and `research/`, including dotted monkeypatch targets,
  dynamic module strings, `python -m` invocations, and package-directory references.
- Updated affected package docstrings and `imperaos/__main__.py`.
- Added `imperaos/product_identity.py`, containing a frozen, slotted
  `ProductIdentity` dataclass, deterministic canonical JSON loading, exact field/value
  validation, `PRODUCT_IDENTITY`, and the explicit `load_product_identity()` API.
- Expanded `tests/test_brand_identity.py` with canonical parity, immutability, and
  missing/unexpected/non-string/mismatched-value rejection coverage. The forbidden
  legacy package spelling in the mismatch fixture is assembled at runtime.
- Preserved legacy runtime environment stems and state paths for their later migration
  task, and did not modify `pyproject.toml` or `uv.lock`.

## Changed files

- Staged task diff: 603 files (including this report), comprising 286 package-tree
  path moves plus namespace consumer/test updates and the new identity module.
- Renamed the legacy Python package tree to `imperaos/**/*.py`.
- Added: `imperaos/product_identity.py`.
- Updated namespace consumers: tracked Python files under `tests/`, `scripts/`,
  `benchmarks/`, and `research/`.
- Updated identity tests: `tests/test_brand_identity.py`.
- Added this report: `.superpowers/sdd/task-2.1-report.md`.

## TDD evidence

### RED

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_brand_identity.py -q --basetemp C:\t\t21id-red
```

Observed exit code `1` during collection with the expected cause:

```text
ModuleNotFoundError: No module named 'imperaos.product_identity'
```

### GREEN

After the minimal loader implementation, the targeted test returned exit code `0`:

```text
..........                                                               [100%]
```

The fresh acceptance rerun produced the same `10 passed` result.

## Verification

Environment PATH was prefixed as required by the task brief.

| Check | Result |
|---|---|
| `pytest tests/test_brand_identity.py -q --basetemp C:\t\t21id` | exit `0`; 10 passed |
| `python -m compileall -q imperaos` | exit `0`; no output |
| `pytest --collect-only -q --basetemp C:\t\t21collect` | exit `0`; 857 tests collected |
| Legacy Python module namespace guard | pass; no legacy imports, dotted module targets, `python -m` module names, or package-directory references |
| `ruff check imperaos/product_identity.py tests/test_brand_identity.py` | exit `0`; all checks passed |
| `git diff --check` | exit `0`; no whitespace errors |
| `git status --short -- pyproject.toml uv.lock` | no output; both boundary files unchanged |

The requested broad Ruff run over `imperaos tests scripts benchmarks research` found
only two existing E501 violations on unchanged lines:

- `imperaos/model_providers/registry.py:59` (109 > 100)
- `imperaos/runtime/config.py:1007` (103 > 100)

All Ruff findings introduced in the new identity module/tests were fixed, and the
focused authored-file run is clean.

## Brand inventory delta

Inventory mode completed with exit code `0`. The audit status remains `fail`, as
expected before the later rebrand tasks finish.

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Findings | 3,851 | 1,666 | -2,185 |
| Legacy content matches | 3,543 | 1,644 | -1,899 |
| Legacy path matches | 289 | 3 | -286 |
| Scanned files | 1,503 | 1,505 | +2 |

## Known Task 2.2 dependency

Distribution metadata, wheel package configuration, and the installed console entry
point still reference the old distribution/package configuration by design. Packaging
and installed console-entrypoint tests therefore remain dependent on Task 2.2 and were
not forced into Task 2.1 scope.
