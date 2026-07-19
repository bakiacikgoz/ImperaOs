# RFC 008: macOS Live Fixture Qualification

## Status

Implemented as a fail-closed evidence gate. This phase does not enable
unrestricted desktop automation.

## Scope

Phase 4B qualifies only supervised local macOS fixtures:

- `local_browser_form`
- `textedit_safe_typing`
- `finder_fixture_file`
- `sensitive_surface_stop`
- `terminal_deny`

The report scope is `supervised_local_fixtures`. Windows and Linux remain not
qualified for live execution.

## Required Opt-In

The live fixture command must see explicit one-run opt-in values:

```text
IMPERAOS_COMPUTER_USE_LIVE_MACOS=1
IMPERAOS_COMPUTER_USE_SUPERVISED_FIXTURE_ONLY=1
IMPERAOS_COMPUTER_USE_REQUIRE_STEP_APPROVAL=1
IMPERAOS_COMPUTER_USE_ACK=I understand ImperaOS will control my macOS desktop only for local supervised fixtures.
```

Without those exact values, the report is `blocked`, `qualificationPassed=false`,
and all fixtures remain `skipped`.

## Report And Replay

The canonical report path is:

```text
artifacts/computer_use/macos_qualification_report.json
```

The report includes host metadata, provider readiness, permission states,
fixture results, local fixture artifact paths, redacted event log path, replay
audit path, limitations, blockers, and safety invariants. Raw screenshot
persistence must remain `0`.

Replay verification:

```bash
uv run imperaos computer-use replay \
  --report artifacts/computer_use/macos_qualification_report.json \
  --verify \
  --json
```

For blocked reports this command may exit zero when replay/audit integrity is
valid. Qualification status and replay integrity are separate dimensions:
`qualificationPassed=false` can coexist with `replayIntegrityVerified=true`.

## Operator Stages

- `fixture_qualified`: a fresh matching local fixture report exists, but
  `macos_live_enabled=false`.
- `permission_ready`: local permissions and input/capture are ready, but the
  provider is not ready.
- `provider_ready`: provider is ready, but fresh qualification evidence is
  missing or invalid.
- `qualified_limited`: all macOS gates pass and `liveEnabled=true`.

Any missing opt-in, stale report, commit/config mismatch, missing permission,
disabled backend, unsafe screenshot policy, terminal policy drift, or sensitive
surface policy drift keeps the runtime fail-closed.
