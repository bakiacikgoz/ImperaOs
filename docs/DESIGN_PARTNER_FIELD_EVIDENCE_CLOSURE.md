# Design Partner Field Evidence Closure

Field evidence closure is the release-candidate proof that a design-partner
target environment was validated without storing raw prompts, raw responses,
screenshots, secrets, or PII. It is stricter than rehearsal evidence: strict RC
promotion requires target-environment mode plus independent operator
attestation.

## Commands

```bash
uv run imperaos pilot field prepare \
  --profile enterprise \
  --mode target-environment \
  --ack-target-environment \
  --target-environment-label design-partner-field-target-redacted \
  --output-root artifacts/design-partner-field-evidence

uv run imperaos pilot field collect \
  --session artifacts/design-partner-field-evidence/session.json \
  --evidence-root artifacts \
  --output-root artifacts/design-partner-field-evidence

uv run imperaos pilot field verify \
  --bundle artifacts/design-partner-field-evidence/target_evidence_bundle.json \
  --output artifacts/design-partner-field-evidence/verification.json

uv run imperaos pilot field attest-verify \
  --session artifacts/design-partner-field-evidence/session.json \
  --bundle artifacts/design-partner-field-evidence/target_evidence_bundle.json \
  --operator-attestation artifacts/design-partner-field-evidence/operator_attestation.json \
  --output artifacts/design-partner-field-evidence/attestation_validation.json

uv run imperaos pilot field promote-rc \
  --profile enterprise \
  --field-root artifacts/design-partner-field-evidence \
  --rc-root artifacts/design-partner-rc
```

The same commands are available under `control-plane pilot field`.

## Evidence Rules

- Evidence is hash-only and redacted.
- Rehearsal mode may be useful for dry runs, but it cannot produce strict RC
  ready.
- `public-desktop-installer`, live computer-use claims, and multi-tenant cloud
  claims must remain blocked or deferred.
- Any raw prompt/response/screenshot, secret-like marker, or PII persistence is
  a release blocker.
- Field closure is exposed in snapshots as `designPartnerFieldEvidence`.

## Gate

```bash
make design-partner-field-evidence-gate
```

The gate runs schema generation, backend tests, CLI tests, field evidence
collection, independent attestation verification, strict RC promotion, field
pack generation, and Operator Panel coverage.
