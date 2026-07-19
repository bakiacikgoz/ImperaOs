from pathlib import Path

from imperaos.memory.authority import build_memory_authority, proposal_from_cli
from imperaos.memory.sync_importer import import_memory_sync_pack
from imperaos.memory.sync_pack import export_memory_sync_pack
from imperaos.runtime.config import RuntimeConfig


def test_sync_import_dry_run_and_apply_approval_gate(tmp_path: Path) -> None:
    config = RuntimeConfig.from_profile("balanced")
    config.memory.db_path = str(tmp_path / "memory.sqlite3")
    config.memory.v3_enabled = True
    config.memory.sync.enabled = True
    authority = build_memory_authority(config, evidence_root=tmp_path / "evidence")
    authority.propose_write(
        proposal_from_cli(
            actor="operator",
            scope="personal",
            owner_type="user",
            owner="operator",
            visibility="private",
            text="Portable memory summary.",
            role="operator",
            reason="test",
        )
    )
    output = tmp_path / "sync.json"
    export_memory_sync_pack(config=config, output_path=output, source_environment="test")

    dry_run = import_memory_sync_pack(config=config, input_path=output, dry_run=True)
    blocked_apply = import_memory_sync_pack(config=config, input_path=output, dry_run=False)

    assert dry_run.status == "pass"
    assert blocked_apply.status == "blocked"
    assert "MEMORY_SYNC_IMPORT_APPROVAL_REQUIRED" in blocked_apply.blocking_reasons
