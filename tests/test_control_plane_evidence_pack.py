from __future__ import annotations

import json
from pathlib import Path

from imperaos.control_plane.evidence_pack import EvidencePackBuilder
from imperaos.control_plane.registry import AgentRegistry, load_agent_spec
from imperaos.control_plane.run_coordinator import ControlPlaneRunCoordinator
from imperaos.runtime.config import RuntimeConfig


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


def _create_run(tmp_path: Path):
    registry = AgentRegistry(root_dir=tmp_path / "cp")
    registry.register(
        load_agent_spec("examples/control_plane/agent_governed_ops.yaml"),
        actor="test",
    )
    coordinator = ControlPlaneRunCoordinator(
        config=_config(tmp_path),
        registry=registry,
        root_dir=tmp_path / "cp",
    )
    return coordinator.submit_run(
        agent_id="governed-ops",
        user_input="inspect queue",
        actor="test",
        mode="dry_run",
    )


def test_evidence_export_and_verify_pass(tmp_path) -> None:
    run = _create_run(tmp_path)
    builder = EvidencePackBuilder(config=_config(tmp_path), root_dir=tmp_path / "cp")

    manifest = builder.export_for_run(run_id=run.run_id, output_dir=tmp_path / "evidence")
    result = builder.verify(manifest_path=tmp_path / "evidence" / "manifest.json")

    assert manifest.run_id == run.run_id
    assert result.status == "pass"
    assert result.hash_chain_verified is True


def test_evidence_verify_detects_tamper(tmp_path) -> None:
    run = _create_run(tmp_path)
    builder = EvidencePackBuilder(config=_config(tmp_path), root_dir=tmp_path / "cp")
    builder.export_for_run(run_id=run.run_id, output_dir=tmp_path / "evidence")
    run_summary = tmp_path / "evidence" / "run_summary.json"
    payload = json.loads(run_summary.read_text(encoding="utf-8"))
    payload["status"] = "tampered"
    run_summary.write_text(json.dumps(payload), encoding="utf-8")

    result = builder.verify(manifest_path=tmp_path / "evidence" / "manifest.json")

    assert result.status == "fail"
    assert "EVIDENCE_HASH_MISMATCH" in result.blocking_reasons
