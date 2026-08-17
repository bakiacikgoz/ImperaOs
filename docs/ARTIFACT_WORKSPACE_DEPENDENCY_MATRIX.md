# Artifact Workspace Dependency Matrix

- Status: Accepted decision baseline; bundled fallback adapters accepted
- Owner: MAIN / Artifact Workspace
- Authoritative sources: approved artifact workspace plan Task 1.1; `contracts/artifact_workspace/dependency_matrix.json`; official package documentation linked below
- Last verified: 2026-07-16 at Git commit `d79f5e4c40573ccd99dfd07eca4ca54c1b1f545c`
- Open decisions: optional commercial Handsontable and tldraw entitlements

## Decision

The root `pnpm-lock.yaml` is canonical. All new dependencies must be saved with exact versions. The app-local lockfile is a release blocker and must not be updated as a second authority. Renderer packages must work offline under a non-null Tauri CSP without remote CDNs or global `unsafe-eval`.

The machine-readable source is `contracts/artifact_workspace/dependency_matrix.json`; `scripts/check_artifact_workspace_compatibility.py` validates the decision baseline and supplies a fail-closed `--release` gate.

## Required Phase 2 pins

| Area | Exact packages | License | Gate/fallback |
|---|---|---|---|
| Assistant runtime | `@assistant-ui/react@0.14.26`, `ai@6.0.228`, `@ai-sdk/react@3.0.230` | MIT / Apache-2.0 | ImperaOS external store remains canonical; Tauri transport only; legacy workbench fallback |
| Document | `@blocknote/core@0.51.4`, `@blocknote/react@0.51.4` | MPL-2.0 | Remote embeds/uploads denied; plain Markdown fallback |
| Flow | `@xyflow/react@12.11.2` | MIT | Local CSS only; textual outline fallback |
| Code | `monaco-editor@0.55.1`, `@monaco-editor/react@4.7.0` | MIT | Local workers and local Monaco loader; CodeMirror fallback |
| Slides/export | `pptxgenjs@4.0.1`, `exceljs@4.4.0` | MIT | ArrayBuffer to native export ticket; no renderer file download |
| Forms | `react-hook-form@7.81.0`, `zod@4.4.3`, `@hookform/resolvers@5.4.0`, RJSF `6.6.2`, `ajv@8.20.0`, `ajv-formats@3.0.1` | MIT / Apache-2.0 | CSP-safe allowlisted validator and backend parity are implemented |
| Spreadsheet fallback | Repository-owned React grid over the strict spreadsheet contract | Project license | Formula evaluation disabled; bounded virtual row window; CSV/XLSX native export |
| Canvas fallback | Repository-owned React canvas over `CanvasContentV2` | Project license | Local shapes/free draw/assets only; remote embeds denied; JSON/SVG/PNG native export |
| UI/security/native | `lucide-react@1.24.0`, `react-resizable-panels@4.12.2`, `dompurify@3.4.12`, `@tauri-apps/plugin-dialog@2.7.1` | ISC / MIT / MPL-2.0-or-Apache-2.0 | Local assets, sanitized rendering, native dialog only |

## Deferred packages

`handsontable@18.0.0`, `@handsontable/react-wrapper@18.0.0`, and `tldraw@5.2.5` are not installable or activatable for production until a commercial/offline-compatible entitlement is recorded. Their commercial adapter capabilities remain off. The accepted fallback is the repository-owned, contract-preserving spreadsheet and canvas implementation; it adds no unapproved dependency and is selected automatically when entitlement is absent.

## Compatibility result

The dependency/CSP probe remains valid. Missing commercial entitlement is a documented adapter-selection result, not a release blocker, because both repository-owned fallback adapters are available. RJSF uses the bounded CSP-safe validator and requires no runtime code generation.

All required Phase 2 packages are exact-pinned in the root workspace lockfile. The redundant app-local lockfile was removed. Tauri CSP is non-null, local-only, and contains no `unsafe-eval`; editor-specific production probes remain required before their feature flags can open.

Run:

```powershell
.\.venv\Scripts\python.exe scripts/check_artifact_workspace_compatibility.py
.\.venv\Scripts\python.exe scripts/check_artifact_workspace_compatibility.py --release
```

The first command validates the decision artifact and reports commercial-package blockers. The release adapter gate accepts those blockers only when the corresponding bundled fallback capability is present; any unrelated blocker or missing fallback remains fail-closed.

## Official sources

- [assistant-ui ExternalStoreRuntime](https://www.assistant-ui.com/docs/runtimes/custom/external-store)
- [AI SDK custom transport](https://ai-sdk.dev/docs/ai-sdk-ui/transport)
- [BlockNote formats](https://www.blocknotejs.org/docs/foundations/supported-formats)
- [RJSF validation and precompile constraints](https://rjsf-team.github.io/react-jsonschema-form/docs/usage/validation/)
- [Monaco React local loader](https://github.com/suren-atoyan/monaco-react)
- [Tauri CSP](https://v2.tauri.app/security/csp/)
- [Handsontable license key rules](https://handsontable.com/docs/react-data-grid/license-key/)
- [tldraw licensing](https://tldraw.dev/community/license)
