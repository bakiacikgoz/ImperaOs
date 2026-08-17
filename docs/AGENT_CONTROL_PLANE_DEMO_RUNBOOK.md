# Agent Control Plane Demo Runbook

The canonical pilot demo runbook is now `docs/PILOT_DEMO_RUNBOOK.md`.

Use this compatibility checklist when an older handoff references this file:

1. Run `make pilot-readiness-gate`.
2. Open the Operator Panel in preview or Tauri mode.
3. Walk the deterministic pilot flow from Dashboard through Execution Surfaces.
4. Verify the latest evidence pack.
5. Confirm the claim guard matrix keeps computer-use live execution blocked.

CLI smoke commands:

```bash
uv run imperaos control-plane snapshot --json
uv run imperaos control-plane claims verify --profile enterprise --json
uv run python scripts/run_control_plane_demo.py --profile enterprise --json
```
