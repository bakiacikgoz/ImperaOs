# RFC Computer-Use 012: Real Vision Action Planner

## Status

Implemented for the supervised vision-first path. This RFC does not mark live
desktop automation as production-qualified.

## Scope

This change lets the Ollama vision provider return strict `candidate_actions`
alongside the existing screen interpretation fields. The runtime then selects
the first planner-valid candidate action instead of stopping with a deterministic
`done` decision on the Ollama path.

The supported default path remains fail-closed:

- invalid provider JSON or schema errors return `VISION_PROVIDER_INVALID_RESPONSE`
- missing candidate actions return a `done` stop decision
- low-confidence candidates are rejected before policy classification
- unsupported action types are rejected before policy classification
- invalid click-style target boxes are rejected before policy classification
- step approval still blocks execution before click/type/hotkey-style actions
- raw screenshot paths are not written into approval snapshots

## Provider Contract

The frozen JSON Schema for provider responses lives at:

```text
contracts/computer_use/vision_provider_response.schema.json
```

Provider responses may include:

```json
{
  "candidate_actions": [
    {
      "action_id": "act_click_submit",
      "action_type": "click",
      "target_element_id": "submit",
      "target_bbox": {"x": 0.6, "y": 0.45, "w": 0.2, "h": 0.15},
      "rationale": "The objective asks to submit the safe local fixture.",
      "expected_effect": "The fixture should show a submitted state.",
      "risk_class": "medium",
      "requires_approval": true,
      "confidence": 0.91
    }
  ]
}
```

`candidate_actions` may be omitted or empty. Omission is treated as an empty
list so older synthetic doctor fixtures remain compatible.

`hotkey` may be omitted, an array, or `null` on the wire. The runtime normalizes
`null` to an empty list before strict model validation. Extra top-level fields
or extra candidate action fields remain invalid and fail closed.

## Planner Rules

`CandidateActionPlanner` only performs candidate hygiene and selection. It does
not replace `UniversalComputerUsePolicy`.

The planner evaluates the first configured candidate window, preserves provider
ordering, and returns the first valid action. It rejects:

- action types outside the runtime `action_set`
- action confidence below `min_action_confidence`
- click, double-click, right-click, or move actions without a valid normalized
  target box
- target boxes where `x + w > 1.0` or `y + h > 1.0`
- type-text actions without text
- denied hotkeys such as `cmd+q`, `cmd+w`, and `cmd+space`

## Runtime Wiring

For `vision_provider="ollama"`, the vision-first runtime now wires:

- `OllamaVisionInterpreter`
- `CandidateActionPlanner`
- `MacOSInputExecutor`
- `ConservativeVisionStepVerifier`

For `vision_provider="mock"`, deterministic test wiring remains unchanged.

## Verification

Targeted gate:

```bash
uv run --extra dev ruff check imperaos/computer_use/vision_runtime/providers/ollama_vision.py imperaos/computer_use/vision_runtime/provider_doctor.py imperaos/computer_use/vision_runtime/planner.py imperaos/computer_use/vision_runtime/runtime.py imperaos/computer_use/vision_runtime/verifier.py imperaos/computer_use/runtime.py tests/test_computer_use_vision_provider.py tests/test_computer_use_vision_planner.py tests/test_computer_use_vision_runtime.py tests/test_computer_use_vision_policy.py tests/test_computer_use_vision_approval.py tests/test_computer_use_vision_verifier.py
uv run --extra dev pytest -q tests/test_computer_use_vision_provider.py tests/test_computer_use_vision_planner.py tests/test_computer_use_vision_runtime.py tests/test_computer_use_vision_policy.py tests/test_computer_use_vision_approval.py tests/test_computer_use_vision_verifier.py
```
