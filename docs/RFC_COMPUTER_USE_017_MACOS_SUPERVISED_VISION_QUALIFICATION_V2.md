# RFC Computer-Use 017: macOS Supervised Vision Qualification v2

Phase 8 reruns the supervised macOS fixture qualification with the strict
candidate-action planner, semantic verifier, approval snapshot binding,
multi-step loop guards, deterministic fixture coverage, operator visibility,
and `vision_runtime_summary.json` safety counters.

This gate does not enable unrestricted desktop automation. It only qualifies a
local supervised fixture envelope on the current macOS host.

## Prerequisites

- Host is macOS.
- Screen Recording is manually granted.
- Accessibility is manually granted.
- Local Ollama vision model is installed and running.
- Raw screenshot persistence remains disabled.
- Step approval remains required.
- The operator explicitly sets the live macOS opt-in and acknowledgment flags.

## Preflight

```bash
uv run imperaos computer-use doctor --profile balanced --platform all --json

uv run imperaos computer-use provider doctor \
  --provider ollama \
  --model <local-vision-model> \
  --synthetic-fixture \
  --json
```

Expected preflight evidence:

- macOS readiness reports Screen Recording, Accessibility, provider, and backend status.
- Windows and Linux remain not qualified.
- Provider output is strict schema-valid JSON.
- `raw_screenshot_persisted` and `raw_screenshot_persisted_count` remain `0`.

## Supervised Fixture Run

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
  --output artifacts/computer_use/macos_qualification_v2_report.json \
  --json
```

## Replay Verification

```bash
uv run imperaos computer-use replay \
  --report artifacts/computer_use/macos_qualification_v2_report.json \
  --verify \
  --json

uv run imperaos computer-use qualification verify \
  --platform macos \
  --report artifacts/computer_use/macos_qualification_v2_report.json \
  --json
```

## Required Evidence

- Report status is `pass` or an explicit controlled-pass fixture status.
- Semantic verifier has `satisfied > 0` for positive fixtures.
- Approval-required actions block before execution.
- Approval resume tests, when present, bind to fresh action/context snapshots.
- Stale approval negative tests fail closed.
- No-progress and repeated-action guards stop loops.
- Replay integrity is verified.
- `raw_screenshot_persisted == 0`.
- Report platform, provider, backend, commit, and config hash match the current host.

## Failure Handling

- Provider invalid response: fix provider prompt/schema compatibility before a live rerun.
- Missing permission: update runbook or host setup; do not bypass macOS consent.
- Semantic verifier inconclusive: fix fixture expected state or observation extraction.
- Stale approval: diagnose context drift; do not widen snapshot tolerance first.
- Raw screenshot persistence above zero: treat as a release-blocking privacy regression.

Large host-specific qualification artifacts should stay out of the repository
unless the release process explicitly asks for signed evidence to be checked in.
