from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from imperaos.computer_use.vision_runtime.platforms import evaluate_platform_matrix
from imperaos.runtime.config import ComputerUseRuntimeConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "evaluate_computer_use_platform_matrix.py"
FIXTURE_ROOT = REPO_ROOT / "contracts" / "computer_use" / "fixtures"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _enabled_macos_config() -> ComputerUseRuntimeConfig:
    return ComputerUseRuntimeConfig(
        runtime_mode="vision_first",
        vision_enabled=True,
        vision_provider="ollama",
        vision_model="llava",
        macos_live_enabled=True,
        macos_capture_backend="screencapture",
        macos_input_backend="quartz",
        macos_require_step_approval=True,
    )


def test_platform_matrix_passes_when_all_platforms_are_fail_closed() -> None:
    matrix = evaluate_platform_matrix(ComputerUseRuntimeConfig(), current_platform="windows")

    assert matrix["status"] == "pass"
    assert matrix["liveAutomationDefault"] is False
    assert matrix["rawScreenshotPersistenceDefault"] is False
    assert matrix["platforms"]["windows"]["reasonCode"] == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    assert matrix["platforms"]["linux"]["reasonCode"] == "LINUX_COMPUTER_USE_NOT_QUALIFIED"
    assert matrix["capabilityResolution"]["public_live_claim_allowed"] is False
    assert matrix["platforms"]["windows"]["capability"]["liveEnabled"] is False
    assert matrix["platforms"]["windows"]["capability"]["reasonCode"] == (
        "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    )
    assert matrix["platforms"]["windows"]["evidenceStatus"] == "missing"
    assert matrix["securityInvariants"]["screenTextTreatedAsUntrusted"] is True
    assert matrix["blockers"] == []


def test_platform_matrix_fails_if_live_claim_has_no_valid_evidence() -> None:
    config = ComputerUseRuntimeConfig(
        vision_enabled=True,
        vision_provider="mock",
        windows_live_enabled=True,
        windows_capture_backend="mock",
        windows_input_backend="mock",
    )
    matrix = evaluate_platform_matrix(config, current_platform="windows")

    assert matrix["status"] == "fail"
    assert "windows_live_ready_without_valid_qualification" in matrix["blockers"]


def test_platform_matrix_uses_resolver_for_supervised_macos_pass_fixture() -> None:
    fixture_path = FIXTURE_ROOT / "macos_supervised_v2_evidence_pass.json"
    matrix = evaluate_platform_matrix(
        _enabled_macos_config(),
        current_platform="macos",
        commit="fixture-commit",
        evidence_by_platform={"macos": _fixture(fixture_path.name)},
        evidence_paths={"macos": str(fixture_path)},
    )

    macos = matrix["platforms"]["macos"]
    assert matrix["status"] == "pass"
    assert macos["liveEnabled"] is False
    assert macos["supervisedLiveAllowed"] is True
    assert macos["public_live_claim_allowed"] is False
    assert macos["reasonCode"] == "MACOS_SUPERVISED_VISION_QUALIFIED_LOCAL_ONLY"
    assert macos["evidenceStatus"] == "valid"
    assert macos["capability"]["liveEnabled"] is False
    assert macos["capability"]["supervisedLiveAllowed"] is True


def test_platform_matrix_blocks_commit_mismatch_evidence() -> None:
    matrix = evaluate_platform_matrix(
        _enabled_macos_config(),
        current_platform="macos",
        commit="fixture-commit",
        evidence_by_platform={
            "macos": _fixture("macos_supervised_v2_evidence_fail_commit_mismatch.json")
        },
    )

    macos = matrix["platforms"]["macos"]
    assert matrix["status"] == "fail"
    assert macos["liveEnabled"] is False
    assert "COMPUTER_USE_EVIDENCE_COMMIT_MISMATCH" in {
        blocker["code"] for blocker in macos["capability"]["blockers"]
    }


def test_platform_matrix_raw_screenshot_failure_does_not_leak_raw_fields() -> None:
    matrix = evaluate_platform_matrix(
        _enabled_macos_config(),
        current_platform="macos",
        commit="fixture-commit",
        evidence_by_platform={
            "macos": _fixture("macos_supervised_v2_evidence_fail_raw_screenshot.json")
        },
    )

    encoded = json.dumps(matrix, sort_keys=True)
    assert matrix["status"] == "fail"
    assert "COMPUTER_USE_RAW_SCREENSHOT_INVARIANT_FAILED" in {
        blocker["code"]
        for blocker in matrix["platforms"]["macos"]["capability"]["blockers"]
    }
    assert "rawScreenshotPath" not in encoded
    assert "ocrText" not in encoded
    assert "visibleScreenText" not in encoded


def test_platform_matrix_script_writes_json_and_markdown(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "evaluate_computer_use_platform_matrix",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    output = tmp_path / "matrix.json"
    markdown = tmp_path / "matrix.md"
    exit_code = module.main(
        [
            "--profile",
            "balanced",
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ]
    )

    assert exit_code == 0
    assert output.exists()
    assert markdown.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    markdown_text = markdown.read_text(encoding="utf-8")
    assert payload["capabilityResolution"]["public_live_claim_allowed"] is False
    assert "Public Claim" in markdown_text
    assert "COMPUTER_USE_EVIDENCE_MISSING" in markdown_text
    assert "rawScreenshotPath" not in markdown_text
