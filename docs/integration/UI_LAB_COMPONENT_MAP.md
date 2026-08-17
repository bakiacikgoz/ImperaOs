# UI Lab component map

Canonical source: `/Users/baki/Documents/ImperaOS-UI-Lab` at
`165208e90dd37376d5f0a21df22b7a1e7756aab5`.

| UI Lab source | Product Shell destination | Real product binding retained |
| --- | --- | --- |
| `src/styles/{tokens,globals,surfaces}.css` | `product-shell/styles/ui-lab/*.css`, `ProductTheme.tsx` | Exact frozen CSS and dark/light theme state; product routes only |
| `src/app/App.tsx` | `ProductShellApp.tsx`, `router/ProductRouter.tsx` | Hash router, durable routes and isolated `/system/*` rollback |
| `src/shell/AppShell.tsx` | `shell/AppShell.tsx`, `shell/TopBar.tsx` | Product route state, real shell controls and preferences |
| `src/shell/Sidebar.tsx` | `shell/Sidebar.tsx` | Durable projects/tasks, native folder registration, pin and archive |
| `src/shell/GlobalSearch.tsx` | `shell/GlobalSearch.tsx` | Real project/task/artifact/approval results and routing |
| `src/pages/NewWorkPage.tsx` | `pages/NewWorkPage.tsx` | Durable task/message creation and governed assistant start |
| `src/composer/Composer.tsx` | `components/assistant/AssistantComposer.tsx` (`product` variant) | Model discovery, runtime profiles, context attachments, safe tools, slash commands, send/cancel |
| `src/pages/TaskPage.tsx` | `pages/TaskPage.tsx` | Durable task lookup, live assistant session and persisted layout split |
| `src/conversation/ConversationView.tsx` | `conversation/ProductConversationView.tsx` | Persisted/live messages, run state, governed artifacts, approvals, copy/regenerate/cancel |
| `src/workspace/WorkSurface.tsx` | `workspace/WorkSurface.tsx`, `WorkspaceTabs.tsx` | Canonical Artifact Workspace, native browser/preview, PTY terminal |
| `src/context-rail/ContextRail.tsx` | `context-rail/ContextRail.tsx` | Real run, approval, artifact, policy and safe-control state |
| `src/bottom-dock/BottomDock.tsx` | `bottom-dock/BottomDock.tsx` | Real audit/activity metrics and persisted dock sizing |
| `src/browser/*` | `browser/BrowserSurface.tsx`, `PreviewSurface.tsx`, `BrowserApprovalInbox.tsx` | Mode-specific native origin policy, isolated agent session, redirect revalidation and explicit approvals |
| `src/pages/{Library,Approvals,Agents,Automations}*` | `pages/CollectionPage.tsx`, `GovernedCollections.tsx` | Canonical artifact, approval and agent bridges; honest empty scheduled-work state |
| `src/settings/SettingsShell.tsx` | `settings/SettingsShell.tsx` | Persisted product settings and explicit advanced-system route |
| Reference responsive hierarchy | `e2e/ui-lab-theme-parity.spec.ts`, `scripts/capture-ui-lab-parity.ts` | Five viewports, dark/light, source/target evidence pairs |

All target modules are owned by this repository. Production code does not import
the UI Lab checkout, `src/mocks/**`, or `src/stores/demoStore.ts`. The parity
capture fixture exists only in the Playwright script and cannot become a native
runtime fallback.
