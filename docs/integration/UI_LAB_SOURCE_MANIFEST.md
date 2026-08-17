# ImperaOS UI Lab source manifest

- Source path: `/Users/baki/Documents/ImperaOS-UI-Lab`
- Frozen source SHA: `165208e90dd37376d5f0a21df22b7a1e7756aab5`
- Target base SHA: `0a9c4ea5a6e26a3b32a9dd327ec1d7154ac39376`
- Source validation: 39 Node tests passed; `pnpm lint` and `pnpm build` passed on 2026-07-25.

## Imported design contract

The source supplies the visual product model: the three-column shell, task hierarchy,
composer, conversation, workspace, context rail, bottom dock, collections and settings.
Its React 19/Vite/Tauri 2 dependencies were reconciled with the Operator Panel's React
19/Vite/Tauri 2 stack. The target adds `react-router-dom` 7.18 and `zustand` 5.0.

## Explicitly not imported into production

`src/mocks/**` and `src/stores/demoStore.ts` are fixtures only. Product Shell loads no
module from the UI Lab checkout and no mock module. Runtime actions are delegated to the
existing Operator Panel bridge, assistant runtime and Artifact Workspace.

## Style decision

The source's tokens and surface grammar are recreated in the scoped
`.imperaos-product-shell-v2` namespace, preventing a global CSS collision with the legacy
panel while preserving its information density and dark/light palette.

## Integration status

Implemented on this branch: the Product Shell/router/preferences; workspace-scoped SQLite
projects, tasks, messages, links and preferences; the existing sidecar/Tauri clients;
governed project/task/artifact/approval/agent search; real first-turn task creation and
session correlation; durable transcripts; governed model/context/tool composer controls; a
user-started native PTY/xterm surface; and mode-scoped native browser/preview child-webview
policy with redirect checks, isolated agent profiles, registered local preview origins and
explicit approval prompts for popups, downloads and external applications.

The V2 implementation work is complete on this branch: governed Artifact
Workspace/runtime tab hosting, multi-session terminal preservation and project-root
registration, durable assistant-message action references, task context/activity data and
the collections/settings surfaces are all connected to the product runtime rather than a
demo store. Task pinning, ordering and archival, as well as direct durable task reload,
are backed by the Product Workspace store.

The automated release checks pass. The GUI launch probe verifies that the Tauri desktop
process starts and remains alive; live bridge instrumentation and an assistant turn remain
explicitly conditional on a desktop automation harness and a locally qualified assistant
runtime. Those prerequisites are not represented as a mock or a successful response.
