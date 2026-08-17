# RFC Computer-Use 018: Operator Panel Control Plane

## Scope

This RFC defines the Operator Panel and CLI control plane for computer-use
runtime selection, start gating, recent outcome summary, and safe operator
remediation display.

It does not make a production qualification claim, does not unblock public
release, and does not handle signing/notarization/provider secrets.

## Runtime Selection

Operator Panel submit flows carry an explicit runtime choice:

```text
vision-first | legacy-pilot | auto
```

The UI default is `vision-first`. `legacy-pilot` is available only as an
explicit operator selection and must show a warning that the legacy pilot path is
local and supervised.

The CLI default for `computer-use run --runtime` remains unchanged for backward
compatibility.

## Start Gate

The default UI start gate is fail-closed:

```text
computerUseVisionRuntime.enabled == true
computerUseVisionRuntime.failClosed == true
```

If either condition is false, Start Session remains disabled and the UI shows
copy-safe reason codes from `computerUseVisionRuntime.reasonCode`,
`capabilityResolution.blockers`, and the selected platform blockers.

For `legacy-pilot`, start is allowed only when the legacy capability is enabled,
fail-closed, and macOS-scoped. There is no silent fallback from vision-first to
legacy.

## Summary Contract

The CLI exposes recent outcome summary through:

```bash
uv run python -m imperaos computer-use summary \
  --root-dir .imperaos/team/jobs \
  --limit 20 \
  --json
```

The JSON response includes `contractVersion`, `status`, `artifact_root`,
`window`, `counts`, `recent_runs`, `top_failure_codes`, last outcome timestamps,
readiness blockers, and a human summary. Missing or empty roots return
`status=ok` with zero observed runs.

The Operator Panel bridge declares `computerUseSummaryJson=true` and exposes the
same payload through `bridge_computer_use_summary`.

## Safety Invariants

- Fail closed by default.
- Raw screenshot persistence remains disabled by default.
- Terminal control remains `deny`.
- Sensitive surface handling remains `stop`.
- Risky actions still require fresh approval.
- Replay/audit integrity is evidence, not business correctness proof.

## Local Verification

```bash
uv run python -m imperaos computer-use doctor --json
uv run python -m imperaos computer-use summary --root-dir .imperaos/team/jobs --limit 20 --json
uv run python -m imperaos operator capabilities --json
corepack pnpm --dir apps/operator-panel test
cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml
```
