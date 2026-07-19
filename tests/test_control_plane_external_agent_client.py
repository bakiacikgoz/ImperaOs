from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.external_agent_client import (
    run_external_agent_manifest,
    run_external_agent_pilot_suite,
)
from imperaos.runtime.config import RuntimeConfig

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[1]


def _config(tmp_path: Path) -> RuntimeConfig:
    config = RuntimeConfig.from_profile("enterprise")
    return config.model_copy(
        update={
            "governance": config.governance.model_copy(
                update={
                    "policy_path": str(REPO_ROOT / "config/policies/enterprise.toml"),
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                }
            )
        }
    )


def test_external_agent_manifest_read_only_allowed(tmp_path: Path) -> None:
    response = run_external_agent_manifest(
        manifest_path=REPO_ROOT / "examples/external_agents/read_only_inventory_agent/agent.json",
        request_path=REPO_ROOT / "examples/external_agents/read_only_inventory_agent/request.json",
        config=_config(tmp_path),
        root_dir=tmp_path / "control-plane",
    )

    assert response.policy_decision == "allow"
    assert response.evidence_verify_status == "valid"


def test_external_agent_pilot_suite_covers_policy_outcomes(tmp_path: Path) -> None:
    kwargs = {
        "examples_root": REPO_ROOT / "examples/external_agents",
        "output_path": tmp_path / "external-agent-pilot-report.json",
        "config": _config(tmp_path),
        "root_dir": tmp_path / "control-plane",
    }
    report = run_external_agent_pilot_suite(**kwargs)
    repeated = run_external_agent_pilot_suite(**kwargs)

    assert report["status"] == "pass"
    assert repeated["status"] == "pass"
    first_approvals = {
        case["case"]: case["approvalId"] for case in report["cases"] if case["approvalId"]
    }
    repeated_approvals = {
        case["case"]: case["approvalId"] for case in repeated["cases"] if case["approvalId"]
    }
    assert repeated_approvals == first_approvals

    decisions = {case["case"]: case["policyDecision"] for case in report["cases"]}
    assert decisions["read_only_inventory_agent"] == "allow"
    assert decisions["ops_remediation_agent"] == "require_approval"
    assert decisions["destructive_blocked_agent"] == "deny"


def test_external_agent_pilot_suite_covers_policy_outcomes_with_fresh_root(
    tmp_path: Path,
) -> None:
    report = run_external_agent_pilot_suite(
        examples_root=REPO_ROOT / "examples/external_agents",
        output_path=tmp_path / "external-agent-pilot-report.json",
        config=_config(tmp_path),
        root_dir=tmp_path / "control-plane",
    )

    assert report["status"] == "pass"
    decisions = {case["case"]: case["policyDecision"] for case in report["cases"]}
    assert decisions["read_only_inventory_agent"] == "allow"
    assert decisions["ops_remediation_agent"] == "require_approval"
    assert decisions["destructive_blocked_agent"] == "deny"


def test_external_agent_cli_run(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "control-plane",
            "external-agent",
            "run",
            "--profile",
            "enterprise",
            "--root-dir",
            str(tmp_path / "control-plane"),
            "--manifest",
            str(REPO_ROOT / "examples/external_agents/destructive_blocked_agent/agent.json"),
            "--request",
            str(REPO_ROOT / "examples/external_agents/destructive_blocked_agent/request.json"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["policyDecision"] == "deny"
