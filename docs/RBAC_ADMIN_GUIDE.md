# RBAC Admin Guide

Inspect the local RBAC matrix:

```bash
uv run imperaos control-plane rbac matrix --profile lite --json
```

Check a permission without mutating state:

```bash
uv run imperaos control-plane rbac check \
  --actor-id identity-disabled \
  --permission config.read \
  --profile lite \
  --json
```

Unknown actors and missing permissions deny by default.

