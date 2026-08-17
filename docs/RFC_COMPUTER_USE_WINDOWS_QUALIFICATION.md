# RFC: Windows Computer-Use Qualification

Status: draft, not enabled

Windows live computer-use automation remains disabled and fail-closed with `WINDOWS_COMPUTER_USE_NOT_QUALIFIED` until a signed Windows qualification report explicitly enables that surface.

## Scope

This RFC defines the evidence required before Windows live computer-use can be considered. It does not enable runtime behavior.

Supported today:

- Windows core CLI.
- Operator panel.
- Bundled runtime generation and verification.
- Installer smoke evidence.

Not supported today:

- Windows live desktop/browser automation.
- Windows live execute mode.
- Any shell passthrough surface for computer-use.

## Candidate Primitives

- Windows UI Automation or accessibility-layer observation.
- Browser automation adapter with explicit allowlisted surfaces.
- File dialog and filesystem adapter with allowed-root enforcement.
- Foreground window and focus drift observation.
- Replay evidence for every mutating step.

## Hard Stops

The runtime must stop before action when any of these conditions occur:

- Unknown visual or unclassified surface.
- Focus drift or active-window mismatch.
- Unexpected modal or prompt.
- UAC, security, admin, credentials, MFA, password manager, payment, banking, billing, or identity surfaces.
- Confidence below threshold.
- Approval required but not executed.
- Missing replay or observation evidence.

## Required Evidence Before Enablement

- Dry-run only test set.
- Step-approval test set.
- Replay verification evidence.
- Sensitive-surface deny tests.
- Clean Windows VM run.
- No shell passthrough.
- Signed qualification report attached to the release gate.
- Matching `computer-use-platform-qualification/v1` report for platform, commit, and config hash.
- `computer-use doctor --platform windows --json` must keep `liveEnabled=false` until that report validates.

## Product Claim Rule

The product must keep reporting:

```text
WINDOWS_COMPUTER_USE_NOT_QUALIFIED
```

until the signed qualification report exists and a separate release gate explicitly changes the Windows capability contract.

## Phase 3 Gate Command

```bash
uv run python scripts/evaluate_computer_use_platform_matrix.py --profile balanced --output artifacts/computer_use_platform_matrix.json --markdown artifacts/COMPUTER_USE_PLATFORM_MATRIX.md
uv run python -m imperaos computer-use doctor --profile balanced --platform windows --json
uv run python -m imperaos computer-use qualification verify --profile balanced --platform windows --report artifacts/windows/qualification.json --json
```
