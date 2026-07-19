# Current Release Decision - 2026-05-23

## Current state

2026-05-23 local readiness snapshot is green for the requested validation
commands on `main` at commit `4f68014`.

Evidence is stored under:

```text
artifacts/readiness/2026-05-23/
```

This snapshot does not deploy, migrate, delete files, publish artifacts, rotate
credentials, or approve a public release. `git status --short` returned empty
when captured at the start of the validation sequence.

## Hat A status

Hat A remains supported inside the source/CLI/enterprise self-hosted boundary.
The requested local quality and runtime-contract checks passed:

- Python lint: PASS.
- Python test suite: PASS.
- Operator Panel frontend QA: PASS.
- Operator Panel Tauri Rust tests: PASS.
- Operator capabilities contract: PASS command execution, with computer-use
  live claims still gated and fail-closed.

This snapshot refreshes local confidence only. It does not replace the existing
signed qualification, soak, GA readiness, or release-operator evidence chain.

## Hat B blockers

Hat B desktop public release remains blocked.

- macOS public desktop release still requires signing credentials,
  notarization, stapling, and clean-machine Gatekeeper evidence.
- Windows public desktop release still requires Authenticode signing,
  timestamping, signed RC evidence, clean VM smoke, and a passing promote gate.
- Internal unsigned desktop artifacts remain QA/evaluation artifacts only.

## UI functional QA status

Operator Panel frontend QA passed with `qa:frontend`.

- UI control audit: 125 controls, 0 critical, 0 high, 36 medium.
- Vitest: 25 test files passed, 87 tests passed.
- ESLint: PASS.
- Production build: PASS.
- Playwright E2E: 13 tests passed.
- Frontend QA summary: 0 blockers; E2E, accessibility, and responsive checks
  passed.

## Computer-use claim boundary

Computer-use doctor and operator capabilities commands both exited `0`, but the
live computer-use claim remains blocked by contract.

- Current platform: macOS.
- Vision runtime: disabled / not qualified.
- Live enabled: false.
- Public live claim allowed: false.
- Qualification status: missing.
- macOS blockers include `VISION_RUNTIME_DISABLED`,
  `VISION_PROVIDER_UNAVAILABLE`, `MACOS_CAPTURE_BACKEND_DISABLED`, and
  `MACOS_INPUT_BACKEND_DISABLED`.
- Windows and Linux live computer-use remain not qualified and disabled.

The macOS pilot surface may only be described as qualification-gated and
fail-closed. This snapshot does not support unrestricted live desktop
automation claims.

## Non-developer operator attestation status

Independent non-developer operator attestation is still not provided in this
snapshot. The template and validator path exist, but automated validation cannot
substitute for a separate human attestation file validated with
`--operator-attestation`.

## Green gates

All requested validation commands exited `0`:

- `git status --short`
- `uv run --extra dev ruff check .`
- `uv run --extra dev pytest -q`
- `corepack pnpm --dir apps/operator-panel qa:frontend`
- `cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml`
- `uv run python -m imperaos computer-use doctor --json`
- `uv run python -m imperaos operator capabilities --json`

## Red / blocked gates

No requested validation command failed.

Product/release blockers still remain:

- Hat B macOS public desktop release is blocked by signing/notarization and
  Gatekeeper evidence.
- Hat B Windows public desktop release is blocked by signed RC, clean VM smoke,
  and promote-gate evidence.
- Vision-first live computer-use remains blocked because qualification evidence
  is missing.
- Independent non-developer operator attestation is missing.

## Next single blocker to close

Collect and validate the independent non-developer operator attestation for the
current Hat A release boundary. Hat B should remain separate until desktop
signing/notarization credentials and signed installer evidence are available.

## No-ship boundaries

- Do not ship public macOS desktop installers without codesign, notarization,
  stapling, and clean-machine Gatekeeper evidence.
- Do not ship public Windows desktop installers without Authenticode signed RC,
  clean VM smoke, and promote-gate evidence.
- Do not present internal unsigned desktop artifacts as public installers,
  signed release candidates, or enterprise/public releases.
- Do not claim unrestricted live computer-use automation.
- Do not claim Windows or Linux live computer-use.
- Do not claim independent non-developer operator attestation until the human
  attestation file is provided and validated.
- Do not treat this snapshot as a deploy, migration, credential, signing,
  notarization, or secret-management operation.
