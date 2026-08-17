# Enterprise Workspace Onboarding

Enterprise workspace onboarding creates the local organization, workspace, first principal, membership, and device records used by the control plane. The flow is self-hosted first: it does not open a network listener and it does not require a cloud identity provider to start.

## Operator Flow

1. Verify identity is enabled for the enterprise profile.
2. Run the bootstrap command:

```powershell
uv run imperaos enterprise workspace bootstrap --profile enterprise --workspace-id pilot-workspace --organization-id local-org --display-name "Pilot Workspace" --json
```

3. Inspect the snapshot:

```powershell
uv run imperaos enterprise workspace snapshot --profile enterprise --json
```

4. Confirm the snapshot reports `rawSecretsExposed=false` and `networkListenerEnabled=false`.
5. Enroll external agents through the token/request/approval lifecycle in `docs/AGENT_ENROLLMENT_RUNBOOK.md`.

## Expected State

The ready state includes one active organization, one active workspace, one verified actor, at least one active membership, and any approved agents bound to a workspace, principal, and device. Missing identity, missing membership, or inactive device state must block access rather than silently falling back.

## Validation

Run the focused gate before promoting this slice:

```powershell
uv run python scripts/run_enterprise_workspace_onboarding_gate.py --profile enterprise --json
```

The Make target wraps schema generation, focused Python tests, Operator Panel tests, the Playwright route smoke, and `git diff --check`:

```powershell
make enterprise-workspace-onboarding-gate
```
