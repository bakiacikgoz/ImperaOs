# Design Partner RC Evidence Closure

This runbook closes Design Partner RC warnings with real local evidence. It does
not enable the public desktop installer or live computer-use claims.

## Required Gates

Run these from the repository root:

```bash
make enterprise-hat-a-evidence-gate
uv run python scripts/evaluate_evidence_index.py --profile enterprise --evidence-root artifacts/control-plane/evidence --select-latest-valid --staged-evidence-root artifacts/design-partner-rc/evidence-sample --root-dir artifacts/design-partner-rc/evidence-index/state --output artifacts/design-partner-rc/evidence_index.json
uv run python scripts/evaluate_reports_alerts.py --profile enterprise --root-dir .imperaos/control-plane --evidence-root artifacts --output-dir artifacts/design-partner-rc/reports-alerts-logs
uv run python scripts/generate_design_partner_rc_pack.py --profile enterprise --state-root .imperaos/control-plane --evidence-root artifacts --output artifacts/design-partner-rc --fail-on-conditional --json
```

`make design-partner-rc-gate` runs this sequence as part of the normal RC gate.

## Ready Criteria

- `artifacts/design-partner-rc/manifest.json` has `status=pass`.
- `designPartnerRcStatus=ready`.
- `warnings=[]` and `blockers=[]`.
- `evidencePackCount` is greater than zero.
- `readyReportCount` is greater than zero.
- Required artifacts are present and non-empty.

## Expected Blocked Boundaries

These claims must remain blocked during Design Partner RC:

- `public-desktop-installer`
- `live-macos-computer-use`
- `live-windows-computer-use`
- `live-linux-computer-use`

Expected blocked boundary alerts are resolved for RC readiness accounting. Real
critical or error alerts, such as silent fallback, evidence tamper, invalid
signature, or an opened public desktop/live computer-use claim, still keep RC out
of ready.

## No-Ship Conditions

- Any RC manifest blocker.
- Any RC manifest warning under `--fail-on-conditional`.
- Public desktop installer boundary is not blocked.
- Computer-use live boundary is not blocked.
- Evidence index is missing or blocked.
- Enterprise Hat A claim is not allowed.
- `git diff --check` fails.
