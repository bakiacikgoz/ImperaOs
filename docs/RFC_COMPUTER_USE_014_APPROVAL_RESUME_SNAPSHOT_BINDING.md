# RFC Computer-Use 014: Approval Resume Snapshot Binding

## Status

Implemented as a validation core for vision-step approvals. This RFC does not
enable automatic production desktop execution.

## Goal

Approval resume must be bound to the same action, policy, objective, and screen
context that the operator reviewed. An approved ticket alone is not executable.

## Lifecycle

Vision approvals follow the existing governance lifecycle:

```text
pending -> approved -> executed -> consumed
```

Runtime resume validation requires:

- ticket status is `executed`
- ticket execution status is `executed`
- ticket is not consumed
- snapshot is not stale
- action digest matches
- policy hash matches
- observation hash and surface identity match
- sensitive indicators are absent

If any check fails, validation returns a fail-closed reason code such as
`APPROVAL_NOT_EXECUTED`, `REPLAY_BLOCKED`, or
`COMPUTER_USE_STALE_APPROVAL_SNAPSHOT`.

## Snapshot Fields

Vision approval snapshots now include both backward-compatible fields and the
new binding fields:

- `approval_kind`
- `objective_digest`
- `step_id`
- `action_digest`
- `planner_version`
- `provider_name`
- `provider_model`
- `observation_digest`
- `target_element_id`

Raw screenshot paths remain `null` and must not be used for resume validation.

## Verification

Targeted gate:

```bash
uv run --extra dev ruff check imperaos/computer_use/vision_runtime/approval.py imperaos/computer_use/vision_runtime/runtime.py tests/test_computer_use_vision_approval.py tests/test_approval_flow.py
uv run --extra dev pytest -q tests/test_computer_use_vision_approval.py tests/test_approval_flow.py tests/test_privacy_regression.py
git diff --check
```
