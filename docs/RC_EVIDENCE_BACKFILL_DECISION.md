# RC Evidence Backfill Decision

The RC evidence backfill is a deterministic bridge for the mainline RC freeze state. It does not create production evidence and does not claim remote CI, review approval, live provider behavior, or deploy readiness.

## Decision

`mainline-rc` gate evidence is backfilled only from local, hash-only orchestrator artifacts under `artifacts/release-gates/mainline-rc`. The Control Plane exposes this as `rcGateEvidence`, and the RC freeze verifier can treat missing `REQUIRED_GATE_MISSING:*` warnings as satisfied only when the release-gate ledger verifies as `ready`.

## Acceptance Rules

- All required gates must be present in the ledger.
- All required artifacts must exist and match their SHA-256 hashes.
- Raw prompt, raw response, raw screenshot, and secret scans must pass.
- The ledger must identify `control-plane-gate` and `design-partner-handoff-gate` as passing gates before those RC freeze warnings can be cleared.
- The gate remains non-destructive and shell-free.

## Non-Goals

- No automatic PR merge or stack collapse.
- No main branch push.
- No release publication.
- No migration apply.
- No installer or public desktop claim.

## Audit Trail

Use:

```bash
uv run imperaos release gates verify --ledger artifacts/release-gates/mainline-rc/gate_evidence_ledger.json --json
uv run imperaos release rc-freeze verify --manifest artifacts/mainline-rc-freeze/manifest.json --gate-ledger artifacts/release-gates/mainline-rc/gate_evidence_ledger.json --json
```

The first command verifies the evidence ledger. The second command applies that verified evidence to RC freeze decision logic.
