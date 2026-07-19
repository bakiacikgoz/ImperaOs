from __future__ import annotations

import json
from pathlib import Path

import jsonschema
from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.computer_use.models import ComputerUseMode
from imperaos.computer_use.vision_runtime.models import (
    InputActionType,
    StopDecision,
    VisionObservation,
)
from imperaos.computer_use.vision_runtime.planner import CandidateActionPlanner
from imperaos.computer_use.vision_runtime.policy import UniversalComputerUsePolicy
from imperaos.computer_use.vision_runtime.providers.ollama_vision import (
    OllamaVisionInterpreter,
)
from imperaos.contracts.operator_panel import OperatorCapabilitiesPayload
from imperaos.runtime.config import ComputerUseRuntimeConfig
from imperaos.runtime.platform import current_platform

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[1]
VISION_FIXTURE_DIR = REPO_ROOT / "contracts" / "computer_use" / "fixtures"
VISION_PROVIDER_SCHEMA_PATH = (
    REPO_ROOT / "contracts" / "computer_use" / "vision_provider_response.schema.json"
)
VISION_FIXTURE_NAMES = {
    "vision_click_submit.json",
    "vision_type_text.json",
    "vision_scroll_target.json",
    "vision_modal_open_close.json",
    "vision_denied_hotkey.json",
    "vision_sensitive_surface.json",
    "vision_empty_candidates.json",
}


def test_operator_capabilities_exposes_additive_vision_runtime_contract() -> None:
    result = runner.invoke(app, ["operator", "capabilities", "--json"])

    assert result.exit_code == 0
    payload = OperatorCapabilitiesPayload.model_validate_json(result.stdout)
    vision = payload.features.computer_use_vision_runtime

    assert vision.replayable is True
    assert vision.fail_closed is True
    assert vision.scope == "vision_first_desktop_web_file"
    assert set(vision.execution_modes).issubset({"dry_run", "step_approval", "execute"})

    if current_platform().label == "windows":
        assert vision.enabled is False
        assert vision.stage == "not_qualified"
        assert vision.reason_code == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    else:
        assert vision.enabled is False
        assert vision.stage in {"not_configured", "configured", "not_qualified"}


def test_operator_capabilities_schema_contains_vision_runtime_field() -> None:
    result = runner.invoke(app, ["operator", "capabilities", "--json"])
    assert result.exit_code == 0
    raw = json.loads(result.stdout)

    assert "computerUsePilot" in raw["features"]
    assert "computerUseVisionRuntime" in raw["features"]
    assert raw["features"]["computerUseVisionRuntime"]["failClosed"] is True


def test_cli_vision_first_runtime_fails_closed_without_provider(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "computer-use",
            "run",
            "--once",
            "Read the current screen",
            "--runtime",
            "vision-first",
            "--job-id",
            "vision-cli",
            "--root-dir",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["computer_use"]["status"] == "failed"
    assert payload["computer_use"]["stop_reason"] == "VISION_RUNTIME_NOT_CONFIGURED"
    assert payload["computer_use"]["redaction_report"]["raw_screenshot_persisted_count"] == 0


def test_deterministic_vision_fixtures_validate_provider_schema() -> None:
    schema = json.loads(VISION_PROVIDER_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)

    fixture_names = {path.name for path in VISION_FIXTURE_DIR.glob("vision_*.json")}

    assert fixture_names == VISION_FIXTURE_NAMES
    for name in sorted(VISION_FIXTURE_NAMES):
        payload = json.loads((VISION_FIXTURE_DIR / name).read_text(encoding="utf-8"))
        validator.validate(payload)
        assert "raw_screenshot_path" not in json.dumps(payload)


def test_deterministic_vision_fixtures_cover_planner_and_policy_outcomes() -> None:
    planner = CandidateActionPlanner(
        allowed_action_types=set(InputActionType),
        min_action_confidence=0.80,
        max_candidates=5,
    )
    policy = UniversalComputerUsePolicy(ComputerUseRuntimeConfig())

    outcomes = {}
    for name in sorted(VISION_FIXTURE_NAMES):
        payload = json.loads((VISION_FIXTURE_DIR / name).read_text(encoding="utf-8"))
        provider = OllamaVisionInterpreter(
            model="fixture",
            client=lambda payload=payload, **_: {"response": json.dumps(payload)},
        )
        interpretation = provider.interpret(
            objective=name.removesuffix(".json"),
            observation=VisionObservation(
                screenshot_hash="e" * 64,
                captured_at="2026-05-05T00:00:00+00:00",
                platform="macos",
                confidence=0.9,
            ),
            world=None,
        )
        action_or_stop = planner.next_action(
            objective=name,
            interpretation=interpretation,
            world=None,
        )
        if isinstance(action_or_stop, StopDecision):
            outcomes[name] = action_or_stop.reason
            continue

        if interpretation.sensitive_indicators:
            outcomes[name] = "sensitive_surface"
            continue

        decision = policy.classify(
            action_or_stop,
            VisionObservation(
                screenshot_hash="f" * 64,
                captured_at="2026-05-05T00:00:00+00:00",
                platform="macos",
                active_app=interpretation.active_app_guess,
                active_window_title=interpretation.active_window_title_guess,
                surface_kind=interpretation.surface_kind,
                visible_text_redacted=interpretation.visible_text_redacted,
                ui_elements=interpretation.ui_elements,
                sensitive_indicators=interpretation.sensitive_indicators,
                confidence=interpretation.confidence,
            ),
            mode=ComputerUseMode.EXECUTE,
        )
        outcomes[name] = decision.reason_code

    assert outcomes["vision_click_submit.json"] == "COMPUTER_USE_APPROVAL_REQUIRED"
    assert outcomes["vision_type_text.json"] == "COMPUTER_USE_APPROVAL_REQUIRED"
    assert outcomes["vision_scroll_target.json"] == "POLICY_ALLOW"
    assert outcomes["vision_modal_open_close.json"] == "COMPUTER_USE_APPROVAL_REQUIRED"
    assert outcomes["vision_denied_hotkey.json"] == "no_safe_candidate_action"
    assert outcomes["vision_sensitive_surface.json"] == "sensitive_surface"
    assert outcomes["vision_empty_candidates.json"] == "done"
