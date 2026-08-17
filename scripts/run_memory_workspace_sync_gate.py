from __future__ import annotations

import json
import tempfile
from pathlib import Path

from imperaos.memory.workspace_models import (
    MemoryPrincipal,
    MemoryWorkspace,
    MemoryWorkspaceMembership,
    WorkspaceMemoryRecord,
)
from imperaos.memory.workspace_store import WorkspaceMemoryStore
from imperaos.memory.workspace_sync import WorkspaceMemorySyncCoordinator


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        store = WorkspaceMemoryStore(root / "workspace_memory.sqlite3")
        store.upsert_principal(
            MemoryPrincipal(
                principalId="operator-local",
                principalType="operator",
                displayName="OP",
            )
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
                memoryId="wm_sync_gate",
                workspaceId="default",
                scopeType="personal",
                scopeId="operator-local",
                ownerPrincipalId="operator-local",
                memoryTarget="sync-gate",
                contentHash="b" * 64,
                summary="Workspace sync gate summary.",
            ),
            expected_state_version=None,
        )
        coordinator = WorkspaceMemorySyncCoordinator(store=store)
        pack_path = root / "workspace_sync_pack.json"
        pack = coordinator.export_pack(
            workspace_id="default",
            source_client_id="gate-cli",
            output_path=pack_path,
        )
        verify = coordinator.verify_pack(pack_path)
        report = coordinator.import_pack(input_path=pack_path, dry_run=True)
        status = (
            "pass"
            if pack.manifest.raw_content_included is False
            and verify.status == "pass"
            and report.status == "pass"
            else "fail"
        )
        print(
            json.dumps(
                {
                    "status": status,
                    "manifest": pack.manifest.model_dump(mode="json", by_alias=True),
                    "verify": verify.model_dump(mode="json", by_alias=True),
                    "import": report.model_dump(mode="json", by_alias=True),
                },
                indent=2,
                sort_keys=True,
            )
        )
        if status != "pass":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
