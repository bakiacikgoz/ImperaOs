from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()


def test_control_plane_cli_register_simulate_submit_claims(tmp_path) -> None:
    root = tmp_path / "cp"
    spec = Path("examples/control_plane/agent_governed_ops.yaml").resolve()

    register = runner.invoke(
        app,
        [
            "control-plane",
            "agent",
            "register",
            "--spec",
            str(spec),
            "--profile",
            "lite",
            "--root-dir",
            str(root),
            "--json",
        ],
    )
    assert register.exit_code == 0
    assert json.loads(register.stdout)["agent_id"] == "governed-ops"

    listed = runner.invoke(
        app,
        [
            "control-plane",
            "agent",
            "list",
            "--root-dir",
            str(root),
            "--json",
        ],
    )
    assert listed.exit_code == 0
    agent_payload = json.loads(listed.stdout)["agents"][0]
    assert agent_payload["agent_type"] == "internal"
    assert agent_payload["policy_pack_id"] == "active-runtime-policy"
    assert agent_payload["last_evidence_status"] == "missing"

    simulate = runner.invoke(
        app,
        [
            "control-plane",
            "policy",
            "simulate",
            "--agent-id",
            "governed-ops",
            "--profile",
            "lite",
            "--root-dir",
            str(root),
            "--json",
        ],
    )
    assert simulate.exit_code == 0
    assert json.loads(simulate.stdout)["overall_status"] == "conditional"

    submit = runner.invoke(
        app,
        [
            "control-plane",
            "run",
            "submit",
            "--agent-id",
            "governed-ops",
            "--once",
            "inspect queue",
            "--profile",
            "lite",
            "--root-dir",
            str(root),
            "--json",
        ],
    )
    assert submit.exit_code == 0
    run_payload = json.loads(submit.stdout)
    assert run_payload["status"] == "approval_pending"
    assert run_payload["approval_ids"]

    evidence_dir = tmp_path / "evidence"
    export = runner.invoke(
        app,
        [
            "control-plane",
            "evidence",
            "export",
            "--run-id",
            run_payload["run_id"],
            "--output",
            str(evidence_dir),
            "--profile",
            "lite",
            "--root-dir",
            str(root),
            "--json",
        ],
    )
    assert export.exit_code == 0
    assert (evidence_dir / "manifest.json").exists()

    claims = runner.invoke(
        app,
        [
            "control-plane",
            "claims",
            "verify",
            "--profile",
            "lite",
            "--evidence-root",
            str(tmp_path),
            "--json",
        ],
    )
    assert claims.exit_code == 0
    assert json.loads(claims.stdout)["version"] == "control-plane.claim-matrix/v1"
