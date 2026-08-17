# Security Baseline

Agent Control Plane deployments must preserve fail-closed policy evaluation,
verified identity for enterprise mutations, signed evidence packs, and
claim-guard blocks for unsupported desktop or computer-use claims.

## Scope

This baseline defines the minimum acceptable security posture for `enterprise` profile deployments of ImperaOS / ImperaOS.
It applies to self-hosted, single-tenant installations where the runtime and its stores are under enterprise operator control.

## Secure Defaults

- `enterprise` profile is `default-deny` and `fail-closed`.
- Governance must remain enabled with `policy_fail_mode=fail_closed`.
- `web_enabled=false` by default.
- `debug_mode=false` by default.
- `privacy_mode=true` by default.
- PII redaction must stay enabled for governance and artifact output.
- Mutating Team Runtime and governance actions require a verified identity assertion.
- Audit and operational artifacts must use asymmetric signing in enterprise mode.
- Control Plane evidence manifests must be signed and verifiable in enterprise mode.
- Metrics export defaults to file/textfile output only. Network listeners are opt-in.
- Memory, approval, checkpoint, audit, team artifact, and backup roots must be separated.

## Deployment Boundaries

- `restricted` profile is for controlled pilot.
- `enterprise` profile is the secure default for GA-class self-hosted deployment.
- Local single-user developer mode is not an enterprise boundary and must not be treated as one.
- Operator panel is a secondary surface. Mutation authority remains in the CLI permission gate.

## Artifact Integrity Expectations

The following artifacts must be signed in enterprise mode:

- `audit_envelope.json`
- policy bundle manifests
- `team_pilot_report.json`
- `ga_readiness_report.json`
- `support_bundle_manifest.json`
- backup and upgrade manifests

Hash chains protect event continuity; envelope and manifest signatures protect exported evidence.

## Logging And Privacy Posture

- Raw prompt or provider content is not retained by default.
- Privacy-off debugging requires explicit operator override outside enterprise default mode.
- Support bundles must be redacted by default.
- Logs and metrics should avoid direct secrets, API tokens, or provider credentials.

## Restricted Versus Admin Mode

- `operator` can run approved runtime actions and inspect status.
- `security_admin` owns approval execution authority, audit export, and key controls.
- `platform_admin` owns enable/disable, maintenance mode, backup, restore, and deployment actions.
- `policy_admin` edits and publishes policy bundles but does not gain audit export or approval execution by default.

## Misconfiguration Risks

These are blocking findings for enterprise deployment:

- identity disabled under `enterprise` profile
- HMAC compatibility signing used for enterprise artifacts
- prod and staging sharing the same store or artifact root
- provider credentials stored as plaintext in the runtime account home without enterprise controls
- debug/privacy override enabled by default in enterprise mode
- network exporters enabled without explicit deployment approval

## Startup Abort Conditions

Enterprise startup must abort if any of the following are true:

- verified identity gating is unavailable
- asymmetric signing provider is not configured
- trusted verification keys are absent
- storage separation checks fail
- immutable audit export expectation is disabled
- privacy or redaction defaults are weakened

## Validation Command

```bash
uv run imperaos security baseline --profile enterprise --json
```

Expected outcome:

- JSON output with `overall_status=pass`
- signed artifact at `artifacts/security_posture.json`
