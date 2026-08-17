# Browser Origin Policy

This policy is enforced per browser mode. There is no global allow-origin
switch and a decision in one mode never grants access in another mode.

## User browser

- An address explicitly submitted through the user browser may use `https`.
- `http`, `file`, `javascript`, `data`, `tauri`, and `asset` are denied.
- Every navigation, including a redirect, is checked again against this rule.

## Preview browser

- A preview may use only an exact `localhost` or `127.0.0.1` origin that the
  trusted ImperaOS runtime registered with an explicit port.
- The renderer cannot register preview origins. Arbitrary local ports are
  denied, as are host, scheme, or port substitutions during redirects.
- The trusted desktop launcher may bootstrap task-owned preview origins through
  `IMPERAOS_BROWSER_DEPLOYMENT_POLICY_JSON` before the renderer starts. Invalid
  or oversized policy fails closed.

## Agent browser

- An agent session requires both a task ID and a domain from that task's
  trusted task/deployment allowlist.
- It may use only `https` to an exact allowed domain. Missing or empty policy
  fails closed.
- Each agent window has a fresh browser profile; it cannot read user browser
  cookies or reuse the user session.
- Trusted task/deployment domain allowlists use the same startup policy
  envelope; the renderer cannot extend them.

## External effects

- Redirects are rechecked under their session's mode policy.
- Back/forward is a native record of ImperaOS-issued navigations, not a
  remote-page JavaScript integration. Each selected history URL is checked
  again before navigation.
- `file`, `javascript`, `data`, `tauri`, and `asset` are content/internal
  schemes, not external applications: they remain denied and no approval can
  turn them into an executable route.
- New windows are denied until the user explicitly approves reopening the URL
  in the originating governed browser tab. A popup never creates an unmanaged
  top-level window or inherits ambient approval.
- Downloads and external application schemes remain blocked after notifying
  the user. They require a future governed save/approval workflow; an
  acknowledgement is not an approval to execute.
- The main renderer can report only the measured reserved viewport for a known
  browser session. Native code rejects unknown sessions, non-finite, negative,
  zero, or oversized bounds; geometry does not grant navigation or origin
  authority. Inactive workspace tabs hide their matching child webview so it
  cannot remain as an unmanaged overlay or cover an approval dialog.

## Enforcement

The policy and its runtime registries live in
`apps/operator-panel/src-tauri/src/browser.rs`. Browser webviews have separate
data directories by mode. The default Tauri capability applies only to the
`main` webview, so remote child webviews do not receive renderer IPC
permissions.
