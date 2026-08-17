# RFC Computer-Use 013: Conservative Semantic Step Verification

## Status

Implemented for the supervised vision-first runtime path. This does not change
the production qualification boundary.

## Goal

The runtime must not advance a multi-step vision loop solely because an input
action returned successfully. After an action executes, the verifier records a
semantic status:

- `satisfied`: the expected effect was observed in redacted fixture evidence
- `skipped`: the action does not require screen-change verification, such as
  `wait` or `move_mouse`
- `inconclusive`: the screen changed, but the expected effect was not proven
- `failed`: no useful change occurred, or a security blocker appeared

Only satisfied or skipped results count as successful progression signals.

## Privacy Boundary

Verification evidence is allowlisted metadata only. It may include observation
hashes, action digest, redacted text counts, and boolean match flags. It must not
include raw screenshot paths, image bytes, unredacted OCR text, or secrets.

## Runtime Behavior

`ConservativeVisionStepVerifier` now returns `VerificationResult` with:

- `status`
- `reason_code`
- `evidence`
- `before_observation_hash`
- `after_observation_hash`
- `action_digest`

Existing `verified`, `confidence`, `message`, and `details` fields remain for
backward compatibility.

If verification fails and the recovery budget is exhausted, the runtime uses the
semantic verifier `reason_code` as the stop reason when available.

## Current Deterministic Rules

- `wait` and `move_mouse` return `skipped`
- sensitive indicators after an action return
  `COMPUTER_USE_SENSITIVE_SURFACE_DETECTED`
- expected effect observed in redacted visible text returns `satisfied`
- changed observation without expected evidence returns `inconclusive`
- unchanged observation for mutating actions returns `failed`

## Verification

Targeted gate:

```bash
uv run --extra dev ruff check imperaos/computer_use/vision_runtime/models.py imperaos/computer_use/vision_runtime/verifier.py imperaos/computer_use/vision_runtime/runtime.py tests/test_computer_use_vision_verifier.py tests/test_computer_use_vision_runtime.py
uv run --extra dev pytest -q tests/test_computer_use_vision_verifier.py tests/test_computer_use_vision_runtime.py tests/test_computer_use_vision_replay.py tests/test_privacy_regression.py
git diff --check
```
