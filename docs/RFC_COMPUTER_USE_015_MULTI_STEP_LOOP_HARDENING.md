# RFC Computer-Use 015: Multi-Step Vision Runtime Loop Hardening

## Status

Implemented for the vision-first runtime loop. This RFC does not enable
unrestricted live desktop automation.

## Goal

The runtime must stop deterministic no-progress loops before they can keep
executing inputs. Planner output is treated as an input proposal, not proof that
the loop is making progress.

## Guards

The vision-first runtime now applies these guards before policy classification
and before input execution:

- repeated action digest stops with `VISION_REPEATED_ACTION_REJECTED`
- consecutive `wait` actions above `max_consecutive_wait_actions` stop with
  `VISION_WAIT_BUDGET_EXCEEDED`

The action digest uses the normalized `VisionAction` JSON payload with
`exclude_none=True`. A guard stop records a blocked step with the current policy
hash and does not call the input executor.

## Configuration

`ComputerUseRuntimeConfig.max_consecutive_wait_actions` defaults to `3`.

It can be configured through TOML as:

```toml
[computer_use]
max_consecutive_wait_actions = 3
```

and through the environment as:

```text
IMPERAOS_COMPUTER_USE_MAX_CONSECUTIVE_WAIT_ACTIONS=3
```

## Non-Goals

- no production qualification claim
- no Windows or Linux live enablement
- no raw screenshot persistence
- no bypass of approval or semantic verification gates

## Verification

Targeted gate:

```bash
uv run --extra dev ruff check imperaos/computer_use/vision_runtime/runtime.py imperaos/runtime/config.py tests/test_computer_use_vision_runtime.py
uv run --extra dev pytest -q tests/test_computer_use_vision_runtime.py tests/test_computer_use_vision_replay.py tests/test_fault_injection.py tests/test_policy_fail_closed.py
git diff --check
```
