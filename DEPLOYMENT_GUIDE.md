# Deployment Guide

This guide targets the self-hosted Agent Control Plane boundary. Deployments
should expose the governed runtime through registry, policy simulation,
approval, evidence and claim-guard workflows before any production-readiness
claim is made.

## Reference Deployment

### Linux Runtime Host

- dedicated service account
- encrypted local volume
- separate roots for config, stores, artifacts, and backups
- no inbound network listener unless explicitly approved
- enterprise profile as the default operating profile

### macOS Operator Workstation

- operator panel or CLI only
- no direct mutation authority outside CLI permission checks
- access limited to approved operator roles

### Windows Operator Workstation

- operator panel, bundled runtime, CLI smoke, and signed release-candidate evidence are supported on Windows x64
- WebView2 runtime must be present for the Tauri shell
- Windows live computer-use automation is disabled unless a Windows qualification
  report explicitly enables that surface; current reason code is
  `WINDOWS_COMPUTER_USE_NOT_QUALIFIED`
- unsigned CI smoke installers are internal validation artifacts only; public or
  enterprise release artifacts require Authenticode signing, timestamp proof,
  clean VM installer smoke, installed runtime/capabilities/doctor evidence,
  runtime manifest and bundle hash evidence, and
  `windows-public-release-gate.json` pass evidence
- do not deploy public or enterprise Windows artifacts if the gate file is
  missing, blocked, failed, has blocking reasons, used unsigned smoke, has
  `clean_vm_claimed != true`, or has an installer hash mismatch

## Deployment Steps

1. Install dependencies and application package.
2. Provision enterprise signing keys or KMS adapter.
3. Provision trusted verification keys.
4. Provision identity assertion path or IdP integration.
5. Resolve config and verify enterprise baseline.
6. Run backup, metrics snapshot, and GA readiness preflight.
7. Enable runtime traffic only after baseline passes.

## Environment Separation

Use separate roots per environment for:

- memory store
- approval store
- checkpoint store
- audit export
- team artifacts
- backups

Do not reuse the same paths between staging and production.

## Preflight Commands

```bash
uv run imperaos config resolve --profile enterprise --json
uv run imperaos security baseline --profile enterprise --json
uv run imperaos metrics snapshot --profile enterprise --json
uv run imperaos ga readiness --profile enterprise --report artifacts/ga_readiness_report.json --json
```
# Product-Complete Deployment Gate

Before claiming a self-hosted enterprise deployment is product-complete, run:

```bash
uv run python scripts/run_product_complete_closure_gate.py --profile enterprise --json
```

The gate writes JSON, Markdown, PR body, and no-ship register artifacts under
`artifacts/product-complete-closure/`. Any `noShipBlockers` entry blocks the
ready claim.
