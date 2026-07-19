# RFC Computer Use 006: Cross-Platform Qualification Gates

Status: draft, disabled by default

## Scope

Phase 3 adds one shared contract for macOS, Windows, and Linux computer-use readiness.
It does not enable public live desktop automation on any platform.

The runtime must expose platform state as:

- `liveEnabled=false` unless platform qualification evidence is present and valid
- `failClosed=true`
- `executionModes=["dry_run", "step_approval"]` by default
- a platform-specific reason code when live execution is blocked

## Platform Status Model

`imperaos.computer_use.vision_runtime.platforms` is the source of truth for:

- platform capability serialization
- platform-specific blockers
- public matrix evaluation
- operator contract `computerUseVisionRuntime.platforms`

Expected default reason codes:

- macOS: `MACOS_COMPUTER_USE_NOT_QUALIFIED`
- Windows: `WINDOWS_COMPUTER_USE_NOT_QUALIFIED`
- Linux: `LINUX_COMPUTER_USE_NOT_QUALIFIED`

## Qualification Evidence

Live execution requires a `computer-use-platform-qualification/v1` report that matches:

- platform
- commit
- platform-specific config hash
- provider and backend configuration
- permission and safety invariants
- task suite pass count

Missing, stale, mismatched, or failed reports keep the platform blocked.

## Public Matrix Gate

The matrix gate is intentionally stricter than the operator preview. It fails when a
profile appears configured for live execution but lacks valid platform evidence.

```bash
uv run python scripts/evaluate_computer_use_platform_matrix.py --profile balanced --output artifacts/computer_use_platform_matrix.json --markdown artifacts/COMPUTER_USE_PLATFORM_MATRIX.md
```

The expected disabled default posture is `status=pass`, because every platform remains
fail-closed and no live claim is made.

## CLI Surfaces

```bash
uv run python -m imperaos operator capabilities --json
uv run python -m imperaos computer-use doctor --profile balanced --platform all --json
uv run python -m imperaos computer-use qualification verify --profile balanced --platform windows --report artifacts/windows/qualification.json --json
```

## Non-Goals

- No raw screenshot persistence by default.
- No terminal control by default.
- No Windows UAC secure desktop automation.
- No Linux Wayland or X11 live input claim.
- No public live support claim without separate signed evidence.
