from pathlib import Path

from imperaos.memory.semantic.fixtures import build_semantic_fixture
from imperaos.memory.semantic.models import MemorySearchRequest
from imperaos.memory.workspace_models import WorkspaceMemoryWriteRequest


def test_semantic_search_does_not_return_cross_scope_or_raw(tmp_path: Path) -> None:
    fixture = build_semantic_fixture(tmp_path)

    result = fixture.service.search(
        MemorySearchRequest(
            query="private billing",
            principalId="operator-local",
            workspaceId="default",
            requestedScopes=("personal:operator-local",),
        )
    )

    assert fixture.hard_negative_memory_id not in {hit.memory_id for hit in result.hits}
    assert result.scope_violation_count == 0
    assert result.raw_leak_count == 0
    assert result.raw_content_included is False


def test_semantic_search_blocks_stale_index_by_default(tmp_path: Path) -> None:
    fixture = build_semantic_fixture(tmp_path)
    fixture.service.authority.propose_or_write(
        WorkspaceMemoryWriteRequest(
            workspaceId="default",
            principalId="operator-local",
            scopeType="personal",
            scopeId="operator-local",
            summary="A newly added memory should make the index stale.",
            memoryTarget="new-stale-record",
        )
    )

    result = fixture.service.search(
        MemorySearchRequest(
            query="newly added memory",
            principalId="operator-local",
            workspaceId="default",
            requestedScopes=("personal:operator-local",),
        )
    )

    assert result.status == "blocked"
    assert "MEMORY_SEMANTIC_INDEX_STALE" in result.reason_codes
    assert result.hits == ()
