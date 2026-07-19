from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.runtime.config import RuntimeConfig

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[1]


def test_computer_use_doctor_reports_all_platforms_without_enabling_live_execution() -> None:
    result = runner.invoke(
        app,
        ["computer-use", "doctor", "--profile", "balanced", "--platform", "all", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["contract_version"] == "3.0"
    assert payload["runtime"] == "computer_use_vision"
    assert set(payload["platforms"]) == {"macos", "windows", "linux"}
    assert payload["platforms"]["windows"]["liveEnabled"] is False
    assert payload["platforms"]["windows"]["reasonCode"] == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    assert payload["platforms"]["linux"]["reasonCode"] == "LINUX_COMPUTER_USE_NOT_QUALIFIED"
    resolution = payload["capabilityResolution"]
    assert resolution["artifactVersion"] == "computer-use-capability-resolution/v1"
    assert resolution["public_live_claim_allowed"] is False
    windows = resolution["platforms"]["windows"]
    assert windows["liveEnabled"] is False
    assert windows["supervisedLiveAllowed"] is False
    assert windows["reasonCode"] == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    assert windows["public_live_claim_allowed"] is False
    assert "COMPUTER_USE_EVIDENCE_MISSING" in {
        blocker["code"] for blocker in windows["blockers"]
    }
    assert payload["computerUse"]["visionRuntime"]["capability"][
        "public_live_claim_allowed"
    ] is False


def test_computer_use_doctor_can_scope_to_windows() -> None:
    result = runner.invoke(
        app,
        ["computer-use", "doctor", "--profile", "balanced", "--platform", "windows", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload["platforms"]) == {"windows"}
    assert payload["platforms"]["windows"]["stage"] == "not_qualified"
    assert set(payload["capabilityResolution"]["platforms"]) == {"windows"}
    assert payload["computerUse"]["visionRuntime"]["capability"]["platform"] == "windows"


def test_computer_use_doctor_reports_stale_evidence_from_resolver() -> None:
    result = runner.invoke(
        app,
        ["computer-use", "doctor", "--profile", "balanced", "--platform", "macos", "--json"],
        env={
            "IMPERAOS_COMPUTER_USE_MACOS_QUALIFICATION_REPORT": str(
                REPO_ROOT
                / "contracts"
                / "computer_use"
                / "fixtures"
                / "macos_supervised_v2_evidence_fail_stale.json"
            )
        },
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    macos = payload["capabilityResolution"]["platforms"]["macos"]
    assert macos["liveEnabled"] is False
    assert macos["evidence"]["status"] == "invalid"
    assert "COMPUTER_USE_EVIDENCE_STALE" in {
        blocker["code"] for blocker in macos["blockers"]
    }


def test_computer_use_doctor_reports_commit_mismatch_from_resolver(monkeypatch) -> None:
    monkeypatch.setattr("imperaos.cli._current_git_sha", lambda: "fixture-commit")

    result = runner.invoke(
        app,
        ["computer-use", "doctor", "--profile", "balanced", "--platform", "macos", "--json"],
        env={
            "IMPERAOS_COMPUTER_USE_MACOS_QUALIFICATION_REPORT": str(
                REPO_ROOT
                / "contracts"
                / "computer_use"
                / "fixtures"
                / "macos_supervised_v2_evidence_fail_commit_mismatch.json"
            )
        },
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    macos = payload["capabilityResolution"]["platforms"]["macos"]
    assert macos["liveEnabled"] is False
    assert "COMPUTER_USE_EVIDENCE_COMMIT_MISMATCH" in {
        blocker["code"] for blocker in macos["blockers"]
    }


def test_computer_use_doctor_reports_platform_mismatch_from_resolver(monkeypatch) -> None:
    monkeypatch.setattr("imperaos.cli._current_git_sha", lambda: "fixture-commit")

    result = runner.invoke(
        app,
        ["computer-use", "doctor", "--profile", "balanced", "--platform", "all", "--json"],
        env={
            "IMPERAOS_COMPUTER_USE_VISION_ENABLED": "1",
            "IMPERAOS_COMPUTER_USE_VISION_PROVIDER": "ollama",
            "IMPERAOS_COMPUTER_USE_VISION_MODEL": "llava",
            "IMPERAOS_COMPUTER_USE_MACOS_LIVE_ENABLED": "1",
            "IMPERAOS_COMPUTER_USE_MACOS_CAPTURE_BACKEND": "screencapture",
            "IMPERAOS_COMPUTER_USE_MACOS_INPUT_BACKEND": "quartz",
            "IMPERAOS_COMPUTER_USE_MACOS_QUALIFICATION_REPORT": str(
                REPO_ROOT
                / "contracts"
                / "computer_use"
                / "fixtures"
                / "macos_supervised_v2_evidence_pass.json"
            ),
        },
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    macos = payload["capabilityResolution"]["platforms"]["macos"]
    assert macos["liveEnabled"] is False
    assert macos["supervisedLiveAllowed"] is False
    assert "COMPUTER_USE_EVIDENCE_PLATFORM_MISMATCH" in {
        blocker["code"] for blocker in macos["blockers"]
    }


def test_computer_use_doctor_fails_closed_when_resolver_raises(monkeypatch) -> None:
    def _raise_resolution_error(**_kwargs: object) -> object:
        raise RuntimeError("resolver unavailable")

    monkeypatch.setattr(
        "imperaos.computer_use.vision_runtime.capability_resolver."
        "resolve_computer_use_capabilities",
        _raise_resolution_error,
    )

    result = runner.invoke(
        app,
        ["computer-use", "doctor", "--profile", "balanced", "--platform", "windows", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    windows = payload["capabilityResolution"]["platforms"]["windows"]
    assert windows["liveEnabled"] is False
    assert windows["reasonCode"] == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    assert [blocker["code"] for blocker in windows["blockers"]] == [
        "COMPUTER_USE_CAPABILITY_RESOLVER_EXCEPTION"
    ]


def test_computer_use_doctor_capability_output_does_not_leak_raw_screenshot_fields() -> None:
    result = runner.invoke(
        app,
        ["computer-use", "doctor", "--profile", "balanced", "--platform", "macos", "--json"],
        env={
            "IMPERAOS_COMPUTER_USE_MACOS_QUALIFICATION_REPORT": str(
                REPO_ROOT
                / "contracts"
                / "computer_use"
                / "fixtures"
                / "macos_supervised_v2_evidence_fail_raw_screenshot.json"
            )
        },
    )

    assert result.exit_code == 0
    payload_text = json.dumps(json.loads(result.stdout), sort_keys=True)
    assert "rawScreenshotPath" not in payload_text
    assert "ocrText" not in payload_text
    assert "visibleScreenText" not in payload_text


def test_computer_use_doctor_macos_shape_reports_exact_fail_closed_blockers() -> None:
    result = runner.invoke(
        app,
        ["computer-use", "doctor", "--profile", "balanced", "--platform", "macos", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["platform"] == "macos"
    assert payload["stage"] == "blocked"
    assert payload["liveEnabled"] is False
    assert payload["reasonCode"] == "MACOS_LIVE_OPT_IN_MISSING"
    assert payload["optIn"]["present"] is False
    assert payload["optIn"]["required"] is True
    assert payload["nextActions"]
    assert payload["permissionSubjects"]
    assert payload["manualInstructions"]
    assert payload["permissions"]["screenRecording"]["status"] in {
        "granted",
        "missing",
        "unknown",
    }
    assert payload["permissions"]["screenRecording"]["manualGrantRequired"] is (
        payload["permissions"]["screenRecording"]["status"] != "granted"
    )
    assert payload["permissions"]["screenRecording"]["autoGrantAttempted"] is False
    assert payload["permissions"]["accessibility"]["status"] in {
        "granted",
        "missing",
        "unknown",
    }
    assert payload["permissions"]["accessibility"]["manualGrantRequired"] is (
        payload["permissions"]["accessibility"]["status"] != "granted"
    )
    assert payload["permissions"]["accessibility"]["autoGrantAttempted"] is False
    assert payload["permissions"]["inputMonitoring"]["status"] == "not_required"
    assert payload["provider"]["ready"] is False
    assert payload["provider"]["kind"] == "none"
    assert payload["capture"]["backend"] == "disabled"
    assert payload["capture"]["reasonCode"] == "MACOS_CAPTURE_BACKEND_DISABLED"
    assert payload["input"]["backend"] == "disabled"
    assert payload["input"]["reasonCode"] == "MACOS_INPUT_BACKEND_DISABLED"
    assert payload["qualification"]["reasonCode"] == "MACOS_QUALIFICATION_REPORT_MISSING"
    assert payload["safety"]["rawScreenshotPersistence"] is False
    assert payload["safety"]["terminalPolicy"] == "deny"
    assert payload["safety"]["sensitiveSurfacePolicy"] == "stop"


def test_computer_use_qualification_verify_fails_closed_when_report_is_missing(
    tmp_path,
) -> None:
    result = runner.invoke(
        app,
        [
            "computer-use",
            "qualification",
            "verify",
            "--profile",
            "balanced",
            "--platform",
            "windows",
            "--report",
            str(tmp_path / "missing.json"),
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["allowed"] is False
    assert "VISION_PLATFORM_QUALIFICATION_MISSING" in payload["blockers"]


def test_computer_use_qualification_verify_accepts_schema_input_fixture() -> None:
    result = runner.invoke(
        app,
        [
            "computer-use",
            "qualification",
            "verify",
            "--schema",
            str(REPO_ROOT / "contracts" / "computer_use" / "platform_qualification.schema.json"),
            "--input",
            str(
                REPO_ROOT
                / "contracts"
                / "computer_use"
                / "fixtures"
                / "windows_platform_qualification_pass_fixture.json"
            ),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["reviewOnly"] is True
    assert payload["runtimeLiveEnabled"] is False
    assert payload["platform"] == "windows"
    assert payload["checks"]["approval_freshness_enforced"] is True
    assert payload["checks"]["replay_integrity_verified"] is True


def test_macos_live_qualification_run_blocks_without_explicit_opt_in(tmp_path) -> None:
    output = tmp_path / "macos_qualification_report.json"
    result = runner.invoke(
        app,
        [
            "computer-use",
            "qualification",
            "run",
            "--profile",
            "balanced",
            "--platform",
            "macos",
            "--suite",
            "live-fixture-smoke",
            "--mode",
            "supervised",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert report["status"] == "blocked"
    assert report["qualificationStatus"] == "blocked"
    assert report["qualificationPassed"] is False
    assert report["fixtureQualified"] is False
    assert report["productionQualified"] is False
    assert report["liveEnabled"] is False
    assert report["liveEnabledDefault"] is False
    assert report["stage"] == "blocked"
    assert report["scope"] == "supervised_local_fixtures"
    assert report["safety"]["rawScreenshotPersistedCount"] == 0
    assert report["safety"]["replayIntegrityVerified"] is True
    assert report["artifacts"]["rawScreenshotCount"] == 0
    assert report["artifacts"]["phase4dPreflightPath"].endswith(
        "macos_phase4d_preflight.json"
    )
    assert report["artifacts"]["phase4dFlagInventoryPath"].endswith(
        "macos_phase4d_flag_inventory.json"
    )
    assert report["artifacts"]["phase4ePreflightPath"].endswith(
        "macos_phase4e_preflight.json"
    )
    assert report["artifacts"]["phase4eFlagInventoryPath"].endswith(
        "macos_phase4e_flag_inventory.json"
    )
    assert report["artifacts"]["phase4ePermissionReadinessPath"].endswith(
        "macos_phase4e_permission_readiness.json"
    )
    assert report["provider"]["strictJsonValidated"] is False
    assert report["capture"]["rawPersistedCount"] == 0
    assert (output.parent / "macos_phase4d_preflight.json").exists()
    assert (output.parent / "macos_phase4d_flag_inventory.json").exists()
    phase4e_preflight = output.parent / "macos_phase4e_preflight.json"
    phase4e_inventory = output.parent / "macos_phase4e_flag_inventory.json"
    phase4e_permissions = output.parent / "macos_phase4e_permission_readiness.json"
    assert phase4e_preflight.exists()
    assert phase4e_inventory.exists()
    assert phase4e_permissions.exists()
    permission_payload = json.loads(phase4e_permissions.read_text(encoding="utf-8"))
    assert permission_payload["autoGrantAttempted"] is False
    assert permission_payload["manualInstructions"]
    inventory_payload = json.loads(phase4e_inventory.read_text(encoding="utf-8"))
    assert inventory_payload["vision_enabled"]["default"] is False
    assert inventory_payload["ollama_model_pull_opt_in"]["default"] is False
    assert "MACOS_LIVE_OPT_IN_MISSING" in report["blockers"]
    assert "MACOS_LIVE_ACK_MISSING" in report["blockers"]
    assert "MACOS_SUPERVISED_FIXTURE_ONLY_REQUIRED" in report["blockers"]
    assert "MACOS_STEP_APPROVAL_REQUIRED" in report["blockers"]
    assert "MACOS_CAPTURE_BACKEND_DISABLED" in report["blockers"]
    assert "MACOS_INPUT_BACKEND_DISABLED" in report["blockers"]
    assert report["optIn"]["present"] is False
    assert {fixture["id"] for fixture in report["fixtures"]} == {
        "local_browser_form",
        "textedit_safe_typing",
        "finder_fixture_file",
        "sensitive_surface_stop",
        "terminal_deny",
    }
    assert all(fixture["status"] == "skipped" for fixture in report["fixtures"])


def test_computer_use_provider_doctor_command_blocks_without_model() -> None:
    result = runner.invoke(
        app,
        [
            "computer-use",
            "provider",
            "doctor",
            "--provider",
            "ollama",
            "--synthetic-fixture",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["reasonCode"] == "VISION_PROVIDER_MODEL_NOT_CONFIGURED"


def test_macos_live_qualification_run_blocks_without_acknowledgment(tmp_path) -> None:
    output = tmp_path / "macos_qualification_report.json"
    result = runner.invoke(
        app,
        [
            "computer-use",
            "qualification",
            "run",
            "--profile",
            "balanced",
            "--platform",
            "macos",
            "--suite",
            "live-fixture-smoke",
            "--mode",
            "preflight",
            "--output",
            str(output),
            "--json",
        ],
        env={
            "IMPERAOS_COMPUTER_USE_LIVE_MACOS": "1",
            "IMPERAOS_COMPUTER_USE_SUPERVISED_FIXTURE_ONLY": "1",
            "IMPERAOS_COMPUTER_USE_REQUIRE_STEP_APPROVAL": "1",
        },
    )

    assert result.exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["qualificationStatus"] == "blocked"
    assert "MACOS_LIVE_ACK_MISSING" in report["blockers"]


def test_macos_qualification_replay_verify_passes_integrity_for_blocked_report(tmp_path) -> None:
    output = tmp_path / "macos_qualification_report.json"
    run_result = runner.invoke(
        app,
        [
            "computer-use",
            "qualification",
            "run",
            "--profile",
            "balanced",
            "--platform",
            "macos",
            "--suite",
            "live-fixture-smoke",
            "--mode",
            "supervised",
            "--output",
            str(output),
            "--json",
        ],
    )
    assert run_result.exit_code == 0

    result = runner.invoke(
        app,
        [
            "computer-use",
            "replay",
            "--report",
            str(output),
            "--verify",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["verified"] is True
    assert payload["qualificationStatus"] == "blocked"
    assert payload["qualificationPassed"] is False
    assert payload["replayIntegrityVerified"] is True
    assert payload["auditHashChainVerified"] is True
    assert payload["checks"]["raw_screenshot_policy"] is True
    assert payload["checks"]["hash_chain_verified"] is True
    assert payload["checks"]["audit_hash_chain_verified"] is True


def test_all_profiles_keep_computer_use_defaults_fail_closed() -> None:
    for profile in ("balanced", "default", "enterprise", "lite", "research", "restricted"):
        config = RuntimeConfig.from_profile(profile, root_dir=REPO_ROOT).computer_use

        assert config.vision_enabled is False
        assert config.vision_provider == "none"
        assert config.raw_screenshot_persistence is False
        assert config.raw_screenshot_retention == "disabled"
        assert config.raw_screenshot_max_count == 0
        assert config.terminal_control == "deny"
        assert config.sensitive_surface_policy == "stop"
        assert config.macos_live_enabled is False
        assert config.macos_capture_backend == "disabled"
        assert config.windows_live_enabled is False
        assert config.linux_live_enabled is False
