# Design Partner First-Run Operations

The first-run drill is deterministic by default and records only status, reason
codes, and output hashes. It does not persist raw command output.

```bash
uv run imperaos pilot ops drill \
  --profile enterprise \
  --mode deterministic \
  --output-root artifacts/design-partner-handoff \
  --json
```

The drill covers:

- config resolve;
- control-plane doctor;
- security baseline;
- identity whoami;
- metrics snapshot;
- control-plane snapshot;
- claim guard verify;
- governed pilot workflow verify;
- field evidence verify;
- evidence pack verify;
- support bundle export.
- handoff pack build/verify.

Stop on any `blocked` step. Conditional steps are expected in local deterministic
mode when identity or target-environment evidence is not present.
