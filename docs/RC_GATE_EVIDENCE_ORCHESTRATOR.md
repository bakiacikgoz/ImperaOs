# RC Gate Evidence Orchestrator

The RC Gate Evidence Orchestrator is the local, non-destructive evidence layer for the mainline RC freeze train. It plans, runs, verifies, and exports hash-only gate evidence for `mainline-rc` without requiring GNU Make.

## Boundaries

- No live provider calls.
- No computer-use execution.
- No deploy, merge, tag, release, migration apply, or destructive shell commands.
- No raw prompts, responses, screenshots, secrets, or PII in release artifacts.
- Gate commands must be argv lists and run with `shell=False`.

## Commands

```bash
uv run imperaos release gates plan --target mainline-rc --profile enterprise --json
uv run imperaos release gates run --target mainline-rc --profile enterprise --mode rc-focused --output-root artifacts/release-gates/mainline-rc --json
uv run imperaos release gates verify --ledger artifacts/release-gates/mainline-rc/gate_evidence_ledger.json --json
uv run imperaos release gates export --ledger artifacts/release-gates/mainline-rc/gate_evidence_ledger.json --output-root artifacts/release-gates/mainline-rc --json
uv run imperaos control-plane release gates snapshot --profile enterprise --evidence-root artifacts/release-gates/mainline-rc --json
```

The official cross-platform gate is:

```bash
uv run python scripts/run_rc_evidence_orchestrator_gate.py --profile enterprise --json
```

`make rc-evidence-orchestrator-gate` is a convenience wrapper only. Windows operators can use the Python script directly.

## Evidence Contract

The run command writes `artifacts/release-gates/mainline-rc/gate_evidence_ledger.json` and `GATE_EVIDENCE_LEDGER.md`. The ledger stores artifact paths, SHA-256 hashes, gate status, and missing-artifact metadata. It does not persist command stdout, raw model payloads, screenshots, or secrets.

Verification fails closed when:

- a required gate is missing;
- a required artifact is missing;
- an artifact hash does not match the ledger;
- raw prompt, raw response, raw screenshot, or secret markers are detected;
- an unsafe command is present in the gate plan.

## Operator Panel

The Control Plane snapshot exposes `rcGateEvidence`. The Operator Panel route `RC Gate Evidence` shows:

- latest ledger and verification status;
- gate, missing-gate, and missing-artifact counts;
- raw/secret scan status;
- platform and Make requirement;
- whether the evidence can satisfy the RC freeze gate-artifact warnings.

This route is informational. It does not trigger live runs or mutate release state.
