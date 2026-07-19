# RFC 009: macOS Live Readiness and Safe Rerun

## Status

Implemented as a readiness hardening layer and safe preflight rerun path. This
does not enable unrestricted desktop automation.

## Scope

The macOS qualification path is limited to supervised local fixtures. Windows
and Linux live computer-use remain unqualified and disabled.

## Readiness States

The macOS doctor and qualification report distinguish:

- missing one-run live opt-in
- missing human-readable acknowledgment
- missing supervised-fixture-only scope
- missing step approval requirement
- provider unavailable, timed out, or invalid strict JSON
- Screen Recording and Accessibility permission readiness
- capture and input backend readiness
- fixture qualification status
- replay and audit integrity status

Blocked preflight reports can be audit-valid while not qualification-valid:

```text
qualificationPassed=false
replayIntegrityVerified=true
auditHashChainVerified=true
```

## Required One-Run Opt-In

```text
IMPERAOS_COMPUTER_USE_LIVE_MACOS=1
IMPERAOS_COMPUTER_USE_SUPERVISED_FIXTURE_ONLY=1
IMPERAOS_COMPUTER_USE_REQUIRE_STEP_APPROVAL=1
IMPERAOS_COMPUTER_USE_ACK=I understand ImperaOS will control my macOS desktop only for local supervised fixtures.
```

These values are scoped to one command environment. They are not persisted into
default config.

## Safe Preflight

```bash
uv run imperaos computer-use doctor --platform macos --json
uv run imperaos computer-use qualification run \
  --platform macos \
  --suite live-fixture-smoke \
  --mode preflight \
  --output artifacts/computer_use/macos_qualification_report.json \
  --json
uv run imperaos computer-use replay \
  --report artifacts/computer_use/macos_qualification_report.json \
  --verify \
  --json
```

Preflight must not perform input automation. If prerequisites are missing, it
writes a blocked report with actionable blockers and redacted audit events.

## Safety Invariants

- live automation remains disabled by default
- model assets are operator-managed and are not auto-installed
- raw screenshots are not persisted by default
- terminal control remains denied
- sensitive surfaces stop before input
- Screen Recording and Accessibility are never auto-granted
- `fixtureQualified=true` never means `productionQualified=true`
