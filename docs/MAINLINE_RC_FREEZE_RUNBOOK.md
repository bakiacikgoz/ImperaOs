# Mainline RC Freeze Runbook

This runbook keeps the stacked Design Partner RC chain local, deterministic, and non-destructive before human-reviewed mainline merge.

## Boundaries

- Do not merge PRs automatically.
- Do not push to `main`.
- Do not publish releases or tags.
- Do not enable live computer-use or public desktop installer claims.
- Do not persist raw prompts, responses, screenshots, secrets, or PII.

## Local Gate

```bash
make mainline-rc-freeze-gate
```

Review `artifacts/mainline-rc-freeze/manifest.json` and `artifacts/mainline-rc-freeze/RC_FREEZE_DECISION.md`.

## RC Evidence Gate

Run the cross-platform evidence gate before clearing gate-artifact warnings:

```bash
uv run python scripts/run_rc_evidence_orchestrator_gate.py --profile enterprise --json
```

When `make` is available, this wrapper is equivalent:

```bash
make rc-evidence-orchestrator-gate
```

The evidence ledger lives at `artifacts/release-gates/mainline-rc/gate_evidence_ledger.json`. To apply it to the RC freeze verifier:

```bash
uv run imperaos release rc-freeze verify --manifest artifacts/mainline-rc-freeze/manifest.json --gate-ledger artifacts/release-gates/mainline-rc/gate_evidence_ledger.json --json
```

Only a verified `ready` ledger can clear `REQUIRED_GATE_MISSING:*` warnings. Missing artifacts, tampered hashes, raw payload markers, or secret markers keep the freeze decision blocked or conditional.

## Decision Rules

- `blocked`: stop and fix blockers before any merge discussion.
- `conditional`: review warnings and remote CI manually.
- `ready`: eligible for human-reviewed stacked PR merge sequencing, not automatic merge.

Remote CI, review approvals, and actual merge order remain separate human-controlled checks.
