from imperaos.memory.semantic.models import (
    MemorySemanticIndexSnapshot,
    SemanticIndexManifest,
)


def test_semantic_manifest_forbids_raw_persistence() -> None:
    manifest = SemanticIndexManifest(
        indexId="idx",
        workspaceId="default",
        backendKind="in_memory_fixture",
        embeddingProfileId="deterministic-fixture-v1",
        sourceStateVersion=1,
        indexStateVersion=1,
        recordCount=0,
        rawPersistence=False,
    )

    assert manifest.raw_persistence is False


def test_semantic_snapshot_defaults_disabled() -> None:
    snapshot = MemorySemanticIndexSnapshot()

    assert snapshot.status == "available_disabled"
    assert snapshot.raw_persistence is False
