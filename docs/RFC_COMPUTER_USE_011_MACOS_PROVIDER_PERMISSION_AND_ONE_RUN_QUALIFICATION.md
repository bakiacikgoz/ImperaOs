# RFC Computer-Use 011: macOS Provider, Permission, and One-Run Qualification

## Scope

Phase 4E keeps macOS computer-use limited to a single supervised local fixture qualification attempt. Production automation remains disabled by default, and Windows/Linux live computer-use remain unqualified.

## Provider Readiness

The operator must explicitly select a local Ollama-compatible vision model:

```bash
IMPERAOS_COMPUTER_USE_VISION_PROVIDER=ollama
IMPERAOS_COMPUTER_USE_VISION_MODEL=<local-vision-model>
```

Readiness is checked with a generated synthetic local fixture image:

```bash
uv run imperaos computer-use provider doctor \
  --provider ollama \
  --model "$IMPERAOS_COMPUTER_USE_VISION_MODEL" \
  --synthetic-fixture \
  --json
```

The doctor checks that the model is configured, present in `ollama list`, accepts image input, and returns strict schema-valid JSON. It does not auto-select text-only models and does not run `ollama pull`. Model pulls require separate operator action; `IMPERAOS_ALLOW_OLLAMA_MODEL_PULL=1` is documented only as an explicit future opt-in and remains fail-closed here.

## Permission Readiness

macOS Screen Recording and Accessibility are manual prerequisites. The runtime reports the likely launching process and manual remediation, but it never grants permissions, mutates TCC databases, opens System Settings, or uses private bypasses.

## One-Run Live Gates

The supervised run remains blocked until all of these are present for the one command:

```bash
IMPERAOS_COMPUTER_USE_LIVE_MACOS=1
IMPERAOS_COMPUTER_USE_SUPERVISED_FIXTURE_ONLY=1
IMPERAOS_COMPUTER_USE_REQUIRE_STEP_APPROVAL=1
IMPERAOS_COMPUTER_USE_ACK="I understand ImperaOS will control my macOS desktop only for local supervised fixtures."
```

Runtime config still defaults to `vision_enabled=false`, `vision_provider="none"`, `macos_live_enabled=false`, `macos_capture_backend="disabled"`, `macos_input_backend="disabled"`, and `raw_screenshot_persistence=false`.

## Fixture Qualification

`fixtureQualified=true` requires all positive local fixtures to pass, sensitive-surface and terminal fixtures to deny before execution, step approval to remain enforced, replay/audit verification to pass, and `raw_screenshot_persisted_count=0`.

`fixtureQualified=true` does not mean production-qualified. `productionQualified=false` and default `liveEnabled=false` remain mandatory after a passing fixture report.
