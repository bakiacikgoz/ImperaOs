# Mainline RC Release Train

This document records the local release train verification layer for the stacked
design partner RC work. It is not an auto-merge process.

Build the manifest and verification report:

```bash
uv run imperaos release train manifest \
  --profile enterprise \
  --output artifacts/design-partner-handoff/release_train_manifest.json \
  --json

uv run imperaos release train verify \
  --profile enterprise \
  --manifest artifacts/design-partner-handoff/release_train_manifest.json \
  --output artifacts/design-partner-handoff/RELEASE_TRAIN_REPORT.json \
  --json
```

Manual PR order remains:

1. Agent memory policy enforcement.
2. Governed pilot workflow release closure.
3. Design partner target evidence attestation closure.
4. Design partner RC handoff ops readiness.

After manual merge, regenerate baseline artifacts and run:

```bash
make design-partner-handoff-gate
make pilot-readiness-gate
make mainline-gate
```

Rollback is revert-only. Do not force-push release train branches after review.
