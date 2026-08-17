# ImperaOS Documentation Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Canonicalize all Git-tracked Markdown/text content and paths to ImperaOS while proving that every document change is an identity-only byte transformation.

**Architecture:** Build the authoritative document set from Git, lock it with one permanent regression contract, then run a deterministic byte-replacement migration and two boundary-checked file moves. Verify the working tree against a replay of the same transformation before committing.

**Tech Stack:** Python, pytest, Ruff, Git, Markdown/text files

## Global Constraints

- Scope is exactly Git-tracked `*.md` and `*.txt` content plus two documentation path renames.
- Replace both former product families in every casing/context; keep all other bytes unchanged.
- Apply longer repository/product variants before shorter family variants.
- Preserve newline encoding, BOM state, dates, numeric results, statuses, hashes, and non-brand prose.
- Do not edit source code, JSON/YAML fixtures, lockfiles, or binary metadata in this phase.
- Do not mutate the actual Git remote, GitHub repository, packages, registries, releases, or external systems.
- Use boundary-checked non-recursive moves for the two files.
- Do not create temporary output directly under `C:\`; remove all agent-owned temp files.
- The implementation commit subject must be exactly `docs: publish all documentation under ImperaOS`.

## File Structure

- `tests/test_documentation_brand_identity.py`: permanent Git-tracked documentation content/path contract.
- Every matched tracked `*.md`/`*.txt`: byte-preserving identity replacements only.
- `docs/IMPERAOS_ENTERPRISE_THEME_SYSTEM_v1.md`: canonical enterprise-theme path.
- `docs/IMPERAOS_V0.2X_KAPSAMLI_DURUM_RAPORU_2026-03-01.md`: canonical historical status path.
- `.superpowers/sdd/task-8-documentation-migration-handoff.md`: ignored execution evidence.
- `.superpowers/sdd/task-8-report.md`: durable verification report.

---

### Task 1: Documentation Identity Contract and Migration

**Files:**
- Create: `tests/test_documentation_brand_identity.py`
- Modify: all matched Git-tracked `*.md` and `*.txt`
- Rename: two former-named files under `docs/` to the canonical paths listed above

- [ ] **Step 1: Write the failing tracked-document contract**

The test must:

1. Run `git ls-files -- '*.md' '*.txt'` from the repository root and require a non-empty result.
2. Construct the former families without embedding a contiguous finding:

```python
family_one = "bin" + "liquid"
family_two = "ae" + "gis"
```

3. Casefold every tracked document path and UTF-8-decoded content, collecting any match for either family.
4. Assert the violation list is empty with relative paths in the failure message.
5. Require the two canonical `docs/IMPERAOS_...` paths.
6. Require README to contain canonical `uv run imperaos`, `.imperaos`, and `IMPERAOS_` examples. Do not add a repository URL that is absent from the base README; existing URLs elsewhere remain covered by the generic scan.

Use `utf-8-sig` for the scan so a BOM does not affect text matching. Do not write any document in the test.

- [ ] **Step 2: Run RED and capture the baseline**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_documentation_brand_identity.py
```

Record the exact number of tracked documents, content-bearing documents, content violations, and path violations from a separate read-only baseline command. Expected baseline: 234 tracked documents, 138 content-bearing documents, and two legacy-named paths before the new clean plan/spec files are counted at execution time.

- [ ] **Step 3: Build the deterministic byte mapping**

Use these constructed roots:

```python
family_one_title = "Bin" + "Liquid"
family_one_lower = family_one_title.lower()
family_one_upper = family_one_title.upper()
family_two_root = "Ae" + "gis"
family_two_title = family_two_root + "OS"
family_two_lower = family_two_title.lower()
family_two_upper = family_two_title.upper()
```

Apply byte replacements in this order:

```text
family_one_title + "AI" -> ImperaOS
(family_one_title + "AI").lower() -> imperaos
(family_one_title + "AI").upper() -> IMPERAOS
family_two_title -> ImperaOS
family_two_lower -> imperaos
family_two_upper -> IMPERAOS
family_one_title -> ImperaOS
family_one_lower -> imperaos
family_one_upper -> IMPERAOS
family_two_root -> ImperaOS
family_two_root.lower() -> imperaos
family_two_root.upper() -> IMPERAOS
```

Enumerate paths from Git, read/write bytes, and write only when transformed bytes differ. Record each changed path and replacement count in the ignored handoff. Because this is a bulk mechanical rewrite across more than one hundred files, a deterministic byte-rewrite helper is permitted; do not use it for non-mechanical prose edits.

- [ ] **Step 4: Perform the two verified file moves**

Resolve repository root, both source paths, and both destination paths to absolute paths. Confirm all four stay within `<repo>\docs`, both sources exist, and neither destination exists. Then use native PowerShell `Move-Item -LiteralPath` for non-recursive moves.

Source names must be constructed from the same family fragments rather than embedded contiguously. Destinations are:

```text
docs/IMPERAOS_ENTERPRISE_THEME_SYSTEM_v1.md
docs/IMPERAOS_V0.2X_KAPSAMLI_DURUM_RAPORU_2026-03-01.md
```

- [ ] **Step 5: Run GREEN and documentation consumers**

Run with a worktree-local ignored basetemp:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_documentation_brand_identity.py `
  tests/test_bundled_runtime_identity.py `
  tests/test_design_partner_mainline_handoff.py `
  tests/test_observability_identity.py `
  tests/test_automation_distribution_identity.py `
  tests/test_brand_consistency_gate.py
.\.venv\Scripts\python.exe -m ruff check tests/test_documentation_brand_identity.py
```

Expected: all selected tests and Ruff pass.

- [ ] **Step 6: Prove replacement-only semantics**

Before staging, replay the byte mapping against every base-HEAD tracked Markdown/text file:

- unchanged files must equal their base bytes;
- changed same-path files must equal `transform(base_bytes)`;
- each canonical rename destination must equal `transform(base source bytes)`;
- the only new non-document-migration file is `tests/test_documentation_brand_identity.py`;
- the only deleted paths are the two verified rename sources.

Fail if any byte differs outside the deterministic mapping. Record transformed-file count and total replacement count.

- [ ] **Step 7: Run the final generic scan and commit**

Run the permanent test again, `git diff --check`, inspect rename detection and `git status --short`, then stage exactly the test plus all transformed/renamed documents. Commit:

```powershell
git commit -m "docs: publish all documentation under ImperaOS"
```

Expected: no tracked Markdown/text content or path contains either former family.

---

### Task 2: Phase 8 Verification Evidence

**Files:**
- Create: `.superpowers/sdd/task-8-report.md`

- [ ] **Step 1: Run committed-HEAD inventory**

Run the brand consistency gate in inventory mode into ignored `.superpowers/sdd/task-8-brand-inventory`. Verify the SHA matches Task 1 and record category/classification counts and the delta from Task 7.2's 920-finding baseline.

- [ ] **Step 2: Create the durable report**

Use these sections:

```markdown
# Phase 8 Documentation Identity Verification Report

## Scope
## Implementation Commit
## RED Evidence
## Migration Counts
## File Renames
## Replacement-Only Audit
## Focused GREEN Evidence
## Tracked Documentation Scan
## Brand Inventory and Delta
## Historical-Record Semantics
## External-Action Boundary
## Temporary-Artifact Cleanup
## Final Status
```

Record actual file/replacement counts, exact test results, inventory SHA/counts, and the fact that historical facts were preserved while naming was canonicalized.

- [ ] **Step 3: Verify and commit the report**

Cross-check raw JSON and handoff, run `git diff --check`, and commit only `.superpowers/sdd/task-8-report.md` with subject `docs: record phase 8 documentation verification`. Leave generated inventory ignored.

- [ ] **Step 4: Complete independent reviews**

Require implementation spec/code-quality review and final combined implementation/report review. Review must sample active guides, historical reports, root README/setup docs, internal plans, both path renames, replacement-only audit evidence, and inventory delta. Fix every Critical or Important issue and obtain an explicit Ready for Phase 9 decision.
