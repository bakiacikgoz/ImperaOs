from __future__ import annotations

from imperaos.memory.semantic.backends.in_memory_fixture import InMemoryFixtureSemanticBackend


class SQLiteTextSemanticBackend(InMemoryFixtureSemanticBackend):
    backend_kind = "sqlite_text"
