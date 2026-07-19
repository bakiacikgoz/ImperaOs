# Policy Pack Admin Guide

Validate and dry-run promotion before any policy activation:

```bash
uv run imperaos control-plane policy pack-validate \
  --manifest contracts/control_plane/fixtures/policy_pack_valid_enterprise.json \
  --json

uv run imperaos control-plane policy pack-promote-dry-run \
  --manifest contracts/control_plane/fixtures/policy_pack_valid_enterprise.json \
  --json
```

Unsafe allow rules for destructive, credential-sensitive, security-sensitive,
financial/legal, computer-use, or unknown risk classes are blocked.

