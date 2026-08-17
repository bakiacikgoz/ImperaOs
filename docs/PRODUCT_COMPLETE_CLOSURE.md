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

Every required readiness field starts as `not_run`. A field becomes `pass` only
after its named check actually runs successfully, and the report records that
check as readiness evidence. Missing or skipped required checks are blockers:
`not_run` never equals `pass`.

Generated artifacts:

- `artifacts/product-complete-closure/product_complete_closure_report.json`
- `artifacts/product-complete-closure/product_complete_closure_report.md`
- `artifacts/product-complete-closure/product_complete_pr_body.md`
- `artifacts/product-complete-closure/no_ship_register.json`

`--skip-commands` is diagnostic only and always produces no-ship blockers for
missing required checks. It cannot be used to create a passing closure report.
