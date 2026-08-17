# RC Freeze Reconciliation Runbook

Use this runbook after the RC evidence orchestrator has produced a ready gate ledger.

```bash
uv run imperaos release rc reconcile --profile enterprise --gate-ledger artifacts/release-gates/mainline-rc/gate_evidence_ledger.json --freeze-manifest artifacts/mainline-rc-freeze/manifest.json --output artifacts/rc-release-decision/rc_freeze_reconciliation.json --json
```

Rules:

- Ready ledger plus missing gate-artifact freeze warnings reconciles to `ready`.
- Ledger missing, hash mismatch, raw/secret marker, or unreconciled freeze blockers reconcile to `blocked`.
- Reconciliation does not merge, tag, publish, deploy, call live providers, or enable computer-use.
