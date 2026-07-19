# Product-Complete Closure

The product-complete closure gate is the top-level local proof for ImperaOS /
ImperaOS as a self-hosted single-organization enterprise Agent Control Plane.

Canonical command:

```bash
uv run python scripts/run_product_complete_closure_gate.py --profile enterprise --json
```

The gate aggregates:

- Product scope and no-ship register.
- Real assistant runtime diagnostics.
- Operator Panel route/action productization.
- First-run readiness diagnostics.
- Enterprise workspace onboarding.
- Governed agent workflow smoke.
- Evidence/release closure.

Generated artifacts:

- `artifacts/product-complete-closure/product_complete_closure_report.json`
- `artifacts/product-complete-closure/product_complete_closure_report.md`
- `artifacts/product-complete-closure/product_complete_pr_body.md`
- `artifacts/product-complete-closure/no_ship_register.json`
