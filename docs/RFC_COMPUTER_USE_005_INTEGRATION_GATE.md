# RFC Computer Use 005: Integration Gate

## Scope

This RFC defines the Phase 2.5 integration gate for the vision-first computer-use
foundation. The gate answers one narrow question: whether the branch is safe to
review and merge as a disabled-by-default supervised beta capability.

It does not qualify public live desktop automation. Live macOS qualification remains a
separate evidence requirement.

## Merge Standard

The branch is merge-ready when all integration checks pass:

- console and module entrypoints work from the repo path and temp copied paths
- default runtime config keeps vision execution disabled
- raw screenshot persistence remains disabled with max count `0`
- macOS live input remains disabled unless explicitly configured
- Windows live execution reports `WINDOWS_COMPUTER_USE_NOT_QUALIFIED`
- operator capabilities validate against the frozen v2 contract
- security policy denies sensitive surfaces, terminal control, stale approval snapshots,
  and risky actions without approval
- `git diff --check` has no whitespace errors

The gate intentionally does not require live macOS qualification for foundation merge.

## Public Release Standard

Public live claims remain blocked until live macOS qualification evidence is present and
passing. Missing live evidence must appear as a live/public blocker, not a merge blocker.

Expected disabled beta release posture:

```json
{
  "foundation_merge": "disabled_beta_candidate",
  "public_live_claims": "blocked",
  "live_blockers": [
    "live_macos_qualification_missing"
  ]
}
```

## Entrypoint Path Matrix

The integration gate verifies these commands:

```bash
uv run imperaos --version
uv run python -m imperaos --version
uv run imperaos operator capabilities --json
uv run python -m imperaos operator capabilities --json
```

They must work from:

- the current worktree path
- a normal ASCII temp copy
- a temp path containing spaces
- a native Turkish Unicode temp path; the gate keeps the source literal as
  `Masa\u00fcst\u00fc Test Alan\u0131`

Editable packaging uses Hatchling exact editable mode plus `editables` so console
scripts do not depend on locale-decoded `.pth` path entries.

## Gate Command

```bash
uv run python scripts/evaluate_computer_use_integration_gate.py --profile balanced --output artifacts/computer_use_integration_gate.json --markdown artifacts/COMPUTER_USE_INTEGRATION_GATE.md
```

The JSON report includes:

- `status`
- `merge_ready`
- `release_status`
- `branch`
- `commit`
- `defaults`
- `platform_gates`
- `operator_contract`
- `security_invariants`
- `checks`
- `blockers`

`merge_ready=true` only when every merge check passes. Live macOS qualification
absence must keep `release_status.public_live_claims=blocked` while allowing
`merge_ready=true` for the disabled beta foundation.
