from pathlib import Path

from imperaos.memory.authority import build_memory_authority, proposal_from_cli
from imperaos.memory.indexes.dense_json import DenseJsonMemoryIndex
from imperaos.memory.indexes.turbovec_optional import TurboVecOptionalIndex
from imperaos.memory.models import (
    MemoryIndexRecord,
    MemoryRetrievalRequest,
    hash_identity,
    sha256_text,
)
from imperaos.memory.redaction import MemoryRedactor
from imperaos.runtime.config import RuntimeConfig


def _config(tmp_path: Path) -> RuntimeConfig:
    config = RuntimeConfig.from_profile("balanced")
    config.memory.db_path = str(tmp_path / "memory.sqlite3")
    config.memory.v3_enabled = True
    return config


def test_memory_authority_denies_secret_and_never_returns_raw_content(tmp_path: Path) -> None:
    authority = build_memory_authority(_config(tmp_path), evidence_root=tmp_path / "evidence")
    result = authority.propose_write(
        proposal_from_cli(
            actor="operator",
            scope="personal",
            owner_type="user",
            owner="operator",
            visibility="private",
            text="remember sk-test-secret-token-123456789",
            role="Research Analyst Agent",
            reason="secret guard",
        )
    )

    assert result.status == "denied"
    assert result.raw_content_included is False
    assert "MEMORY_SECRET_DETECTED" in result.blocking_reasons


def test_memory_authority_writes_retrieves_and_detects_target_conflict(tmp_path: Path) -> None:
    authority = build_memory_authority(_config(tmp_path), evidence_root=tmp_path / "evidence")
    proposal = proposal_from_cli(
        actor="operator",
        scope="personal",
        owner_type="user",
        owner="operator",
        visibility="private",
        text="Project Atlas prefers Friday release notes.",
        role="Research Analyst Agent",
        reason="user preference",
        memory_target="project:atlas",
        expected_state_version=0,
    )
    written = authority.propose_write(proposal)
    conflict = authority.propose_write(
        proposal_from_cli(
            actor="operator",
            scope="personal",
            owner_type="user",
            owner="operator",
            visibility="private",
            text="Project Atlas prefers Monday release notes.",
            role="Research Analyst Agent",
            reason="conflict check",
            memory_target="project:atlas",
            expected_state_version=0,
        )
    )

    result = authority.retrieve(
        MemoryRetrievalRequest(
            actorIdHash=hash_identity("operator"),
            requesterRole="operator",
            query="Friday release notes",
            allowedScopes=["personal"],
            scopeFilters=[
                {
                    "scope": "personal",
                    "ownerType": "user",
                    "ownerIdHash": hash_identity("operator"),
                    "namespace": "default",
                }
            ],
            visibilityFilters=["private"],
            includeContent=False,
            purpose="operator_review",
        )
    )

    assert written.status == "written"
    assert conflict.status == "conflict"
    assert result.status == "pass"
    assert result.hits[0].content_summary is None


def test_redactor_hashes_redacted_summary_not_raw_secret() -> None:
    redaction = MemoryRedactor().redact_candidate(
        candidate_text="Email me at test@example.com and use sk-test-secret-token-123456789",
        source_metadata={},
        privacy_mode=True,
    )

    assert redaction.secret_detected is True
    assert "test@example.com" not in redaction.redacted_summary
    assert "sk-test" not in redaction.redacted_summary
    assert redaction.content_hash == sha256_text(redaction.redacted_summary)


def test_dense_index_filters_scope_and_turbovec_is_disabled_by_default() -> None:
    owner_hash = hash_identity("operator")
    index = DenseJsonMemoryIndex()
    index.add(
        [
            MemoryIndexRecord(
                memoryId="mem_dense_test",
                scope="personal",
                ownerType="user",
                ownerIdHash=owner_hash,
                visibility="private",
                text="Friday release notes",
                contentHash=sha256_text("Friday release notes"),
            )
        ]
    )
    hits = index.search(
        query="release notes",
        scope_filters=[
            {
                "scope": "personal",
                "ownerType": "user",
                "ownerIdHash": owner_hash,
                "namespace": "default",
            }
        ],
        visibility_filters=["private"],
        limit=5,
    )

    assert len(hits) == 1
    assert TurboVecOptionalIndex(enabled=False).status().status == "disabled"
