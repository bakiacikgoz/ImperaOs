from __future__ import annotations

import json
import tempfile
from pathlib import Path

from imperaos.memory.semantic.fixtures import build_semantic_fixture
from imperaos.memory.semantic.models import IndexRebuildRequest, MemorySearchRequest


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        fixture = build_semantic_fixture(Path(temp))
        status = fixture.service.status("default")
        search = fixture.service.search(
            MemorySearchRequest(
                query="provider governance target evidence",
                principalId="operator-local",
                workspaceId="default",
                requestedScopes=("personal:operator-local",),
                limit=8,
            )
        )
        dry_run = fixture.service.rebuild(IndexRebuildRequest(workspaceId="default"))
        passed = (
            status.status == "ready"
            and dry_run.status == "dry_run"
            and any(hit.memory_id == fixture.expected_memory_id for hit in search.hits)
            and all(hit.raw_content_included is False for hit in search.hits)
        )
        payload = {
            "status": "pass" if passed else "fail",
            "indexStatus": status.model_dump(mode="json", by_alias=True),
            "search": search.model_dump(mode="json", by_alias=True),
            "dryRun": dry_run.model_dump(mode="json", by_alias=True),
            "rawContentIncluded": False,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        if not passed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
