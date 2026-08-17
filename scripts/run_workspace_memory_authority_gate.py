from __future__ import annotations

import json
import tempfile
from pathlib import Path

from imperaos.memory.workspace_authority import build_workspace_memory_authority
from imperaos.memory.workspace_models import (
    MemoryPrincipal,
    MemoryWorkspace,
    MemoryWorkspaceMembership,
    WorkspaceMemoryQueryRequest,
    WorkspaceMemoryWriteRequest,
)
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        config = RuntimeConfig.from_profile("balanced")
        config.memory.workspace_authority.enabled = True
        config.memory.workspace_authority.db_path = str(root / "workspace_memory.sqlite3")
        authority = build_workspace_memory_authority(config, evidence_root=root / "evidence")
        authority.store.upsert_principal(
            MemoryPrincipal(
                principalId="operator-local",
                principalType="operator",
                displayName="OP",
            )
        )
        authority.store.create_workspace(
            MemoryWorkspace(
                workspaceId="default",
                displayName="Default",
                ownerPrincipalId="operator-local",
            )
        )
        authority.store.grant_membership(
            MemoryWorkspaceMembership(
                membershipId="member-operator-local",
                workspaceId="default",
                principalId="operator-local",
                roles=("owner",),
                grantedBy="operator-local",
            )
        )
        write = authority.propose_or_write(
            WorkspaceMemoryWriteRequest(
                workspaceId="default",
                principalId="operator-local",
                scopeType="personal",
                scopeId="operator-local",
                summary="Authority gate writes a redacted memory.",
                memoryTarget="authority-gate",
            )
        )
        query = authority.query(
            WorkspaceMemoryQueryRequest(
                workspaceId="default",
                principalId="operator-local",
                scopeType="personal",
                scopeId="operator-local",
                query="redacted",
            )
        )
        payload = {
            "status": "pass"
            if write.status == "committed" and query.status == "pass"
            else "fail",
            "write": write.model_dump(mode="json", by_alias=True),
            "query": query.model_dump(mode="json", by_alias=True),
            "health": authority.health().model_dump(mode="json", by_alias=True),
            "rawContentIncluded": False,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        if payload["status"] != "pass":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
