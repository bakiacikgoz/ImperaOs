# RFC 007: macOS Live Qualification Path

## Status

Implemented as a supervised, opt-in qualification path. It does not enable unrestricted desktop automation.

## Product Boundary

ImperaOS can evaluate whether a local macOS host is ready for a narrow vision-first computer-use qualification run. Live execution remains disabled unless all gates pass:

- `computer_use.vision_enabled=true`
- local strict-JSON provider configured, currently Ollama-compatible
- `computer_use.macos_live_enabled=true`
- non-disabled macOS capture and input backends
- current Screen Recording and Accessibility permissions
- fresh macOS qualification report matching commit and computer-use config hash
- raw screenshot persistence disabled by default
- terminal control denied by default
- sensitive surface policy set to `stop`

Windows and Linux live execution remain not qualified and disabled.

## Runtime Loop

The macOS path preserves the vision-first loop:

```text
observe -> interpret -> decide -> classify_risk -> approve_if_needed -> execute -> verify -> checkpoint
```

OS-specific behavior stays behind `imperaos.computer_use.vision_runtime.drivers`.

## Doctor Commands

```bash
uv run imperaos computer-use doctor --platform macos --json
uv run imperaos computer-use vision doctor --platform macos --json
```

The doctor is CI-safe and does not request, grant, or bypass macOS TCC permissions.

## Qualification Command

```bash
IMPERAOS_COMPUTER_USE_LIVE_OPT_IN=I_UNDERSTAND_THIS_CONTROLS_MY_MAC \
IMPERAOS_COMPUTER_USE_LIVE_MACOS=1 \
uv run imperaos computer-use qualification run \
  --platform macos \
  --suite live-fixture-smoke \
  --mode supervised \
  --output artifacts/computer_use/macos_qualification_report.json \
  --json
```

Without the exact opt-in and `IMPERAOS_COMPUTER_USE_LIVE_MACOS=1`, the command
writes a blocked report and does not mark macOS qualified. A passing local
fixture report can show `fixture_qualified` while the live flag remains off;
`qualified_limited` is the only live-enabled macOS stage.
