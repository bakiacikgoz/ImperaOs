# Current Frontend Release Decision - 2026-05-24

Status: FRONTEND FUNCTIONAL GATE GREEN

This decision supersedes the earlier frontend-only blocker list that said AI
Assistant model selection was not wired. The 2026-05-23 release readiness
snapshot remains a separate date-specific artifact.

## Current state

Operator Panel frontend functional completion is green for Faz 2, Faz 3, and
Faz 4 scope.

Evidence:

- `artifacts/operator-panel-ui/FRONTEND_FUNCTIONAL_GAP_REPORT.md`
- `artifacts/operator-panel-ui/qa-summary.md`
- `artifacts/operator-panel-ui/tauri-bridge-smoke.json`
- `artifacts/operator-panel-ui/tauri-smoke/report.json`
- `artifacts/operator-panel-ui/live-cli-smoke.json`

## Closed frontend blockers

- AI Assistant provider/model/fallback/HF model selection is wired.
- Assistant composer no longer exposes the hard-coded disabled `ImperaOS-Pro`
  model control.
- `useAssistantSession` passes provider, fallback provider, model, and HF model
  ID into `startAssistantTurn` options.
- Placeholder/no-op/release-blocking dead controls are cleared from the audited
  UI surface.
- Page-level control inventory has 0 critical, 0 high, and 0 medium findings.

## UI functional QA status

- Total controls: 127.
- Working controls: 99.
- Disabled with explicit reason: 28.
- Removed until ready: 0.
- Missing handlers: 0.
- No-op handlers: 0.
- Disabled without explicit reason: 0.
- Controls with test coverage evidence: 127/127.

## Bridge confidence

- Preview E2E: PASS.
- Bridge unit tests: PASS.
- Tauri bridge smoke: PASS.
- Tauri launched smoke reportability: PASS/CONDITIONAL depending on whether
  `--launch` was run on a real macOS desktop session.
- Live CLI smoke: PASS for read-only capabilities/config commands.

The live Tauri desktop window is not used to claim unrestricted automation,
public desktop release readiness, or guaranteed real model execution. The
bridge confidence is based on TypeScript invoke contract tests, Rust bridge
tests, command-argument validation, stdio-json event parsing smoke, read-only
CLI smoke, and the macOS local trial launched smoke report when run manually.

## Green gates

- `corepack pnpm --dir apps/operator-panel qa:frontend`: PASS.
- `cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml`:
  PASS, 23 tests.
- `uv run python -m imperaos operator capabilities --json`: PASS.
- `uv run python -m imperaos config resolve --profile balanced --json`: PASS.

## Remaining no-ship boundaries

- Do not claim unrestricted live computer-use automation.
- Do not claim live assistant execution against a real provider/model from this
  frontend decision alone.
- Do not treat preview E2E as proof of a launched production Tauri desktop app.
- Treat launched smoke without full desktop bridge instrumentation as partial
  evidence, not a public release claim.
- Do not ship public desktop artifacts without the existing signing,
  notarization, clean-machine, and promote-gate evidence required by the main
  release decision.

## Next single local-trial check

For personal macOS M4 source/dev confidence, run:

```bash
uv run python scripts/run_macos_local_trial_gate.py --profile enterprise --json
OPERATOR_PANEL_TAURI_LAUNCH=1 corepack pnpm --dir apps/operator-panel exec tsx scripts/tauri-launched-smoke.ts --launch
```

If no real assistant model/provider is configured, `setup_required` or
`conditional` is acceptable for local trial, but it must not be reported as a
fake assistant success.
