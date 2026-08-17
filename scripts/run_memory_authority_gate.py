from __future__ import annotations

import json
from pathlib import Path

from imperaos.memory.authority import build_memory_authority, proposal_from_cli
from imperaos.memory.models import MemoryRetrievalRequest, hash_identity
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    config = RuntimeConfig.from_profile("enterprise")
    authority = build_memory_authority(config)
    owner = "authority-gate"
    owner_hash = hash_identity(owner)
    actor_hash = hash_identity("authority-gate-actor")
    written = authority.propose_write(
        proposal_from_cli(
            actor="authority-gate-actor",
            scope="personal",
            owner_type="user",
            owner=owner,
            visibility="private",
            text="Prefers concise release notes with blocker lists.",
            role="Research Analyst Agent",
            reason="authority positive flow",
            memory_target="release-note-style",
            expected_state_version=0,
        )
    )
    conflict = authority.propose_write(
        proposal_from_cli(
            actor="authority-gate-actor",
            scope="personal",
            owner_type="user",
            owner=owner,
            visibility="private",
            text="Prefers terse release notes.",
            role="Research Analyst Agent",
            reason="conflict negative flow",
            memory_target="release-note-style",
            expected_state_version=0,
        )
    )
    retrieval = authority.retrieve(
        MemoryRetrievalRequest(
            actorIdHash=actor_hash,
            requesterRole="Research Analyst Agent",
            query="release notes blocker",
            allowedScopes=["personal"],
            scopeFilters=[
                {
                    "scope": "personal",
                    "ownerType": "user",
                    "ownerIdHash": owner_hash,
                    "namespace": "default",
                }
            ],
            visibilityFilters=["private"],
            includeContent=True,
            purpose="eval",
        )
    )
    status = (
        "pass"
        if written.status == "written"
        and conflict.status == "conflict"
        and retrieval.status == "pass"
        else "fail"
    )
    payload = {
        "status": status,
        "writeStatus": written.status,
        "conflictStatus": conflict.status,
        "retrievalStatus": retrieval.status,
        "rawContentIncluded": False,
    }
    out = Path("artifacts/memory-governance/memory_authority_gate.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
