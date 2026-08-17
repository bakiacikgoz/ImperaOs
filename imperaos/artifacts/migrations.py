from __future__ import annotations

import hashlib
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode

MIN_BUSY_TIMEOUT_MS = 100
MAX_BUSY_TIMEOUT_MS = 30_000
DEFAULT_BUSY_TIMEOUT_MS = 5_000


@dataclass(frozen=True, slots=True)
class ArtifactMigration:
    version: int
    name: str
    statements: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.version < 1 or not self.name or not self.statements:
            raise ValueError("migration requires a positive version, name, and statements")

    @property
    def checksum(self) -> str:
        payload = "\n-- statement --\n".join(self.statements).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ArtifactMigrationReport:
    current_version: int
    target_version: int
    pending_versions: tuple[int, ...]
    applied_versions: tuple[int, ...]
    database_exists: bool
    database_size_bytes: int
    free_space_bytes: int
    storage_file_count: int
    table_row_counts: dict[str, int] = field(default_factory=dict)


MIGRATIONS: tuple[ArtifactMigration, ...] = (
    ArtifactMigration(
        version=1,
        name="metadata_schema",
        statements=(
            """
            CREATE TABLE artifact_schema_migrations (
                version INTEGER PRIMARY KEY CHECK (version > 0),
                name TEXT NOT NULL UNIQUE,
                checksum TEXT NOT NULL CHECK (length(checksum) = 64),
                applied_at_utc TEXT NOT NULL
            ) STRICT
            """,
            """
            CREATE TABLE artifacts (
                artifact_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (
                    kind IN ('document', 'form', 'code', 'flow', 'spreadsheet', 'canvas', 'slides')
                ),
                title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
                status TEXT NOT NULL DEFAULT 'draft' CHECK (
                    status IN ('draft', 'active', 'archived', 'blocked', 'corrupt')
                ),
                schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version >= 1),
                data_class TEXT NOT NULL CHECK (
                    data_class IN ('public', 'internal', 'confidential', 'regulated')
                ),
                current_revision_id TEXT NOT NULL,
                current_revision_number INTEGER NOT NULL CHECK (current_revision_number >= 1),
                source_session_id TEXT,
                source_turn_id TEXT,
                created_by_type TEXT NOT NULL CHECK (
                    created_by_type IN ('user', 'assistant', 'system', 'import')
                ),
                created_by_id TEXT NOT NULL,
                updated_by_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                archived_at_utc TEXT,
                etag TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (current_revision_id)
                    REFERENCES artifact_revisions(revision_id)
                    DEFERRABLE INITIALLY DEFERRED
            ) STRICT
            """,
            """
            CREATE TABLE artifact_revisions (
                revision_id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                parent_revision_id TEXT,
                base_revision_id TEXT,
                revision_number INTEGER NOT NULL CHECK (revision_number >= 1),
                mutation_type TEXT NOT NULL,
                content_relpath TEXT NOT NULL,
                content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
                content_size_bytes INTEGER NOT NULL CHECK (content_size_bytes >= 0),
                content_encoding TEXT NOT NULL CHECK (
                    content_encoding IN ('utf-8', 'json', 'binary')
                ),
                change_summary TEXT NOT NULL DEFAULT '',
                author_type TEXT NOT NULL CHECK (
                    author_type IN ('user', 'assistant', 'system', 'import')
                ),
                author_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id) ON DELETE RESTRICT,
                FOREIGN KEY (parent_revision_id)
                    REFERENCES artifact_revisions(revision_id) ON DELETE RESTRICT,
                FOREIGN KEY (base_revision_id)
                    REFERENCES artifact_revisions(revision_id) ON DELETE RESTRICT,
                UNIQUE (artifact_id, revision_number),
                UNIQUE (artifact_id, idempotency_key)
            ) STRICT
            """,
            """
            CREATE TABLE artifact_assets (
                asset_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
                media_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                relative_path TEXT NOT NULL,
                width INTEGER CHECK (width IS NULL OR width > 0),
                height INTEGER CHECK (height IS NULL OR height > 0),
                original_name TEXT,
                data_class TEXT NOT NULL CHECK (
                    data_class IN ('public', 'internal', 'confidential', 'regulated')
                ),
                created_by_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                UNIQUE (workspace_id, sha256)
            ) STRICT
            """,
            """
            CREATE TABLE artifact_links (
                link_id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                link_type TEXT NOT NULL CHECK (
                    link_type IN (
                        'session', 'turn', 'run', 'evidence', 'approval', 'source', 'export'
                    )
                ),
                target_id TEXT NOT NULL,
                created_by_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id) ON DELETE RESTRICT,
                UNIQUE (artifact_id, link_type, target_id)
            ) STRICT
            """,
        ),
    ),
    ArtifactMigration(
        version=2,
        name="indexes_and_dedup",
        statements=(
            """
            CREATE INDEX idx_artifacts_workspace_updated
            ON artifacts (workspace_id, updated_at_utc DESC)
            """,
            """
            CREATE INDEX idx_artifacts_workspace_kind_status
            ON artifacts (workspace_id, kind, status)
            """,
            """
            CREATE INDEX idx_artifact_revisions_artifact_created
            ON artifact_revisions (artifact_id, created_at_utc DESC)
            """,
            """
            CREATE TABLE artifact_operation_dedup (
                workspace_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                operation TEXT NOT NULL,
                request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64),
                result_json TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                PRIMARY KEY (workspace_id, idempotency_key)
            ) STRICT
            """,
            """
            CREATE TABLE artifact_write_journal (
                journal_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                revision_id TEXT NOT NULL UNIQUE,
                content_relpath TEXT NOT NULL,
                content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
                state TEXT NOT NULL CHECK (state IN ('pending', 'committed', 'quarantined')),
                created_at_utc TEXT NOT NULL,
                completed_at_utc TEXT
            ) STRICT
            """,
        ),
    ),
    ArtifactMigration(
        version=3,
        name="exports_and_forms",
        statements=(
            """
            CREATE TABLE artifact_exports (
                export_id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                format TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN ('pending', 'completed', 'cancelled', 'failed')
                ),
                basename TEXT NOT NULL,
                sha256 TEXT CHECK (sha256 IS NULL OR length(sha256) = 64),
                size_bytes INTEGER CHECK (size_bytes IS NULL OR size_bytes >= 0),
                actor_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                completed_at_utc TEXT,
                FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id) ON DELETE RESTRICT,
                FOREIGN KEY (revision_id)
                    REFERENCES artifact_revisions(revision_id) ON DELETE RESTRICT
            ) STRICT
            """,
            """
            CREATE TABLE form_submissions (
                submission_id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                schema_revision_id TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                persistence_policy TEXT NOT NULL CHECK (
                    persistence_policy IN ('none', 'redacted', 'encrypted')
                ),
                redacted_summary_json TEXT NOT NULL DEFAULT '{}',
                response_sha256 TEXT NOT NULL CHECK (length(response_sha256) = 64),
                idempotency_key TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id) ON DELETE RESTRICT,
                FOREIGN KEY (schema_revision_id)
                    REFERENCES artifact_revisions(revision_id) ON DELETE RESTRICT,
                UNIQUE (artifact_id, idempotency_key)
            ) STRICT
            """,
            """
            CREATE TABLE artifact_mutation_proposals (
                proposal_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                base_revision_number INTEGER NOT NULL CHECK (base_revision_number >= 1),
                mutation_type TEXT NOT NULL,
                content_json TEXT NOT NULL,
                content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
                idempotency_key TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                proposed_by_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'applied', 'rejected', 'stale')),
                created_at_utc TEXT NOT NULL,
                applied_revision_id TEXT,
                completed_at_utc TEXT,
                FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id) ON DELETE RESTRICT,
                FOREIGN KEY (applied_revision_id)
                    REFERENCES artifact_revisions(revision_id) ON DELETE RESTRICT,
                UNIQUE (artifact_id, idempotency_key)
            ) STRICT
            """,
        ),
    ),
    ArtifactMigration(
        version=4,
        name="artifact_evidence_chain",
        statements=(
            """
            CREATE TABLE artifact_evidence_events (
                event_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                workspace_id TEXT NOT NULL,
                workspace_ref TEXT NOT NULL CHECK (length(workspace_ref) = 64),
                operation TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('success', 'denied', 'error')),
                reason_code TEXT NOT NULL,
                artifact_ref TEXT CHECK (artifact_ref IS NULL OR length(artifact_ref) = 64),
                revision_ref TEXT CHECK (revision_ref IS NULL OR length(revision_ref) = 64),
                content_sha256 TEXT CHECK (
                    content_sha256 IS NULL OR length(content_sha256) = 64
                ),
                principal_ref TEXT NOT NULL CHECK (length(principal_ref) = 64),
                request_ref TEXT NOT NULL CHECK (length(request_ref) = 64),
                latency_bucket TEXT NOT NULL CHECK (
                    latency_bucket IN ('lt10ms', 'lt50ms', 'lt250ms', 'lt1s', 'gte1s')
                ),
                previous_event_hash TEXT CHECK (
                    previous_event_hash IS NULL OR length(previous_event_hash) = 64
                ),
                event_hash TEXT NOT NULL CHECK (length(event_hash) = 64),
                created_at_utc TEXT NOT NULL
            ) STRICT
            """,
            """
            CREATE INDEX idx_artifact_evidence_workspace_sequence
            ON artifact_evidence_events (workspace_id, event_sequence)
            """,
        ),
    ),
    ArtifactMigration(
        version=5,
        name="form_continuation_outbox",
        statements=(
            """
            CREATE TABLE artifact_form_continuation_outbox (
                submission_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'ticketed', 'failed')),
                approval_id TEXT,
                action_hash TEXT CHECK (action_hash IS NULL OR length(action_hash) = 64),
                last_error_code TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                FOREIGN KEY (submission_id)
                    REFERENCES form_submissions(submission_id) ON DELETE RESTRICT
            ) STRICT
            """,
            """
            CREATE INDEX idx_artifact_form_continuation_outbox_status
            ON artifact_form_continuation_outbox (workspace_id, status, created_at_utc)
            """,
        ),
    ),
    ArtifactMigration(
        version=6,
        name="governed_export_authority",
        statements=(
            "ALTER TABLE artifact_exports ADD COLUMN workspace_id TEXT",
            "ALTER TABLE artifact_exports ADD COLUMN actor_type TEXT",
            "ALTER TABLE artifact_exports ADD COLUMN idempotency_key TEXT",
            "ALTER TABLE artifact_exports ADD COLUMN request_sha256 TEXT",
            "ALTER TABLE artifact_exports ADD COLUMN reason_code TEXT",
            "ALTER TABLE artifact_exports ADD COLUMN terminal_idempotency_key TEXT",
            "ALTER TABLE artifact_exports ADD COLUMN terminal_request_sha256 TEXT",
            "CREATE UNIQUE INDEX idx_artifact_exports_workspace_idempotency ON artifact_exports (workspace_id, idempotency_key)",  # noqa: E501
            "CREATE INDEX idx_artifact_exports_workspace_status ON artifact_exports (workspace_id, status, created_at_utc)",  # noqa: E501
        ),
    ),
    ArtifactMigration(
        version=7,
        name="revision_schema_version",
        statements=(
            "ALTER TABLE artifact_revisions ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version >= 1)",  # noqa: E501
            "CREATE INDEX idx_artifact_revisions_artifact_schema ON artifact_revisions (artifact_id, schema_version, revision_number)",  # noqa: E501
        ),
    ),
    ArtifactMigration(
        version=8,
        name="evidence_source_links",
        statements=(
            """
            CREATE TABLE artifact_links_v8 (
                link_id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                link_type TEXT NOT NULL CHECK (
                    link_type IN (
                        'session', 'turn', 'run', 'evidence', 'approval', 'source',
                        'source_evidence', 'export'
                    )
                ),
                target_id TEXT NOT NULL,
                created_by_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id) ON DELETE RESTRICT,
                UNIQUE (artifact_id, link_type, target_id)
            ) STRICT
            """,
            """
            INSERT INTO artifact_links_v8 (
                link_id, artifact_id, link_type, target_id, created_by_id, created_at_utc
            )
            SELECT link_id, artifact_id, link_type, target_id, created_by_id, created_at_utc
            FROM artifact_links
            """,
            "DROP TABLE artifact_links",
            "ALTER TABLE artifact_links_v8 RENAME TO artifact_links",
        ),
    ),
    ArtifactMigration(
        version=9,
        name="operation_dedup_expiry",
        statements=(
            "ALTER TABLE artifact_operation_dedup ADD COLUMN expires_at_utc TEXT",
        ),
    ),
    ArtifactMigration(
        version=10,
        name="artifact_proposal_provenance",
        statements=(
            "ALTER TABLE artifact_mutation_proposals ADD COLUMN request_sha256 TEXT",
            "ALTER TABLE artifact_mutation_proposals ADD COLUMN context_sha256 TEXT",
            "ALTER TABLE artifact_mutation_proposals ADD COLUMN selection_sha256 TEXT",
            "ALTER TABLE artifact_mutation_proposals ADD COLUMN source_session_id TEXT",
            "ALTER TABLE artifact_mutation_proposals ADD COLUMN source_turn_id TEXT",
            "ALTER TABLE artifact_mutation_proposals ADD COLUMN trace_id TEXT",
            "ALTER TABLE artifact_mutation_proposals ADD COLUMN approval_id TEXT",
            "ALTER TABLE artifact_mutation_proposals ADD COLUMN action_hash TEXT",
            "ALTER TABLE artifact_mutation_proposals ADD COLUMN approved_by_id TEXT",
            "ALTER TABLE artifact_mutation_proposals ADD COLUMN applied_by_id TEXT",
        ),
    ),
    ArtifactMigration(
        version=11,
        name="stale_unverifiable_artifact_proposals",
        statements=(
            """
            UPDATE artifact_mutation_proposals
            SET status = 'stale',
                completed_at_utc = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE status = 'pending'
              AND (
                request_sha256 IS NULL
                OR context_sha256 IS NULL
                OR selection_sha256 IS NULL
                OR length(request_sha256) != 64
                OR length(context_sha256) != 64
                OR length(selection_sha256) != 64
              )
            """,
        ),
    ),
    ArtifactMigration(
        version=12,
        name="bind_artifact_proposal_context_scope",
        statements=(
            "ALTER TABLE artifact_mutation_proposals ADD COLUMN context_revision_id TEXT",
            "ALTER TABLE artifact_mutation_proposals ADD COLUMN context_purpose TEXT",
            "ALTER TABLE artifact_mutation_proposals ADD COLUMN target_scope_json TEXT",
            """
            UPDATE artifact_mutation_proposals
            SET status = 'stale',
                completed_at_utc = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE status = 'pending'
            """,
        ),
    ),
)


_ROW_COUNT_TABLES = (
    "artifacts",
    "artifact_revisions",
    "artifact_assets",
    "artifact_links",
    "artifact_operation_dedup",
    "artifact_exports",
    "form_submissions",
    "artifact_mutation_proposals",
    "artifact_evidence_events",
    "artifact_form_continuation_outbox",
)


def connect_artifact_metadata(
    database: str | Path,
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> sqlite3.Connection:
    _validate_busy_timeout(busy_timeout_ms)
    path = Path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        path,
        timeout=busy_timeout_ms / 1_000,
        isolation_level=None,
    )
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
    connection.row_factory = sqlite3.Row
    return connection


def migrate_artifact_metadata(
    database: str | Path,
    *,
    dry_run: bool = False,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    target_version: int | None = None,
) -> ArtifactMigrationReport:
    _validate_busy_timeout(busy_timeout_ms)
    path = Path(database)
    latest_version = max(migration.version for migration in MIGRATIONS)
    requested_version = latest_version if target_version is None else target_version
    current_version = _read_current_version(path)
    _validate_version_direction(current_version, requested_version, latest_version)
    pending = tuple(
        migration
        for migration in MIGRATIONS
        if current_version < migration.version <= requested_version
    )
    before = _build_report(
        path,
        current_version=current_version,
        target_version=requested_version,
        pending=pending,
        applied=(),
    )
    if dry_run or not pending:
        return before

    connection = connect_artifact_metadata(path, busy_timeout_ms=busy_timeout_ms)
    applied: list[int] = []
    try:
        _verify_applied_checksums(connection, current_version)
        for migration in pending:
            try:
                connection.execute("BEGIN IMMEDIATE")
                for statement in migration.statements:
                    connection.execute(statement)
                connection.execute(
                    """
                    INSERT INTO artifact_schema_migrations (
                        version, name, checksum, applied_at_utc
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        migration.version,
                        migration.name,
                        migration.checksum,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.execute(f"PRAGMA user_version={migration.version}")
                connection.commit()
                applied.append(migration.version)
            except sqlite3.Error as exc:
                connection.rollback()
                _raise_migration_error(exc, migration.version)
    finally:
        connection.close()

    return _build_report(
        path,
        current_version=requested_version,
        target_version=requested_version,
        pending=(),
        applied=tuple(applied),
    )


def _read_current_version(path: Path) -> int:
    if not path.exists():
        return 0
    uri = f"file:{quote(path.resolve().as_posix(), safe='/:')}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            return int(connection.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.Error as exc:
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
            "artifact metadata version could not be read",
            details={"classification": "metadata_open_failed"},
        ) from exc


def _validate_version_direction(current: int, target: int, latest: int) -> None:
    if target < current:
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
            "artifact metadata schema downgrade is not supported",
            details={
                "classification": "destructive_downgrade_denied",
                "currentVersion": current,
                "targetVersion": target,
            },
        )
    if target < 0 or target > latest or current > latest:
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_SCHEMA_VERSION_UNSUPPORTED,
            "artifact metadata schema version is unsupported",
            details={
                "classification": "metadata_version_unsupported",
                "currentVersion": current,
                "targetVersion": target,
                "latestVersion": latest,
            },
        )


def _verify_applied_checksums(connection: sqlite3.Connection, current_version: int) -> None:
    if current_version == 0:
        return
    try:
        rows = connection.execute(
            "SELECT version, checksum FROM artifact_schema_migrations"
        ).fetchall()
    except sqlite3.Error as exc:
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
            "artifact migration history is unavailable",
            details={"classification": "migration_history_missing"},
        ) from exc
    recorded = {int(version): checksum for version, checksum in rows}
    for migration in MIGRATIONS:
        if (
            migration.version <= current_version
            and recorded.get(migration.version) != migration.checksum
        ):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "artifact migration checksum drift detected",
                details={
                    "classification": "migration_checksum_mismatch",
                    "version": migration.version,
                },
            )


def _build_report(
    path: Path,
    *,
    current_version: int,
    target_version: int,
    pending: tuple[ArtifactMigration, ...],
    applied: tuple[int, ...],
) -> ArtifactMigrationReport:
    existing_parent = path.parent
    while not existing_parent.exists() and existing_parent != existing_parent.parent:
        existing_parent = existing_parent.parent
    free_space = shutil.disk_usage(existing_parent).free
    root = path.parent.parent if path.parent.name == "metadata" else path.parent
    storage_file_count = (
        sum(1 for item in root.rglob("*") if item.is_file()) if root.exists() else 0
    )
    return ArtifactMigrationReport(
        current_version=current_version,
        target_version=target_version,
        pending_versions=tuple(migration.version for migration in pending),
        applied_versions=applied,
        database_exists=path.exists(),
        database_size_bytes=path.stat().st_size if path.exists() else 0,
        free_space_bytes=free_space,
        storage_file_count=storage_file_count,
        table_row_counts=_read_row_counts(path),
    )


def _read_row_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    uri = f"file:{quote(path.resolve().as_posix(), safe='/:')}?mode=ro"
    counts: dict[str, int] = {}
    with sqlite3.connect(uri, uri=True) as connection:
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        for table in _ROW_COUNT_TABLES:
            if table in existing:
                counts[table] = int(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
    return counts


def _validate_busy_timeout(busy_timeout_ms: int) -> None:
    if not MIN_BUSY_TIMEOUT_MS <= busy_timeout_ms <= MAX_BUSY_TIMEOUT_MS:
        raise ValueError(
            f"busy_timeout_ms must be between {MIN_BUSY_TIMEOUT_MS} and {MAX_BUSY_TIMEOUT_MS}"
        )


def _raise_migration_error(exc: sqlite3.Error, version: int) -> None:
    if isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower():
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_STORAGE_LOCKED,
            "artifact metadata migration is blocked by a database lock",
            retryable=True,
            details={"classification": "metadata_locked", "version": version},
        ) from exc
    raise ArtifactDomainError(
        ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
        "artifact metadata migration failed and was rolled back",
        details={"classification": "migration_failed", "version": version},
    ) from exc
