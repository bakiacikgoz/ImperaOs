# macOS M4 Local Trial Runbook

This runbook prepares ImperaOS / ImperaOS for a personal Apple Silicon M4 local trial from source. It is not a public desktop release, signing, notarization, production deployment, or unrestricted live computer-use procedure.

## Boundaries

- No API keys, signing certificates, passwords, private keys, payment credentials, MFA secrets, or PII are required by this runbook.
- No destructive automation is run.
- Live computer-use is not enabled by the default flow.
- Missing assistant model/provider readiness is reported as `setup_required` or `conditional`, not as a fake assistant response.
- Public `.dmg` release readiness still requires separate signing and notarization evidence.

## Prerequisites

- macOS on Apple Silicon M4.
- Xcode Command Line Tools.
- Python 3.11. The project expects Python `>=3.11,<3.12`; `uv` is preferred.
- `uv`.
- Node 22 or 24.
- Corepack with pnpm 10.29.2 from the repo lockfile.
- Rust stable compatible with at least Rust 1.77.2.
- Optional: Ollama and a local model for a fully working local assistant response.

Check the local toolchain:

```bash
xcode-select -p
rustc --version
cargo --version
node --version
corepack --version
uv --version
```

## Install From Source

```bash
uv sync --python 3.11 --extra dev
corepack enable
corepack pnpm --dir apps/operator-panel install --frozen-lockfile
```

## First Diagnostics

```bash
uv run imperaos setup first-run --profile enterprise --mode local-enterprise --json
uv run imperaos assistant doctor --profile enterprise --json
uv run imperaos assistant models --profile enterprise --json
uv run python scripts/run_macos_local_trial_gate.py --profile enterprise --json
```

Expected result meanings:

- `pass`: source CLI, non-destructive gates, Operator Panel bridge parity, and local safety boundaries are ready for personal local trial.
- `conditional`: local trial can proceed, but an explicit condition remains, such as assistant model/provider setup or a GUI launched probe not being executed.
- `blocked`: do not treat the local trial as ready; inspect `blockers` in the JSON/Markdown evidence.
- `setup_required`: not a fake assistant success. It means the assistant runtime needs provider/model setup before real AI answers can be claimed.

Gate evidence is written to:

```text
artifacts/macos-local-trial/macos_local_trial_gate.json
artifacts/macos-local-trial/MACOS_LOCAL_TRIAL_GATE.md
artifacts/macos-local-trial/no_ship_boundaries.json
```

## Operator Panel Dev Run

```bash
corepack pnpm --dir apps/operator-panel tauri:dev
```

For a local launched smoke probe:

```bash
OPERATOR_PANEL_TAURI_LAUNCH=1 corepack pnpm --dir apps/operator-panel exec tsx scripts/tauri-launched-smoke.ts --launch
```

The launched smoke report is written to:

```text
artifacts/operator-panel-ui/tauri-smoke/report.json
artifacts/operator-panel-ui/tauri-smoke/TAURI_LAUNCHED_SMOKE.md
```

## Optional Local Assistant With Ollama

This is optional and is not required for the base local trial gate.

```bash
ollama serve
ollama list
uv run imperaos assistant doctor --profile enterprise --json
uv run imperaos assistant models --profile enterprise --json
```

If no model/provider is ready, the correct local-trial result is `conditional` or `setup_required`. Product mode must not silently fall back to preview fixture answers.

## Bundled Runtime Check

For arm64 runtime bundle validation:

```bash
make macos-bundled-runtime-gate
```

This builds and verifies:

```text
apps/operator-panel/src-tauri/resources/imperaos-runtime/RUNTIME_MANIFEST.txt
apps/operator-panel/src-tauri/resources/imperaos-runtime/python/bin/python
```

Generated runtime contents are build artifacts and should not be committed.

## Computer-Use Boundary

Default local trial must keep live desktop automation closed:

```bash
uv run python -m imperaos computer-use doctor --json
```

Expected local trial posture:

- `liveEnabled=false`
- `publicLiveClaimAllowed=false` or `public_live_claim_allowed=false`
- qualification is `missing`, `not_qualified`, `disabled`, or otherwise blocked
- raw screenshot persistence is disabled

Optional live macOS computer-use testing is separate from this runbook's default flow. It requires explicit opt-in, Screen Recording, Accessibility, provider readiness, and replay evidence. The required env names are documented here only; this runbook does not generate real tokens:

```bash
export IMPERAOS_COMPUTER_USE_LIVE_OPT_IN=<exact-required-token>
export IMPERAOS_COMPUTER_USE_LIVE_MACOS=1
```

Do not enable live computer-use during the first local trial unless you are intentionally running the separate qualification flow.

## Troubleshooting

- Python 3.12 selected: rerun with `uv sync --python 3.11 --extra dev`.
- Node drift: use Node 22 or 24 and rerun `corepack pnpm --dir apps/operator-panel install --frozen-lockfile`.
- Assistant has no model: treat `setup_required` as conditional, configure a provider/model, then rerun assistant diagnostics.
- Tauri GUI smoke cannot run in CI or headless shell: use contract smoke for CI and run `--launch` manually on macOS desktop.
- macOS blocks unsigned local app launch: local source/dev trial can use `tauri:dev`; public distribution still needs signing and notarization.
