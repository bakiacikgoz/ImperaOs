from pathlib import Path

from imperaos.memory.workspace_models import (
    MemoryPrincipal,
    MemoryWorkspace,
    MemoryWorkspaceMembership,
    WorkspaceMemoryRecord,
)
from imperaos.memory.workspace_store import WorkspaceMemoryStore
from imperaos.memory.workspace_sync import WorkspaceMemorySyncCoordinator


def _store(tmp_path: Path) -> WorkspaceMemoryStore:
    store = WorkspaceMemoryStore(tmp_path / "workspace_memory.sqlite3")
    store.upsert_principal(
        MemoryPrincipal(principalId="operator-local", principalType="operator", displayName="OP")
    )
    store.create_workspace(
        MemoryWorkspace(
            workspaceId="default",
            displayName="Default",
            ownerPrincipalId="operator-local",
        )
    )
    store.grant_membership(
        MemoryWorkspaceMembership(
            membershipId="member-operator-local",
            workspaceId="default",
            principalId="operator-local",
            roles=("owner",),
            grantedBy="operator-local",
        )
    )
    store.write_record(
        WorkspaceMemoryRecord(
            memoryId="wm_sync_record",
            workspaceId="default",
            scopeType="personal",
            scopeId="operator-local",
            ownerPrincipalId="operator-local",
            memoryTarget="sync-target",
            contentHash="a" * 64,
            summary="Sync pack hash-only summary.",
        ),
        expected_state_version=None,
    )
    return store


def test_workspace_sync_export_verify_and_import_dry_run(tmp_path: Path) -> None:
    coordinator = WorkspaceMemorySyncCoordinator(store=_store(tmp_path))
    pack_path = tmp_path / "pack.json"

    pack = coordinator.export_pack(
        workspace_id="default",
        source_client_id="cli-test",
        output_path=pack_path,
    )
    verify = coordinator.verify_pack(pack_path)
    report = coordinator.import_pack(input_path=pack_path, dry_run=True)

    assert pack.manifest.raw_content_included is False
    assert verify.status == "pass"
    assert report.status == "pass"
    assert report.raw_content_included is False


def test_workspace_sync_verify_fails_on_tamper(tmp_path: Path) -> None:
    coordinator = WorkspaceMemorySyncCoordinator(store=_store(tmp_path))
    pack_path = tmp_path / "pack.json"
    coordinator.export_pack(
        workspace_id="default",
        source_client_id="cli-test",
        output_path=pack_path,
    )
    payload = pack_path.read_text(encoding="utf-8").replace("Sync pack", "Tampered")
    pack_path.write_text(payload, encoding="utf-8")

    verify = coordinator.verify_pack(pack_path)

    assert verify.status == "fail"
    assert any(
        reason.startswith("MEMORY_SYNC_ITEM_HASH_MISMATCH")
        for reason in verify.blocking_reasons
    )
