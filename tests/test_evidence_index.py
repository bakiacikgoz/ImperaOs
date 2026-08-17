from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.evidence_index import build_evidence_index
from imperaos.control_plane.evidence_pack import EvidencePackBuilder
from imperaos.control_plane.registry import AgentRegistry, load_agent_spec
from imperaos.control_plane.run_coordinator import ControlPlaneRunCoordinator
from imperaos.runtime.config import RuntimeConfig

runner = CliRunner()


def test_evidence_index_records_verification_history(tmp_path: Path) -> None:
    config, root_dir, evidence_dir = _evidence_pack(tmp_path)

    index = build_evidence_index(config=config, evidence_root=tmp_path, root_dir=root_dir)

    assert index.status == "pass"
    assert index.entries[0].path == str(evidence_dir)
    assert index.entries[0].replay_status == "verified"
    assert index.verification_history[0].status == "pass"
    assert (root_dir / "evidence-index" / "history.json").exists()


def test_evidence_index_blocks_tampered_pack(tmp_path: Path) -> None:
    config, root_dir, evidence_dir = _evidence_pack(tmp_path)
    run_summary = evidence_dir / "run_summary.json"
    payload = json.loads(run_summary.read_text(encoding="utf-8"))
    payload["status"] = "tampered"
    run_summary.write_text(json.dumps(payload), encoding="utf-8")

    index = build_evidence_index(config=config, evidence_root=tmp_path, root_dir=root_dir)

    assert index.status == "blocked"
    assert "EVIDENCE_HASH_MISMATCH" in index.blocking_reasons
    assert index.verification_history[0].status == "fail"


def test_evidence_index_cli(tmp_path: Path) -> None:
    _config, root_dir, _evidence_dir = _evidence_pack(tmp_path)

    result = runner.invoke(
        app,
        [
            "control-plane",
            "evidence",
            "index",
            "--profile",
            "lite",
            "--evidence-root",
            str(tmp_path),
            "--root-dir",
            str(root_dir),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["version"] == "control-plane.evidence-index/v1"


def _config(tmp_path: Path) -> RuntimeConfig:
    config = RuntimeConfig.from_profile("lite")
    return config.model_copy(
        update={
            "governance": config.governance.model_copy(
                update={
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "policy_path": "config/policies/lite.toml",
                }
            )
        }
    )


def _evidence_pack(tmp_path: Path) -> tuple[RuntimeConfig, Path, Path]:
    config = _config(tmp_path)
    root_dir = tmp_path / "cp"
    registry = AgentRegistry(root_dir=root_dir)
    registry.register(
        load_agent_spec("examples/control_plane/agent_governed_ops.yaml"),
        actor="test",
    )
    coordinator = ControlPlaneRunCoordinator(config=config, registry=registry, root_dir=root_dir)
    run = coordinator.submit_run(
        agent_id="governed-ops",
        user_input="inspect queue",
        actor="test",
        mode="dry_run",
    )
    evidence_dir = tmp_path / "control-plane" / "evidence" / f"evp-{run.run_id}"
    EvidencePackBuilder(config=config, root_dir=root_dir).export_for_run(
        run_id=run.run_id,
        output_dir=evidence_dir,
    )
    return config, root_dir, evidence_dir
