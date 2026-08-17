# Artifact Workspace Final Closure Design

**Status:** Approved for implementation by the user-provided final completion plan
**Owner:** MAIN / Artifact Workspace
**Authoritative sources:** `IMPERAOS_ARTIFACT_WORKSPACE_FINAL_TAMLAMA_PLANI.md`; current branch source and contracts
**Last verified:** 2026-07-19 at `efa3157`
**Open decisions:** None

## Outcome

Close the remaining gap between the existing governed Artifact Workspace foundation and the product-level acceptance criteria. Commercial Handsontable/tldraw capabilities remain fail-closed. The bundled spreadsheet and canvas adapters become the supported fallback capabilities and are reported truthfully through backend rollout state and operator UI.

## Architecture

Python remains the only rollout and artifact authority. Named rollout profiles resolve to the existing feature-flag contract; the runtime capability snapshot reports the effective flag state, each artifact kind's edit/export status, the selected adapter, and a bounded reason code. Renderer build flags may still disable a surface but cannot enable backend operations.

React keeps bounded draft and selection state only. Spreadsheet and canvas editors emit the existing strict `SpreadsheetContentV2` and `CanvasContentV2` shapes through the common autosave queue. Free drawing is encoded as bounded line segments, preserving `CanvasContentV2` instead of adding executable or arbitrary payloads. The fallback editors never evaluate formulas, fetch remote assets, render arbitrary HTML, or persist canonical data in browser storage.

Exports use one workbench dialog and the existing native ticket boundary. The dialog exposes format, suggested filename, revision, data class, policy state, estimated size, and the native destination warning. Each supported format is serialized locally, then committed through a single-use backend-authorized ticket. Form submission exports use only the current memory-only session response and never introduce browser persistence.

## Components

### Rollout and capability

- Add exact `artifact_workspace_off`, `artifact_workspace_core`, and `artifact_workspace_full` profiles.
- Extend the runtime snapshot with per-kind `enabled`, `editable`, `exportable`, `reasonCode`, `requiresLicense`, and `adapter` fields.
- Add a dedicated Artifact Workspace capability card to Settings; no environment values, secrets, or license material are rendered.
- Keep legacy assistant/workbench behavior available when the workspace gate is off.

### Spreadsheet fallback

- Preserve sparse cells, columns, sheet IDs/names, and `calculationMode=disabled`.
- Add anchor/focus range selection, keyboard extension, copy/paste, clear range, sheet add/rename, row/column growth, and a bounded virtual row window.
- Emit spreadsheet selection ranges to assistant context and existing autosave/revision/conflict infrastructure.
- Keep CSV/XLSX export and formula-injection hardening.

### Canvas fallback

- Preserve the strict shape allowlist and local `assetId` boundary.
- Add free-draw mode as bounded line segments, selection deletion, object renaming/text editing, multi-select, undo/redo, zoom/pan, and existing move/resize behavior.
- Preserve remote embed/asset denial and JSON/SVG/PNG export.

### Export surface

- Use one format matrix shared by workbench controls and the dialog.
- Support Document JSON/Markdown/HTML; Form Schema JSON/Submission JSON/CSV; Code Source/TXT; Flow JSON/SVG/PNG; Spreadsheet CSV/XLSX; Canvas JSON/SVG/PNG; Slides PPTX/JSON.
- Route every export through the existing begin/cancel/commit ticket lifecycle.
- Show bounded success metadata through the existing operation notice without exposing absolute paths.

### Release truth

- Update the release gate to distinguish commercial capabilities (forced off) from bundled fallback capabilities (available when rollout-enabled).
- Update operator/release documentation so it no longer claims spreadsheet and canvas are unavailable without commercial entitlements.
- GitHub Actions are not invoked in this completion run; local targeted verification and the mandatory local release gate provide the available evidence.

## Error handling and security

- Invalid content, range, selection, asset identity, profile, or export format fails closed.
- Archived artifacts remain read-only; dirty, saving, conflicted, or failed drafts cannot export.
- Export cancellation is not reported as an error; pre-commit failures cancel the ticket.
- Renderer configuration cannot manufacture backend rollout, license, approval, or export authority.
- No direct provider call, code execution, arbitrary path import, remote embed, or raw stack trace is introduced.

## Verification strategy

Use red-green focused tests for each new behavior. Run only affected Python/Vitest tests during implementation, then the plan's local minimum gates and one final artifact workspace release gate. Do not invoke GitHub Actions.
