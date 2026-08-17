# Evidence Index And Reporting Guide

Build an evidence index:

```bash
uv run imperaos control-plane evidence index \
  --profile lite \
  --evidence-root artifacts/design-partner-rc/evidence-sample \
  --json
```

Build reports, alerts, and logs:

```bash
uv run imperaos control-plane reports manifest \
  --profile lite \
  --output-dir artifacts/design-partner-rc/reports-alerts-logs \
  --json
```

The index records verification history and blocks tampered packs.

