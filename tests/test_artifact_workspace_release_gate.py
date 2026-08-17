from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_artifact_workspace_release_gate import (
    GATE_REPORTS,
    REQUIRED_RELEASE_ARTIFACTS,
    _extract_performance_evidence,
    _run_command,
    build_release_readiness,
    evaluate_editor_adapter_gate,
    gate_commands,
    run_leaf_gate,
)


def _report(candidate: str, *, status: str = "pass", test_count: int = 1) -> dict[str, object]:
    return {
        "schemaVersion": "artifact-workspace-gate/v1",
        "candidateSha": candidate,
        "status": status,
        "testCount": test_count,
        "commands": [],
        "blockingReasons": [],
    }


def test_release_readiness_requires_one_immutable_candidate_and_nonzero_tests() -> None:
    candidate = "a" * 40
    reports = {
        gate: _report(candidate)
        for gate in ("contract", "storage", "rpc", "security", "ui", "e2e", "export")
    }
    reports["license"] = _report(candidate, test_count=2)

    ready = build_release_readiness(
        candidate,
        reports,
        dirty_paths=[],
        final_candidate_sha=candidate,
        final_dirty_paths=[],
    )
    assert ready["status"] == "pass"
    assert ready["blockingReasons"] == []
    assert ready["featureFlagDefaults"]["artifact_workspace.enabled"] is False
    assert ready["featureFlagDefaults"]["artifact_workspace.export.enabled"] is False

    reports["e2e"] = _report(candidate, test_count=0)
    blocked = build_release_readiness(candidate, reports, dirty_paths=[])
    assert blocked["status"] == "fail"
    assert "ZERO_TESTS:e2e" in blocked["blockingReasons"]

    reports["e2e"] = _report("b" * 40)
    stale = build_release_readiness(candidate, reports, dirty_paths=[])
    assert "CANDIDATE_MISMATCH:e2e" in stale["blockingReasons"]

    moved = build_release_readiness(
        candidate,
        reports,
        dirty_paths=[],
        final_candidate_sha="c" * 40,
        final_dirty_paths=[" M imperaos/artifacts/service.py"],
    )
    assert "CANDIDATE_CHANGED" in moved["blockingReasons"]
    assert any(
        reason.startswith("FINAL_DIRTY_WORKTREE:")
        for reason in moved["blockingReasons"]
    )


def test_license_gate_resolves_trusted_bundled_fallback_adapters() -> None:
    report = evaluate_editor_adapter_gate(
        {
            "blockers": [
                {"code": "LICENSE_GATE_BLOCKED", "subject": "handsontable"},
                {"code": "LICENSE_GATE_BLOCKED", "subject": "@handsontable/react-wrapper"},
                {"code": "LICENSE_GATE_BLOCKED", "subject": "tldraw"},
            ],
            "matrixValid": True,
        },
        license_capabilities={"spreadsheet": False, "canvas": False},
        fallback_capabilities={"spreadsheet": True, "canvas": True},
    )
    assert report["status"] == "pass"
    assert report["mode"] == "adapter_resolved"
    assert report["commercialCapabilities"] == {
        "spreadsheet": False,
        "canvas": False,
    }
    assert report["fallbackCapabilities"] == {
        "spreadsheet": True,
        "canvas": True,
    }
    assert report["effectiveCapabilities"] == {
        "spreadsheet": True,
        "canvas": True,
    }
    assert report["adapters"] == {
        "spreadsheet": "bundled_fallback",
        "canvas": "bundled_fallback",
    }

    with pytest.raises(ValueError, match="unexpected license blocker"):
        evaluate_editor_adapter_gate(
            {
                "blockers": [{"code": "CSP_DISABLED", "subject": "tauri.conf.json"}],
                "matrixValid": True,
            },
            license_capabilities={"spreadsheet": False, "canvas": False},
            fallback_capabilities={"spreadsheet": True, "canvas": True},
        )

    with pytest.raises(ValueError, match="requires a trusted adapter"):
        evaluate_editor_adapter_gate(
            {"blockers": [], "matrixValid": True},
            license_capabilities={"spreadsheet": False, "canvas": False},
            fallback_capabilities={"spreadsheet": False, "canvas": True},
        )


def test_release_surface_declares_exact_reports_make_targets_and_ci() -> None:
    root = Path(__file__).resolve().parents[1]
    assert set(GATE_REPORTS) == {
        "contract", "storage", "rpc", "security", "ui", "e2e", "export", "license"
    }
    assert set(REQUIRED_RELEASE_ARTIFACTS) == {
        "contract-report.json",
        "storage-integrity-report.json",
        "rpc-performance-report.json",
        "security-report.json",
        "UI_TEST_REPORT.md",
        "export-report.json",
        "license-report.json",
        "release-readiness.json",
        "RELEASE_READINESS.md",
        "NO_SHIP_REGISTER.md",
    }
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    for target in (
        "artifact-contract-gate",
        "artifact-storage-gate",
        "artifact-rpc-gate",
        "artifact-security-gate",
        "artifact-ui-gate",
        "artifact-e2e-gate",
        "artifact-export-gate",
        "artifact-license-gate",
        "artifact-workspace-release-gate",
    ):
        assert f"{target}:" in makefile
    workflow = (root / ".github/workflows/artifact-workspace-ci.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_call:" in workflow
    assert "windows-latest" in workflow
    assert "macos-latest" in workflow
    assert "--gate workspace-release" in workflow
    product_closure = (root / ".github/workflows/product-complete-closure.yml").read_text(
        encoding="utf-8"
    )
    assert "uses: ./.github/workflows/artifact-workspace-ci.yml" in product_closure
    assert "artifact-workspace-release" in product_closure
    package = json.loads((root / "apps/operator-panel/package.json").read_text(encoding="utf-8"))
    assert "pass-with-no-tests" not in package["scripts"]["test:e2e"]


def test_security_gate_contains_artifact_assistant_and_form_trust_regressions() -> None:
    flattened = " ".join(part for command in gate_commands("security") for part in command)
    assert "tests/test_artifact_assistant_integration.py" in flattened
    assert "tests/test_artifact_form_submission.py" in flattened


def test_e2e_gate_contains_phase_23_artifact_quality_matrix() -> None:
    flattened = " ".join(part for command in gate_commands("e2e") for part in command)
    for spec in (
        "e2e/artifact-security.spec.ts",
        "e2e/artifact-accessibility.spec.ts",
        "e2e/artifact-responsive.spec.ts",
        "e2e/assistant-artifact-integration.spec.ts",
    ):
        assert spec in flattened


def test_performance_markers_are_emitted_and_required_by_rpc_ui_reports(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1]
    performance_test = (
        root
        / "apps/operator-panel/src/artifact-workspace/artifactPerformance.test.tsx"
    )
    assert performance_test.is_file()
    assert any(command[-1] == "test" for command in gate_commands("ui"))

    evidence = _extract_performance_evidence(
        'noise\nARTIFACT_PERFORMANCE_JSON={"workload":"rpc-matrix","p95Ms":12.5}\n'
    )
    assert evidence == [{"workload": "rpc-matrix", "p95Ms": 12.5}]

    def command_runner(command: list[str], _root: Path) -> dict[str, object]:
        result: dict[str, object] = {
            "name": "focused",
            "exitCode": 0,
            "durationMs": 1.0,
            "testCount": 1,
            "stdoutSha256": "a" * 64,
            "stderrSha256": "b" * 64,
        }
        if any(part.endswith("test_artifact_rpc_performance.py") for part in command):
            result["performanceEvidence"] = [
                {"workload": "rpc-matrix", "p95Ms": 12.5, "errors": 0}
            ]
        return result

    report = run_leaf_gate(
        "rpc",
        repo_root=tmp_path,
        output_root=tmp_path,
        candidate_sha="a" * 40,
        profile="enterprise",
        command_runner=command_runner,
    )
    assert report["status"] == "pass"
    assert report["performanceEvidence"] == [
        {"workload": "rpc-matrix", "p95Ms": 12.5, "errors": 0}
    ]

    missing = run_leaf_gate(
        "ui",
        repo_root=tmp_path,
        output_root=tmp_path,
        candidate_sha="a" * 40,
        profile="enterprise",
        command_runner=lambda _command, _root: {
            "name": "focused",
            "exitCode": 0,
            "durationMs": 1.0,
            "testCount": 1,
            "stdoutSha256": "a" * 64,
            "stderrSha256": "b" * 64,
        },
    )
    assert missing["status"] == "fail"
    assert "PERFORMANCE_EVIDENCE_MISSING:ui" in missing["blockingReasons"]


def test_command_runner_reports_missing_executable_without_crashing(tmp_path: Path) -> None:
    result = _run_command(["imperaos-command-that-does-not-exist"], tmp_path)
    assert result["exitCode"] == 127
    assert result["testCount"] == 0
