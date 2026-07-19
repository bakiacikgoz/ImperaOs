from pathlib import Path

import pytest

from imperaos.memory.semantic.index_manifest import read_manifest, write_manifest
from imperaos.memory.semantic.models import SemanticIndexManifest


def test_manifest_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    manifest = SemanticIndexManifest(
        indexId="idx",
        workspaceId="default",
        backendKind="in_memory_fixture",
        embeddingProfileId="deterministic-fixture-v1",
        sourceStateVersion=1,
        indexStateVersion=1,
        recordCount=1,
        rawPersistence=False,
    )

    write_manifest(path, manifest)

    assert read_manifest(path) == manifest


def test_manifest_rejects_corrupt_payload(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text('{"rawPersistence": true}', encoding="utf-8")

    with pytest.raises(ValueError):
        read_manifest(path)
