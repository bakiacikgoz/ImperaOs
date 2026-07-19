# RFC Computer-Use 010: macOS One-Run Live Fixture Qualification

## Scope

Phase 4D prepares a local macOS host for one supervised fixture-only qualification attempt. It does not enable production computer-use, background automation, or unrestricted desktop control.

## Defaults

These defaults remain fail-closed in every profile:

- `vision_enabled=false`
- `vision_provider="none"`
- `macos_live_enabled=false`
- `macos_capture_backend="disabled"`
- `macos_input_backend="disabled"`
- `raw_screenshot_persistence=false`
- `raw_screenshot_max_count=0`
- `terminal_control="deny"`
- `sensitive_surface_policy="stop"`

Windows and Linux live computer-use remain disabled and unqualified.

## Provider Readiness

Provider readiness uses only a generated local synthetic fixture image:

```bash
uv run imperaos computer-use provider doctor \
  --provider ollama \
  --model <local-vision-model> \
  --synthetic-fixture \
  --json
```

The command validates strict JSON before marking the provider ready. It does not capture the desktop, does not auto-install Ollama, and does not pull models. Provider failures map to deterministic reason codes such as `VISION_PROVIDER_UNAVAILABLE`, `VISION_PROVIDER_TIMEOUT`, `VISION_PROVIDER_INVALID_RESPONSE`, `VISION_PROVIDER_MODEL_NOT_CONFIGURED`, and `VISION_PROVIDER_STRICT_JSON_CONTRACT_FAILED`.

## Permission Readiness

macOS permissions are detected conservatively and must be granted manually in System Settings:

- Privacy & Security -> Screen Recording
- Privacy & Security -> Accessibility

The doctor reports `manualGrantRequired` and `autoGrantAttempted=false`; it never writes TCC databases or grants permissions.

## One-Run Opt-In

Live fixture execution requires all one-run environment values:

```bash
IMPERAOS_COMPUTER_USE_LIVE_MACOS=1
IMPERAOS_COMPUTER_USE_SUPERVISED_FIXTURE_ONLY=1
IMPERAOS_COMPUTER_USE_REQUIRE_STEP_APPROVAL=1
IMPERAOS_COMPUTER_USE_ACK="I understand ImperaOS will control my macOS desktop only for local supervised fixtures."
```

The opt-in is not persisted to config. `IMPERAOS_COMPUTER_USE_LIVE_MACOS=1` alone is not sufficient.

## Fixtures

The Phase 4D suite is limited to local safe fixtures:

- local browser form
- TextEdit safe typing
- Finder fixture file
- sensitive surface stop
- terminal deny

Positive fixtures must pass. Negative fixtures must block before input. `fixtureQualified=true` never implies `productionQualified=true`, and `liveEnabled=false` remains the default after a passing fixture report.

## Replay

Replay verifies trace integrity and audit hash-chain integrity. It does not prove business correctness. Blocked preflight reports may still replay-verify successfully.
