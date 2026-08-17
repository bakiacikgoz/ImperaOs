# Sprint 2 Acceptance Checklist

Date: 2026-03-13

## Contract Freeze

- `PASS` Capability schema, preview fixture bundle, run summary/detail, approval detail, tail events, artifact payloads, and device action snapshot are typed and checked.
  Evidence: `imperaos/contracts/operator_panel.py`, `tests/test_operator_contracts.py`
- `PASS` Shared preview fixtures are contract-shaped and backed by checked-in examples.
  Evidence: `contracts/operator_panel/fixtures/operator_panel_preview.json`, `apps/operator-panel/src/previewFixtures.ts`
- `PASS` Contract schemas are generated into the repo.
  Evidence: `contracts/operator_panel/schemas`

## Operator Acceptance Flows

- `PASS` Scenario 1: basic task submit, status visibility, replay visibility, artifact export payload.
  Evidence: `tests/test_team_cli.py`, `tests/test_operator_contracts.py`
- `PASS` Scenario 2: approval pending -> approve -> continue.
  Evidence: `tests/test_team_cli.py`
- `PASS` Scenario 3: approval reject / non-executed ticket does not continue.
  Evidence: `tests/test_team_cli.py`
- `PASS` Scenario 4: resume flow keeps run lineage and replay payload shape.
  Evidence: `tests/test_team_cli.py`
- `PASS` Scenario 5: stale snapshot / drift warnings remain surfaced through frozen event vocabulary and replay consistency counters.
  Evidence: `tests/test_computer_use.py`, `apps/operator-panel/src/bridge.test.ts`
- `PASS` Scenario 6: run workspace sections read the same run truth source (`status.json`, `tasks.json`, `handoffs.json`, `audit_envelope.json`, `events.jsonl`).
  Evidence: `apps/operator-panel/src/bridge.ts`, `apps/operator-panel/src/App.tsx`
- `PASS` Scenario 7: system workspace doctor/config/capabilities surfaces use frozen handshake/config payloads.
  Evidence: `apps/operator-panel/src/bridge.test.ts`
- `PASS` Scenario 8: operations workspace surfaces real or honest-empty enterprise payloads with contract markers.
  Evidence: `tests/test_enterprise_cli.py`

## Computer Use Pilot Boundary

- `PASS` Unsupported platform is fail-closed.
- `PASS` Missing adapter is fail-closed.
- `PASS` Scaffold-only adapter reports `autonomy_not_enabled`.
- `PASS` `unknown_visual`, `selector_ambiguous`, `unexpected_modal`, `focus_drift`, and `confidence_below_threshold` hard-stop.
- `PASS` Recorder defaults to redacted evidence.
  Evidence: `tests/test_computer_use.py`
