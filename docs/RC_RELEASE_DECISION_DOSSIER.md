# RC Release Decision Dossier

The release decision dossier combines RC gate evidence, RC freeze reconciliation, no-ship boundaries, and human sign-off status.

```bash
uv run imperaos release decision build --profile enterprise --artifact-root artifacts --output-root artifacts/rc-release-decision --json
uv run imperaos release decision verify --dossier artifacts/rc-release-decision/release_decision_dossier.json --allow-conditional --json
```

Expected status before real human sign-off is `conditional`. The system must not emit `approved_for_design_partner_rc` unless required sign-off files verify against the dossier hash.

The dossier is hash-only. It must not persist raw prompts, raw responses, screenshots, secrets, PII, signing credentials, or provider payloads.
