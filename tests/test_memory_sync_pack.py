import json
from pathlib import Path

from imperaos.memory.authority import build_memory_authority, proposal_from_cli
from imperaos.memory.sync_pack import export_memory_sync_pack, verify_memory_sync_pack
from imperaos.runtime.config import RuntimeConfig


def test_sync_pack_export_verify_and_tamper_detection(tmp_path: Path) -> None:
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
            text="Remember compact sync packs.",
            role="operator",
            reason="test",
        )
    )
    output = tmp_path / "sync.json"

    pack = export_memory_sync_pack(
        config=config,
        output_path=output,
        source_environment="test",
    )
    assert pack.manifest.raw_content_included is False
    assert verify_memory_sync_pack(output).status == "pass"

    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["records"][0]["contentSummary"] = "tampered"
    output.write_text(json.dumps(payload), encoding="utf-8")
    assert verify_memory_sync_pack(output).status == "fail"
