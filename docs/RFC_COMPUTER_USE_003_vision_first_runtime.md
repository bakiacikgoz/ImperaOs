# RFC COMPUTER_USE 003: Vision-First Runtime Foundation

Status: foundation implemented, live OS automation gated

## Summary

This RFC adds a feature-gated vision-first computer-use runtime foundation without replacing the existing Safari/Finder/TextEdit pilot. The new path is organized under `imperaos/computer_use/vision_runtime/` and follows:

```text
observe -> interpret -> compare -> decide -> classify_risk -> approve_if_needed -> execute -> verify -> checkpoint -> continue_or_recover
```

The implementation is intentionally conservative. Deterministic mocks are available for tests, raw screenshots are not persisted by default, and live Windows execution remains disabled until a signed qualification gate explicitly enables it.

## Runtime Components

- `models.py`: strict Pydantic contracts for observations, UI elements, actions, decisions, steps, and run artifacts.
- `ports.py`: protocol interfaces for screen capture, vision interpretation, planning, execution, verification, and audit sinks.
- `policy.py`: universal fail-closed policy for sensitive surfaces, terminal control, confidence thresholds, and approval decisions.
- `runtime.py`: bounded step loop with provider-unavailable fail-closed behavior, approval stops, verification, and recovery budget handling.
- `recorder.py` and `replay.py`: redacted event writing with hash-chain integrity and replay summaries.
- `providers/mock_vision.py`: deterministic capture, planner, and verifier used by unit tests.
- `drivers/windows.py` and `drivers/linux.py`: scaffolded readiness reports that keep live execution disabled.

## Security Invariants

- `privacy_mode=true` remains the default.
- Raw screenshot persistence defaults to zero.
- Password, payment, and other sensitive surfaces stop the run.
- Terminal control is denied by default.
- Risky actions require step approval unless a qualified execution mode explicitly allows them.
- Windows live computer-use stays blocked with `WINDOWS_COMPUTER_USE_NOT_QUALIFIED`.

## Operator Contract

The operator capability payload keeps `computerUsePilot` intact and adds:

```json
"computerUseVisionRuntime": {
  "enabled": false,
  "stage": "not_configured",
  "platform": "macos",
  "scope": "vision_first_desktop_web_file",
  "executionModes": ["dry_run", "step_approval"],
  "replayable": true,
  "failClosed": true,
  "reasonCode": "VISION_RUNTIME_NOT_CONFIGURED"
}
```

Windows reports `stage=not_qualified` and `reasonCode=WINDOWS_COMPUTER_USE_NOT_QUALIFIED`.

## Known Limits

- No bundled live vision provider is enabled.
- Real OS mouse/keyboard drivers are not used by unit tests.
- The CLI `--runtime vision-first` path fails closed unless `computer_use.vision_enabled=true` and a provider is wired.
- Deterministic mock benchmark results are qualification scaffolding, not proof of real-world desktop reliability.
