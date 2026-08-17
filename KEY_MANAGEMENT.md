# Key Management

Agent Control Plane evidence packs use the enterprise signing boundary. In
enterprise mode, unsigned evidence can be generated for diagnostics but cannot
support a readiness or release claim.

## Goal

Enterprise artifacts must be signed with asymmetric keys and verified against a trusted public key set.
`IMPERAOS_AUDIT_SIGNING_KEY` remains a dev/pilot compatibility path only and is not acceptable for enterprise artifacts.

## Provider Modes

- `local_file`: mandatory minimum GA path
- `managed_kms`: supported adapter path for enterprise-managed signing
- `pkcs11_hsm`: planned interface, not a GA blocker for the first self-hosted release
- `env_hmac`: compatibility-only, non-enterprise

## Key Material Model

Each key record must define:

- `key_id`
- `algorithm`
- `purpose`
- `created_at`
- `not_before`
- `not_after`
- `rotation_state`

Trusted public keys live in a separate verification store. Revocation is managed through the key manifest.

## Signing Scope

The following must be signed:

- team audit envelopes
- core governance audit envelopes
- control-plane evidence manifests
- pilot and GA readiness reports
- support bundle manifests
- backup manifests
- policy bundle manifests
- upgrade compatibility manifests

Raw event lines are not individually signed. Integrity is enforced through the hash chain plus signed envelope/manifest.

## Rotation Policy

Rotation uses four phases:

1. `prepare`
2. `dual-verify`
3. `activate`
4. `retire-old`

Rules:

- runtime signs with one active key at a time
- verifier accepts current and overlapping trusted keys
- old keys are retired only after verification overlap is complete
- revoked keys are removed from trust for new verification decisions

## Enterprise Requirements Before GA

- `local_file` asymmetric signing works end to end
- managed KMS adapter contract is implemented and documented
- revocation manifest is enforced during verify
- rotation dry-run is exercised before release candidate sign-off
- historical artifacts remain verifiable after rotation

## Operational Commands

```bash
uv run imperaos keys status --profile enterprise --json
uv run imperaos keys verify --profile enterprise --path artifacts/ga_readiness_report.json --json
uv run imperaos keys rotate-plan --profile enterprise --next-key-id enterprise-signing-next --json
```

## Required Drills

- sign/verify pass
- rotation dry-run
- revoked key reject
- restore-time verification of historical artifacts

## 2026-05-13 Managed KMS Adapter Drill

Managed KMS adapter evidence was published under:

```text
artifacts/readiness/2026-05-13/managed_kms_adapter_drill/
```

Result:

- `managed_kms_live_drill.json`: `status=pass`.
- Signed drill report verification: PASS.
- `signature_mode=managed_kms`.
- Sign/verify drill: PASS.
- Rotation dry-run: PASS.
- Revoked key reject: PASS.
- Restore-time historical artifact verification: PASS.
- Secret material persisted in evidence: `false`.

This exercises the supported `managed_kms` subprocess signer adapter contract.
It does not claim external cloud KMS attestation or hardware HSM/PKCS#11
breadth. Full PKCS#11/HSM breadth remains deferred.
