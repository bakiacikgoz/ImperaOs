# ImperaOS Documentation Identity Design

Date: 2026-07-14
Status: Approved by delegated user authority
Plan task: Phase 8

## Objective

Move every tracked Markdown and text document to ImperaOS identity, including active operator guides, root-level setup material, historical status reports, RFCs, release evidence narratives, research notes, and internal implementation records. Rename the two remaining legacy-named documentation paths and keep all non-brand content byte-stable.

## Current State

The Phase 7.2 committed inventory reports 920 findings. Documentation accounts for the dominant share: 138 of 234 tracked Markdown/text files contain one of two former product families, and two documentation filenames still carry former identity. The affected set spans current instructions and historical records, so piecemeal editing would leave contradictory commands, paths, URLs, environment names, and product descriptions.

## Chosen Approach

Use a repository-wide, tracked-document migration with a byte-preserving replacement engine:

- enumerate only Git-tracked `*.md` and `*.txt` files;
- replace the two former product families in display, lowercase, uppercase, command, state-path, environment, package, metric, reverse-domain, and repository-name contexts;
- map both families to the appropriate ImperaOS casing;
- apply longest product/repository variants before shorter family variants;
- preserve all bytes other than the matched ASCII identity tokens, including newline style and BOM state;
- rename the two remaining documentation paths to `IMPERAOS_...` names;
- update tracked-document references through the same content migration;
- add a regression contract that enumerates tracked documentation through Git and rejects both former families in content and path names.

This approach treats historical documents as rebranded records: dates, statuses, measurements, decision outcomes, and technical claims remain unchanged, while product naming and operational examples become canonical. No compatibility alias is retained in documentation because the final brand gate must be clean.

## Casing Contract

The migration preserves semantic casing:

| Former context | Canonical result |
|---|---|
| Product display or repository display | `ImperaOS` |
| Lowercase command/package/path/metric context | `imperaos` |
| Uppercase environment/constant/path context | `IMPERAOS` |
| Repository URL segment | `ImperaOS` |
| Reverse-domain service context | `com.imperaos` |

The migration logic constructs former-family tokens from fragments so the regression source and design artifacts do not themselves create brand findings.

## Documentation Boundary

Included:

- root-level tracked Markdown/text documents;
- all tracked documents under `docs/`, including `docs/superpowers`;
- tracked application, research, and internal SDD Markdown/text records;
- command examples, filesystem paths, environment variables, package/module names, metric examples, repository URLs, headings, prose, and filenames inside those documents.

Excluded:

- Python, Rust, TypeScript, JSON, YAML, lockfiles, source comments, fixtures, snapshots, and binary metadata; Phase 9 owns them;
- generated or ignored inventory output;
- actual Git remotes, GitHub repository settings, branches, releases, packages, registries, or external systems;
- historical numeric results, dates, status decisions, hashes, and non-brand evidence content.

## File Renames

The two path migrations are:

- the enterprise theme-system document becomes `docs/IMPERAOS_ENTERPRISE_THEME_SYSTEM_v1.md`;
- the comprehensive v0.2x status document becomes `docs/IMPERAOS_V0.2X_KAPSAMLI_DURUM_RAPORU_2026-03-01.md`.

All tracked-document references to these paths must resolve to the canonical names after the content pass.

## Test Design

Follow RED-GREEN-REFACTOR:

1. Add `tests/test_documentation_brand_identity.py` before migrating documents.
2. Use `git ls-files -- '*.md' '*.txt'` to define the authoritative tracked-document set.
3. Construct both former families from smaller fragments and reject them case-insensitively in every tracked document's content and relative path.
4. Require both canonical renamed documents and reject their former path identities without embedding a forbidden token.
5. Require canonical README examples for CLI, state root, and environment prefix; repository URLs are validated wherever they already exist in tracked documentation.
6. Observe RED on the current 138 content-bearing documents and two paths.
7. Apply the byte-preserving migration and the two verified file moves.
8. Run the new contract plus documentation-consuming regression suites and Ruff.
9. Parse Markdown links sufficiently to ensure references to the two renamed files are canonical; do not attempt to repair unrelated pre-existing external links.
10. Run brand inventory at the committed implementation SHA and record the reduced Phase 9 baseline.

## Safety and Review

- The migration operates only on the exact Git-tracked document list.
- The helper records per-token and per-file replacement counts before commit.
- File moves are absolute-path boundary checked and non-recursive.
- A post-migration generic scan must return zero former-family content/path matches in tracked documents.
- `git diff --check` and a replacement-only audit must prove no unrelated byte changes.
- No external network, GitHub, registry, publishing, release, or remote Git operation occurs.
- Verification must not leave temporary artifacts directly under `C:\`.

## Acceptance Criteria

- Every Git-tracked Markdown/text file and path is free of both former product families.
- Both canonical documentation filenames exist and the former paths do not.
- README and operator-facing commands, paths, environment names, metrics, and URLs use ImperaOS.
- Historical dates, results, statuses, and evidence meaning remain intact.
- Documentation identity, existing documentation-consumer tests, and Ruff pass.
- The implementation report contains replacement counts, changed-file count, rename evidence, inventory delta, and no-external-action statement.
- The branch is ready for Phase 9 fixture/source/metadata cleanup.

## Commit Boundary

The implementation commit subject must be exactly:

`docs: publish all documentation under ImperaOS`
