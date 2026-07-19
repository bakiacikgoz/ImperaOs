# Sprint 5.6 Merge Qualification

## Real Acceptance Prereqs

- macOS with Safari installed
- `IMPERAOS_ENABLE_REAL_COMPUTER_USE_TESTS=1`
- Terminal / Codex app allowed to automate Safari and System Events
- Accessibility permission granted for UI scripting
- Safari Developer setting `Allow JavaScript from Apple Events` enabled manually
- Deterministic local fixture server available on `127.0.0.1`

## Repro Commands

```bash
pnpm --dir apps/operator-panel test
pnpm --dir apps/operator-panel lint
pnpm --dir apps/operator-panel build
cargo fmt --check
cargo check
uv run ruff check imperaos/computer_use apps/operator-panel/src-tauri/src tests/test_computer_use.py tests/test_computer_use_world_model.py tests/test_computer_use_runtime.py tests/test_computer_use_acceptance.py tests/test_operator_contracts.py tests/test_team_cli.py
uv run pytest tests/test_computer_use.py tests/test_computer_use_world_model.py tests/test_computer_use_runtime.py tests/test_operator_contracts.py tests/test_team_cli.py -q
IMPERAOS_ENABLE_REAL_COMPUTER_USE_TESTS=1 uv run pytest tests/test_computer_use_acceptance.py -q
```

## 2026-03-14 Qualification Result

- Environment confirmed: macOS 26.3.1, `osascript` available, Safari launchable
- Manual Safari prerequisite satisfied on the qualification machine:
  - Developer menu visible
  - `Allow JavaScript from Apple Events` enabled
  - Automation / Accessibility permissions granted
- Full real Safari acceptance completed with `IMPERAOS_ENABLE_REAL_COMPUTER_USE_TESTS=1`
- Result: `5 passed`

Executed real scenarios:

- upload fixture file through Safari file input
- surface drift fail-closed on unexpected tab change
- direct-link download into scoped runtime path
- pause and resume during a live browser flow
- operator stop during a live browser flow

Qualification fixes landed during this phase:

- `launch_app` / `focus_window` no longer fail pre-action surface verification when another app is frontmost
- real Safari acceptance tests now reset Safari state between runs and assert safe-checkpoint semantics correctly
- upload dialog timing is more tolerant to real macOS sheet startup
- direct-link downloads now use page-discovered link metadata plus scoped runtime fetch, avoiding flaky Safari native download-manager polling for this slice

## Triage

### Blocker

- None remaining for the current controlled browser slice qualification

### High-Value Follow-Up

- Add a doctor/preflight check that detects missing Safari `do JavaScript` capability before starting real acceptance or live browser execution
- Broaden download qualification beyond direct-link artifacts to authenticated/session-bound browser downloads

### Known Boundary

- Real Safari validation remains opt-in and permission-dependent
- Current slice is still controlled, fail-closed, and browser-centered
- Direct-link downloads are now qualified on a real machine; broader authenticated browser downloads are not yet separately qualified
- Cross-platform parity and unrestricted desktop autonomy are not in scope for this release

## Operator Smoke Status

- Automated workspace/state mapping remains green via frontend tests
- Real runtime qualification is green on a machine with the Safari developer prerequisite enabled
- Operator-panel smoke is still represented primarily by test-backed transcript/timeline/control mapping plus the real runtime acceptance runs above

## Merge Checklist

- [x] frontend build / lint / test green
- [x] cargo fmt / check green
- [x] python ruff / pytest green
- [x] gated real acceptance passed on a machine with Safari JavaScript automation enabled
- [x] runtime blocker for desktop activation preflight fixed
- [x] known boundary note updated

## Merge Recommendation

**Go:** the controlled, fail-closed, browser-centered computer-use slice is now qualified on a real Safari machine for upload, drift fail-closed, download, pause/resume, and stop. Merge should still preserve the documented boundaries around manual Safari prerequisites and the narrower qualification of direct-link downloads.
