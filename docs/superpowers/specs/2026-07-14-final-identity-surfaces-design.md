# ImperaOS Final Identity Surfaces Design

**Date:** 2026-07-14  
**Phase:** 9  
**Status:** Approved by the standing execution authorization

## Objective

Close the remaining active identity surfaces after the documentation migration while preserving compatibility checks that intentionally reason about former product-family names.

The phase starts from the verified Phase 8 inventory:

- 69 blocking text findings
- 0 path findings
- 19 binary assets requiring manual review
- 0 generated-artifact findings

## Scope

### Runtime and product strings

Canonicalize remaining prompts, remediation text, permission guidance, browser identity, support archive names, example commands, generated links, and fixture values to ImperaOS.

### Compatibility assertions

Some tests must continue to prove that former package, environment, and storage names are rejected or absent. Those names will be assembled from non-matching fragments inside tests so the compatibility assertion remains meaningful without reintroducing a literal retired identity into the repository inventory.

### Desktop artwork

Use the operator panel's existing code-native `hex` mark as the single visual source. Add a deterministic SVG source with a dark rounded background and the established nested-hex geometry, then regenerate the Tauri desktop icon set from that source.

Artificially generated raster artwork is out of scope because the repository already has a suitable code-native brand primitive.

### Obsolete screenshots

Delete the three unreferenced planning screenshots that visibly contain a former product identity. They are not runtime inputs, documentation dependencies, or release assets.

## Verification contract

The phase is complete only when:

1. focused Python, TypeScript, and Rust tests pass;
2. the desktop icon source and generated binary set pass structural validation;
3. the brand inventory reports zero blocking findings;
4. any remaining binary findings are documented, inspected ImperaOS assets;
5. no test artifacts remain directly under `C:\`;
6. the worktree is clean after the phase report is committed.

## Rollback boundary

Source and fixture changes, screenshot deletions, and generated icons are isolated in Phase 9 commits. Reverting those commits restores the Phase 8 state without touching the earlier package, runtime, distribution, security, or documentation migrations.
