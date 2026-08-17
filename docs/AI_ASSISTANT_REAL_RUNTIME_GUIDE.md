# AI Assistant Real Runtime Guide

The product assistant command surface is:

```bash
uv run imperaos assistant doctor --profile enterprise --json
uv run imperaos assistant models --profile enterprise --json
uv run imperaos assistant turn \
  --profile enterprise \
  --session-id session-1 \
  --turn-id turn-1 \
  --prompt-file compiled_prompt.md \
  --stream-json
```

Product mode cannot fall back to fake assistant answers. If no model/provider is
ready, `assistant doctor` returns setup diagnostics and `previewFallbackAllowed`
is `false`.
