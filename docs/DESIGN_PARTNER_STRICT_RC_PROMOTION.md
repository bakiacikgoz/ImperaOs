# Design Partner Strict RC Promotion

Strict RC promotion is the final evaluator for design-partner field evidence. It
only returns `ready` when all of the following are true:

- field target evidence verification is `pass`;
- field mode is `target_environment`;
- independent non-developer operator attestation is `valid`;
- governed pilot workflow status is `pass`;
- support bundle and security posture summaries are present;
- unsupported desktop/live/cloud claims are blocked or deferred;
- raw, secret, and PII persistence flags are false.

Missing attestation is conditional, not ready. Invalid attestation, raw evidence
persistence, unsupported claim overreach, or failed target evidence verification
is blocked.

Run the evaluator:

```bash
uv run imperaos pilot field promote-rc \
  --profile enterprise \
  --field-root artifacts/design-partner-field-evidence \
  --rc-root artifacts/design-partner-rc
```

The report is written to:

```text
artifacts/design-partner-field-evidence/strict_rc_promotion.json
```

The Operator Panel reads the resulting snapshot through
`designPartnerFieldEvidence.strictRcStatus`.
