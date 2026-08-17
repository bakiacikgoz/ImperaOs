from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from imperaos.artifacts import migrations
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.migrations import (
    ArtifactMigration,
    connect_artifact_metadata,
    migrate_artifact_metadata,
)


def test_migration_dry_run_reports_capacity_without_creating_database(tmp_path: Path) -> None:
    database = tmp_path / "metadata" / "artifacts.sqlite3"

    report = migrate_artifact_metadata(database, dry_run=True)

    assert report.current_version == 0
    assert report.target_version == 12
    assert report.pending_versions == (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
    assert report.applied_versions == ()
    assert report.database_size_bytes == 0
    assert report.free_space_bytes > 0
    assert not database.exists()
    assert not database.parent.exists()


def test_migrations_apply_forward_only_schema_and_runtime_pragmas(tmp_path: Path) -> None:
    database = tmp_path / "metadata" / "artifacts.sqlite3"

    report = migrate_artifact_metadata(database, busy_timeout_ms=2_500)

    assert report.applied_versions == (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
    with connect_artifact_metadata(database, busy_timeout_ms=2_500) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        versions = connection.execute(
            "SELECT version, checksum FROM artifact_schema_migrations ORDER BY version"
        ).fetchall()

        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 2_500
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 12
        revision_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(artifact_revisions)")
        }

    assert {
        "artifacts",
        "artifact_revisions",
        "artifact_assets",
        "artifact_links",
        "artifact_operation_dedup",
        "artifact_write_journal",
        "artifact_exports",
        "form_submissions",
        "artifact_mutation_proposals",
        "artifact_evidence_events",
        "artifact_form_continuation_outbox",
    } <= tables
    assert {
        "idx_artifacts_workspace_updated",
        "idx_artifacts_workspace_kind_status",
        "idx_artifact_form_continuation_outbox_status",
        "idx_artifact_revisions_artifact_schema",
    } <= indexes
    assert "schema_version" in revision_columns
    assert [row[0] for row in versions] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    assert all(len(row[1]) == 64 for row in versions)


def test_migrations_are_idempotent_and_dry_run_does_not_touch_existing_db(
    tmp_path: Path,
) -> None:
    database = tmp_path / "artifacts.sqlite3"
    migrate_artifact_metadata(database)
    timestamp_before = database.stat().st_mtime_ns

    dry_run = migrate_artifact_metadata(database, dry_run=True)
    applied_again = migrate_artifact_metadata(database)

    assert dry_run.pending_versions == ()
    assert dry_run.applied_versions == ()
    assert applied_again.applied_versions == ()
    assert database.stat().st_mtime_ns == timestamp_before


def test_migrations_reject_destructive_downgrade_and_unbounded_timeout(
    tmp_path: Path,
) -> None:
    database = tmp_path / "artifacts.sqlite3"
    migrate_artifact_metadata(database)

    with pytest.raises(ArtifactDomainError) as caught:
        migrate_artifact_metadata(database, target_version=2)
    assert caught.value.code is ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT
    assert caught.value.details["classification"] == "destructive_downgrade_denied"

    with pytest.raises(ValueError, match="busy_timeout_ms"):
        connect_artifact_metadata(database, busy_timeout_ms=60_001)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 12


def test_failed_migration_rolls_back_version_and_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "artifacts.sqlite3"
    migrate_artifact_metadata(database)
    broken = ArtifactMigration(
        version=13,
        name="broken_test_migration",
        statements=("CREATE TABLE must_roll_back (id TEXT)", "NOT VALID SQL"),
    )
    monkeypatch.setattr(migrations, "MIGRATIONS", (*migrations.MIGRATIONS, broken))

    with pytest.raises(ArtifactDomainError) as caught:
        migrate_artifact_metadata(database)

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 12
        assert (
            connection.execute(
                        "SELECT COUNT(*) FROM artifact_schema_migrations WHERE version = 13"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name = 'must_roll_back'"
            ).fetchone()[0]
            == 0
        )


def test_existing_v8_database_receives_asset_reservation_expiry_forward_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "artifacts.sqlite3"
    current_migrations = migrations.MIGRATIONS
    legacy_v2 = ArtifactMigration(
        version=2,
        name="indexes_and_dedup",
        statements=tuple(
            statement.replace("\n                expires_at_utc TEXT,", "")
            for statement in current_migrations[1].statements
        ),
    )
    legacy_migrations = (
        current_migrations[0],
        legacy_v2,
        *current_migrations[2:8],
    )
    monkeypatch.setattr(migrations, "MIGRATIONS", legacy_migrations)
    migrate_artifact_metadata(database)

    monkeypatch.setattr(migrations, "MIGRATIONS", current_migrations)
    report = migrate_artifact_metadata(database)

    assert report.current_version == 12
    assert report.target_version == 12
    assert report.applied_versions == (9, 10, 11, 12)
    with sqlite3.connect(database) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(artifact_operation_dedup)")
        }
        assert "expires_at_utc" in columns
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 12


def test_existing_pending_proposals_without_provenance_are_migrated_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "artifacts.sqlite3"
    current_migrations = migrations.MIGRATIONS
    monkeypatch.setattr(migrations, "MIGRATIONS", current_migrations[:9])
    migrate_artifact_metadata(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO artifact_mutation_proposals (
                proposal_id, workspace_id, artifact_id, base_revision_number,
                mutation_type, content_json, content_sha256, idempotency_key,
                summary, proposed_by_id, status, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                "legacy-proposal",
                "workspace-1",
                "artifact-1",
                1,
                "replace_content",
                "{}",
                "a" * 64,
                "legacy-key",
                "legacy pending proposal",
                "assistant-1",
                "2026-07-17T00:00:00+00:00",
            ),
        )
        connection.commit()

    monkeypatch.setattr(migrations, "MIGRATIONS", current_migrations)
    report = migrate_artifact_metadata(database)

    assert report.applied_versions == (10, 11, 12)
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT status, completed_at_utc FROM artifact_mutation_proposals "
            "WHERE proposal_id = 'legacy-proposal'"
        ).fetchone()
    assert row[0] == "stale"
    assert row[1]
