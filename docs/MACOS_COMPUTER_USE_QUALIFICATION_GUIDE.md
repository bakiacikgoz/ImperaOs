# macOS Computer-Use Qualification Guide

## Scope

This guide covers supervised local macOS qualification only. It is limited to safe local fixtures such as local text editing, local file visibility checks, local HTML forms, scroll verification, and approval-stop checks.

## Manual Prerequisites

The operator must grant permissions manually in macOS settings:

- Screen Recording
- Accessibility

ImperaOS must never edit TCC databases, run `sudo`, ask for an admin password, or use private APIs to bypass consent.

## Config

Defaults are fail-closed:

```toml
[computer_use]
vision_enabled = false
vision_provider = "none"
vision_model = ""
macos_live_enabled = false
macos_capture_backend = "disabled"
macos_input_backend = "disabled"
macos_require_fresh_qualification = true
macos_qualification_report = ""
raw_screenshot_persistence = false
raw_screenshot_max_count = 0
terminal_control = "deny"
sensitive_surface_policy = "stop"
```

## Qualification

Run the doctor first:

```bash
uv run imperaos computer-use doctor --platform macos --json
```

Verify the local provider with a synthetic fixture before any desktop capture or input:

```bash
uv run imperaos computer-use provider doctor \
  --provider ollama \
  --model <local-vision-model> \
  --synthetic-fixture \
  --json
```

The provider command does not pull models or capture the real desktop. The operator owns Ollama installation, model selection, and `ollama serve` lifecycle.
The selected model must be present in `ollama list`, accept image input, and return strict schema-valid JSON. If a model is absent, install it manually; the runtime does not run `ollama pull` by default.

Run live qualification only on a prepared, supervised local desktop:

```bash
IMPERAOS_COMPUTER_USE_LIVE_MACOS=1 \
IMPERAOS_COMPUTER_USE_SUPERVISED_FIXTURE_ONLY=1 \
IMPERAOS_COMPUTER_USE_REQUIRE_STEP_APPROVAL=1 \
IMPERAOS_COMPUTER_USE_ACK="I understand ImperaOS will control my macOS desktop only for local supervised fixtures." \
IMPERAOS_COMPUTER_USE_VISION_ENABLED=1 \
IMPERAOS_COMPUTER_USE_VISION_PROVIDER=ollama \
IMPERAOS_COMPUTER_USE_VISION_MODEL=<local-vision-model> \
IMPERAOS_COMPUTER_USE_MACOS_LIVE_ENABLED=1 \
IMPERAOS_COMPUTER_USE_MACOS_CAPTURE_BACKEND=screencapture \
IMPERAOS_COMPUTER_USE_MACOS_INPUT_BACKEND=quartz \
uv run imperaos computer-use qualification run \
  --platform macos \
  --suite live-fixture-smoke \
  --mode supervised \
  --provider ollama \
  --model <local-vision-model> \
  --output artifacts/computer_use/macos_qualification_report.json \
  --json
```

Run preflight first when preparing a host:

```bash
uv run imperaos computer-use qualification run \
  --platform macos \
  --suite live-fixture-smoke \
  --mode preflight \
  --output artifacts/computer_use/macos_qualification_report.json \
  --json
```

If the explicit opt-in, acknowledgment, supervised-fixture scope, step approval,
or any readiness gate is missing, the command writes a blocked report with local
fixture metadata only. It does not request permissions, grant permissions,
persist raw screenshots, or enable live runtime execution.

Verify report replay integrity separately:

```bash
uv run imperaos computer-use replay \
  --report artifacts/computer_use/macos_qualification_report.json \
  --verify \
  --json
```

A fresh passing report without `macos_live_enabled=true` may report
`fixture_qualified_default_disabled` with `fixtureQualified=true`,
`productionQualified=false`, and `liveEnabled=false` by default. macOS supervised local fixture
qualification is not unrestricted desktop automation, and it does not qualify
Windows or Linux live computer-use.

Replay verifies trace and audit integrity, not business correctness. Raw screenshots are not persisted by default.

## v2 Evidence

For the semantic-verifier v2 gate, use
`artifacts/computer_use/macos_qualification_v2_report.json` as the report path.
The accepted evidence must show positive semantic verification, approval
blocking before execution, stale approval fail-closed behavior when tested,
replay integrity, no unrestricted live enablement, and zero raw screenshot
persistence.
