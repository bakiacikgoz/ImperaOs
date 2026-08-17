# Agent Enrollment Runbook

Agent enrollment binds an external agent to an enterprise workspace before it can use the external gateway. The lifecycle is hash-only by design: raw enrollment tokens are shown once at creation time and are not persisted in state, evidence, fixtures, or snapshots.

## Lifecycle

1. Create a token with the minimum allowed capabilities:

```powershell
uv run imperaos enterprise enrollment token create --profile enterprise --workspace-id pilot-workspace --organization-id local-org --created-by-principal-id principal-admin --allowed-capability read --json
```

2. Pass the raw token to the target host out-of-band. Do not store it in repo files, logs, or evidence.
3. Create an enrollment request from the target host:

```powershell
uv run imperaos enterprise enrollment request create --profile enterprise --token "<shown-once-token>" --agent-id external-agent-01 --device-id device-host-01 --principal-id principal-agent --json
```

4. Review and approve the request:

```powershell
uv run imperaos enterprise enrollment approve --profile enterprise --request-id enrreq-example --approved-by-principal-id principal-admin --json
```

5. Confirm the external gateway accepts read-only requests only after active enrollment.

## Revocation

Revoke a token before use if it is exposed or no longer needed. Revoke or suspend the enrolled agent, device, or principal when the host leaves the workspace. Gateway checks fail closed for revoked enrollment, suspended device, revoked principal, missing workspace binding, and expired token state.

## Evidence Rules

Evidence may include token hashes, request ids, enrollment ids, device ids, principal ids, and workspace ids. Evidence must not include raw token values, bearer strings, authorization headers, or host-local secrets.
