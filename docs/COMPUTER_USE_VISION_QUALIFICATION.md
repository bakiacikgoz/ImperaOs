# Computer-Use Vision Qualification

## Evidence Levels

`deterministic`
: CI-friendly mock qualification using `benchmarks/tasks/computer_use_vision/smoke_tasks.jsonl`.

`live`
: Opt-in macOS local qualification. It requires `IMPERAOS_COMPUTER_USE_LIVE_MACOS=1`, `IMPERAOS_COMPUTER_USE_SUPERVISED_FIXTURE_ONLY=1`, `IMPERAOS_COMPUTER_USE_REQUIRE_STEP_APPROVAL=1`, `IMPERAOS_COMPUTER_USE_ACK`, Screen Recording, Accessibility, `macos_live_enabled=true`, and a configured local vision provider.

## Report Contract

Qualification writes a machine-readable report:

```json
{
  "artifact_version": "computer_use_vision_qualification/v1",
  "mode": "deterministic",
  "status": "pass",
  "summary": {
    "raw_screenshot_persisted_count": 0
  }
}
```

The default output path is `artifacts/computer_use_vision_qualification/qualification.json`.

Each vision-first runtime job also writes `vision_runtime_summary.json` beside
the redacted audit envelope. That summary contains safety counters such as
candidate actions seen/rejected, approval blocks, semantic verifier counts,
no-progress stops, stop reason, and `raw_screenshot_persisted`. The privacy
gate remains `raw_screenshot_persisted == 0` for default qualification runs.

Platform live evidence uses the additive `computer-use-platform-qualification/v1` schema
at `contracts/computer_use/platform_qualification.schema.json`. That report is validated
against platform, commit, config hash, backend, permission, task-suite, and safety
invariants before a platform can report `liveEnabled=true`.

## Gate Rules

- Deterministic pass permits continued development and operator preview.
- Live macOS public claims require separate local evidence.
- Windows live computer-use remains blocked until signed qualification evidence exists.
- Linux live computer-use remains blocked until platform-specific signed qualification evidence exists.
- Raw screenshot persistence must remain `0` unless an explicit local debug policy is enabled.
- Replay verification checks event integrity and policy invariants only; it does not prove task correctness.

## Deterministic Provider Fixtures

Schema-validated local provider-response fixtures live in
`contracts/computer_use/fixtures/vision_*.json`. They cover safe click, type
text, scroll, modal open, denied hotkey, sensitive surface, and empty candidate
paths without storing raw screenshots.

## Commands

```bash
uv run imperaos computer-use qualify --runtime vision-first --suite smoke --mode deterministic --json
uv run imperaos computer-use vision doctor --profile balanced --json
uv run python -m imperaos computer-use doctor --profile balanced --platform all --json
uv run python scripts/evaluate_computer_use_platform_matrix.py --profile balanced --output artifacts/computer_use_platform_matrix.json --markdown artifacts/COMPUTER_USE_PLATFORM_MATRIX.md
```

Live macOS qualification is intentionally skipped unless explicitly opted in:

```bash
IMPERAOS_COMPUTER_USE_LIVE_MACOS=1 \
IMPERAOS_COMPUTER_USE_SUPERVISED_FIXTURE_ONLY=1 \
IMPERAOS_COMPUTER_USE_REQUIRE_STEP_APPROVAL=1 \
IMPERAOS_COMPUTER_USE_ACK="I understand ImperaOS will control my macOS desktop only for local supervised fixtures." \
uv run imperaos computer-use qualification run \
  --platform macos \
  --suite live-fixture-smoke \
  --mode supervised \
  --output artifacts/computer_use/macos_qualification_report.json \
  --json
```

Without the exact opt-in and readiness gates, the macOS report is `blocked`,
not a qualification pass. Replay verification checks audit integrity separately,
so a blocked no-op report can return `replayIntegrityVerified=true` while
`qualificationPassed=false`.
