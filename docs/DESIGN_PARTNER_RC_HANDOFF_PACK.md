# Design Partner RC Handoff Pack

The handoff pack is the operator-facing RC bundle for a controlled design
partner handoff. It does not publish a desktop release, enable live
computer-use, call live provider APIs, or execute destructive actions.

Build and verify:

```bash
uv run imperaos pilot ops drill \
  --profile enterprise \
  --output-root artifacts/design-partner-handoff \
  --json

uv run imperaos release handoff build \
  --profile enterprise \
  --environment-label design-partner-rc-local \
  --output-root artifacts/design-partner-handoff \
  --json

uv run imperaos release handoff verify \
  --manifest artifacts/design-partner-handoff/manifest.json \
  --json
```

Generated files:

- `manifest.json`
- `DESIGN_PARTNER_HANDOFF_README.md`
- `FIRST_RUN_OPERATOR_CHECKLIST.md`
- `CLAIM_BOUNDARY_CARD.md`
- `SUPPORT_ESCALATION_GUIDE.md`
- `PILOT_OPS_DRILL_REPORT.json`
- `RELEASE_TRAIN_REPORT.json`

The pack is `ready` only when release train, strict RC, first-run drill, support
bundle, security posture, target evidence, and independent attestation are all
valid. Missing target evidence or missing attestation keeps the pack
conditional. Claim overreach, hash mismatch, raw marker, secret marker, or false
ready claim blocks the pack.
