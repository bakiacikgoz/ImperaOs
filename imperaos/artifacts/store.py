from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.exports import ArtifactExportRecord, ArtifactExportStatus
from imperaos.artifacts.filesystem import GuardedArtifactFilesystem
from imperaos.artifacts.migrations import (
    DEFAULT_BUSY_TIMEOUT_MS,
    connect_artifact_metadata,
    migrate_artifact_metadata,
)
from imperaos.artifacts.models import (
    ArtifactDescriptor,
    ArtifactMutationType,
    ArtifactRevisionDescriptor,
    can_transition_data_class,
    canonical_json,
)

WriteDisposition = Literal["created", "no_op", "idempotent_replay"]


@dataclass(frozen=True, slots=True)
class RevisionWriteResult:
    artifact: ArtifactDescriptor
    revision: ArtifactRevisionDescriptor
    created: bool
    disposition: WriteDisposition


@dataclass(frozen=True, slots=True)
class StoredRevision:
    descriptor: ArtifactRevisionDescriptor
    content: bytes


@dataclass(frozen=True, slots=True)
class StorageReconciliationReport:
    pending_journals: int
    recovered_commits: int
    quarantined_files: int
    removed_temp_files: int


def revision_content_relpath(
    workspace_id: str,
    artifact_id: str,
    revision_number: int,
    revision_id: str,
    content_encoding: Literal["utf-8", "json", "binary"],
) -> str:
    if revision_number < 1:
        raise ValueError("revision_number must be positive")
    suffix = {"utf-8": "txt", "json": "json", "binary": "bin"}[content_encoding]
    return (
        f"content/{workspace_id}/{artifact_id}/revisions/"
        f"{revision_number:08d}-{revision_id}.{suffix}"
    )


class ArtifactStore:
    def __init__(
        self,
        root: str | Path,
        *,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        self.filesystem = GuardedArtifactFilesystem(root)
        self.database_path = self.filesystem.metadata_root / "artifacts.sqlite3"
        self.busy_timeout_ms = busy_timeout_ms
        migrate_artifact_metadata(
            self.database_path,
            busy_timeout_ms=self.busy_timeout_ms,
        )

    def create_export(
        self,
        *,
        export_id: str,
        workspace_id: str,
        artifact_id: str,
        revision_id: str,
        format_name: str,
        basename: str,
        actor_type: str,
        actor_id: str,
        idempotency_key: str,
        request_sha256: str,
    ) -> tuple[ArtifactExportRecord, bool]:
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                artifact = connection.execute(
                    "SELECT artifact_id FROM artifacts WHERE artifact_id = ? AND workspace_id = ?",
                    (artifact_id, workspace_id),
                ).fetchone()
                revision = connection.execute(
                    "SELECT artifact_id FROM artifact_revisions WHERE revision_id = ?",
                    (revision_id,),
                ).fetchone()
                if artifact is None or revision is None or revision["artifact_id"] != artifact_id:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_NOT_FOUND,
                        "artifact export revision does not exist",
                    )
                existing = connection.execute(
                    "SELECT * FROM artifact_exports WHERE workspace_id = ? AND idempotency_key = ?",
                    (workspace_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    if existing["request_sha256"] != request_sha256:
                        raise ArtifactDomainError(
                            ArtifactErrorCode.IDEMPOTENCY_KEY_REUSE_MISMATCH,
                            "artifact export idempotency key was already used",
                        )
                    connection.commit()
                    return _export_from_row(existing), False
                now = datetime.now(UTC).isoformat()
                connection.execute(
                    """
                    INSERT INTO artifact_exports (
                        export_id, workspace_id, artifact_id, revision_id, format, status,
                        basename, actor_type, actor_id, idempotency_key, request_sha256,
                        created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        export_id, workspace_id, artifact_id, revision_id, format_name,
                        basename, actor_type, actor_id, idempotency_key, request_sha256, now,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM artifact_exports WHERE export_id = ?",
                    (export_id,),
                ).fetchone()
                if row is None:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                        "artifact export record could not be read",
                    )
                connection.commit()
                return _export_from_row(row), True
            except ArtifactDomainError:
                connection.rollback()
                raise
            except sqlite3.Error as exc:
                connection.rollback()
                self._raise_storage_failure(exc, "artifact_export_begin_failed")

    def get_export(self, workspace_id: str, export_id: str) -> ArtifactExportRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM artifact_exports WHERE workspace_id = ? AND export_id = ?",
                (workspace_id, export_id),
            ).fetchone()
        if row is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_NOT_FOUND,
                "artifact export does not exist",
            )
        return _export_from_row(row)

    def transition_export(
        self,
        *,
        workspace_id: str,
        export_id: str,
        actor_type: str,
        actor_id: str,
        status: ArtifactExportStatus,
        basename: str,
        sha256: str | None,
        size_bytes: int | None,
        reason_code: str | None,
        idempotency_key: str,
        request_sha256: str,
    ) -> tuple[ArtifactExportRecord, bool]:
        if status == "pending":
            raise ValueError("artifact export terminal transition is required")
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM artifact_exports WHERE workspace_id = ? AND export_id = ?",
                    (workspace_id, export_id),
                ).fetchone()
                if row is None:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_NOT_FOUND,
                        "artifact export does not exist",
                    )
                if row["actor_type"] != actor_type or row["actor_id"] != actor_id:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
                        "artifact export actor binding does not match",
                    )
                if row["status"] != "pending":
                    if (
                        row["status"] == status
                        and row["terminal_idempotency_key"] == idempotency_key
                        and row["terminal_request_sha256"] == request_sha256
                    ):
                        connection.commit()
                        return _export_from_row(row), False
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_EXPORT_FAILED,
                        "artifact export is already terminal",
                    )
                now = datetime.now(UTC).isoformat()
                connection.execute(
                    """
                    UPDATE artifact_exports
                    SET status = ?, basename = ?, sha256 = ?, size_bytes = ?, reason_code = ?,
                        terminal_idempotency_key = ?, terminal_request_sha256 = ?,
                        completed_at_utc = ?
                    WHERE export_id = ? AND workspace_id = ? AND status = 'pending'
                    """,
                    (
                        status, basename, sha256, size_bytes, reason_code, idempotency_key,
                        request_sha256, now, export_id, workspace_id,
                    ),
                )
                updated = connection.execute(
                    "SELECT * FROM artifact_exports WHERE export_id = ? AND workspace_id = ?",
                    (export_id, workspace_id),
                ).fetchone()
                if updated is None:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                        "artifact export terminal record is missing",
                    )
                connection.commit()
                return _export_from_row(updated), True
            except ArtifactDomainError:
                connection.rollback()
                raise
            except sqlite3.Error as exc:
                connection.rollback()
                self._raise_storage_failure(exc, "artifact_export_transition_failed")

    def preflight_export(
        self,
        *,
        workspace_id: str,
        export_id: str,
        actor_type: str,
        actor_id: str,
        basename: str,
        sha256: str,
        size_bytes: int,
    ) -> tuple[ArtifactExportRecord, bool]:
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM artifact_exports WHERE workspace_id = ? AND export_id = ?",
                    (workspace_id, export_id),
                ).fetchone()
                if row is None:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_NOT_FOUND,
                        "artifact export does not exist",
                    )
                if row["actor_type"] != actor_type or row["actor_id"] != actor_id:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
                        "artifact export actor binding does not match",
                    )
                if row["status"] != "pending" or row["basename"] != basename:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_EXPORT_FAILED,
                        "artifact export is not pending for the authorized basename",
                    )
                if row["sha256"] is not None or row["size_bytes"] is not None:
                    if row["sha256"] == sha256 and row["size_bytes"] == size_bytes:
                        connection.commit()
                        return _export_from_row(row), False
                    raise ArtifactDomainError(
                        ArtifactErrorCode.IDEMPOTENCY_KEY_REUSE_MISMATCH,
                        "artifact export preflight bytes do not match",
                    )
                connection.execute(
                    """
                    UPDATE artifact_exports SET sha256 = ?, size_bytes = ?
                    WHERE workspace_id = ? AND export_id = ? AND status = 'pending'
                    """,
                    (sha256, size_bytes, workspace_id, export_id),
                )
                updated = connection.execute(
                    "SELECT * FROM artifact_exports WHERE workspace_id = ? AND export_id = ?",
                    (workspace_id, export_id),
                ).fetchone()
                if updated is None:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                        "artifact export preflight record is missing",
                    )
                connection.commit()
                return _export_from_row(updated), True
            except ArtifactDomainError:
                connection.rollback()
                raise
            except sqlite3.Error as exc:
                connection.rollback()
                self._raise_storage_failure(exc, "artifact_export_preflight_failed")

    def create_form_submission(
        self,
        *,
        submission_id: str,
        workspace_id: str,
        artifact_id: str,
        schema_revision_id: str,
        principal_id: str,
        persistence_policy: Literal["none"],
        response_sha256: str,
        idempotency_key: str,
        continuation_required: bool = False,
    ) -> bool:
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                artifact = connection.execute(
                    "SELECT artifact_id FROM artifacts WHERE artifact_id = ? AND workspace_id = ?",
                    (artifact_id, workspace_id),
                ).fetchone()
                revision = connection.execute(
                    "SELECT artifact_id FROM artifact_revisions WHERE revision_id = ?",
                    (schema_revision_id,),
                ).fetchone()
                if artifact is None or revision is None or revision["artifact_id"] != artifact_id:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_NOT_FOUND,
                        "form artifact revision does not exist",
                    )
                existing = connection.execute(
                    """
                    SELECT form_submissions.* FROM form_submissions
                    JOIN artifacts ON artifacts.artifact_id = form_submissions.artifact_id
                    WHERE artifacts.workspace_id = ? AND form_submissions.idempotency_key = ?
                    """,
                    (workspace_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    expected = (
                        artifact_id,
                        schema_revision_id,
                        principal_id,
                        persistence_policy,
                        response_sha256,
                    )
                    observed = (
                        existing["artifact_id"],
                        existing["schema_revision_id"],
                        existing["principal_id"],
                        existing["persistence_policy"],
                        existing["response_sha256"],
                    )
                    if observed != expected:
                        raise ArtifactDomainError(
                            ArtifactErrorCode.IDEMPOTENCY_KEY_REUSE_MISMATCH,
                            "form submission idempotency key was already used",
                        )
                    if continuation_required:
                        now = datetime.now(UTC).isoformat()
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO artifact_form_continuation_outbox (
                                submission_id, workspace_id, status, created_at_utc, updated_at_utc
                            ) VALUES (?, ?, 'pending', ?, ?)
                            """,
                            (submission_id, workspace_id, now, now),
                        )
                    connection.commit()
                    return False
                connection.execute(
                    """
                    INSERT INTO form_submissions (
                        submission_id, artifact_id, schema_revision_id, principal_id,
                        persistence_policy, redacted_summary_json, response_sha256,
                        idempotency_key, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, '{}', ?, ?, ?)
                    """,
                    (
                        submission_id,
                        artifact_id,
                        schema_revision_id,
                        principal_id,
                        persistence_policy,
                        response_sha256,
                        idempotency_key,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                if continuation_required:
                    now = datetime.now(UTC).isoformat()
                    connection.execute(
                        """
                        INSERT INTO artifact_form_continuation_outbox (
                            submission_id, workspace_id, status, created_at_utc, updated_at_utc
                        ) VALUES (?, ?, 'pending', ?, ?)
                        """,
                        (submission_id, workspace_id, now, now),
                    )
                connection.commit()
                return True
            except ArtifactDomainError:
                connection.rollback()
                raise
            except sqlite3.Error as exc:
                connection.rollback()
                self._raise_storage_failure(exc, "form_submission_commit_failed")

    def mark_form_continuation_ticketed(
        self,
        *,
        submission_id: str,
        workspace_id: str,
        approval_id: str,
        action_hash: str,
    ) -> None:
        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE artifact_form_continuation_outbox
                SET status = 'ticketed', approval_id = ?, action_hash = ?,
                    last_error_code = NULL, attempt_count = attempt_count + 1,
                    updated_at_utc = ?
                WHERE submission_id = ? AND workspace_id = ?
                """,
                (
                    approval_id,
                    action_hash,
                    datetime.now(UTC).isoformat(),
                    submission_id,
                    workspace_id,
                ),
            ).rowcount
            if updated != 1:
                raise ArtifactDomainError(
                    ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                    "form continuation outbox record is unavailable",
                )

    def mark_form_continuation_failed(
        self,
        *,
        submission_id: str,
        workspace_id: str,
        error_code: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE artifact_form_continuation_outbox
                SET status = 'failed', last_error_code = ?,
                    attempt_count = attempt_count + 1, updated_at_utc = ?
                WHERE submission_id = ? AND workspace_id = ?
                """,
                (error_code[:128], datetime.now(UTC).isoformat(), submission_id, workspace_id),
            )

    def create_artifact(
        self,
        artifact: ArtifactDescriptor,
        revision: ArtifactRevisionDescriptor,
        content: bytes,
        *,
        operation: str | None = None,
        request_hash: str | None = None,
    ) -> RevisionWriteResult:
        self._validate_payload(artifact, revision, content)
        if (
            revision.revision_number != 1
            or revision.parent_revision_id is not None
            or revision.mutation_type is not ArtifactMutationType.CREATE
            or artifact.current_revision_id != revision.revision_id
            or artifact.current_revision_number != 1
        ):
            self._raise_schema_invalid("invalid initial artifact revision contract")
        if operation is not None or request_hash is not None:
            if operation != "create" or request_hash is None or len(request_hash) != 64:
                self._raise_schema_invalid("create operation replay binding is invalid")
            return self._commit_create_operation(
                artifact,
                revision,
                content,
                operation=operation,
                request_hash=request_hash,
            )

        replay = self._find_idempotent_result(
            artifact.workspace_id,
            artifact.artifact_id,
            revision.idempotency_key,
            revision.content_sha256,
        )
        if replay is not None:
            return replay
        if self._artifact_exists(artifact.artifact_id):
            self._raise_conflict("artifact already exists", actual_revision=None)

        self._reserve_journal(artifact, revision)
        self._publish_content(revision, content)
        self._commit_create(artifact, revision)
        return RevisionWriteResult(artifact, revision, True, "created")

    def create_duplicate_artifact(
        self,
        artifact: ArtifactDescriptor,
        revision: ArtifactRevisionDescriptor,
        content: bytes,
        *,
        source_artifact_id: str,
        operation: str,
        request_hash: str,
    ) -> RevisionWriteResult:
        self._validate_payload(artifact, revision, content)
        source = self.get_artifact(artifact.workspace_id, source_artifact_id)
        source_revision = self.get_revision(
            artifact.workspace_id,
            source_artifact_id,
            revision.base_revision_id or "",
        ).descriptor
        self._validate_duplicate_contract(
            source,
            source_revision,
            artifact,
            revision,
        )

        if operation != "duplicate" or len(request_hash) != 64:
            self._raise_schema_invalid("duplicate operation replay binding is invalid")
        return self._commit_duplicate(
            artifact,
            revision,
            content,
            source_artifact_id,
            operation=operation,
            request_hash=request_hash,
        )

    def create_evidence_artifact(
        self,
        artifact: ArtifactDescriptor,
        revision: ArtifactRevisionDescriptor,
        content: bytes,
        *,
        source_evidence_id: str,
        operation: str,
        request_hash: str,
    ) -> RevisionWriteResult:
        self._validate_payload(artifact, revision, content)
        if (
            revision.revision_number != 1
            or revision.parent_revision_id is not None
            or revision.base_revision_id is not None
            or revision.mutation_type is not ArtifactMutationType.IMPORT_EVIDENCE
            or artifact.current_revision_id != revision.revision_id
            or artifact.current_revision_number != 1
            or operation != "import_evidence"
            or not source_evidence_id
            or len(request_hash) != 64
        ):
            self._raise_schema_invalid("invalid evidence import revision contract")
        return self._commit_create_operation(
            artifact,
            revision,
            content,
            operation=operation,
            request_hash=request_hash,
            source_link_type="source_evidence",
            source_target_id=source_evidence_id,
        )

    def append_revision(
        self,
        updated_artifact: ArtifactDescriptor,
        revision: ArtifactRevisionDescriptor,
        content: bytes,
        *,
        expected_revision_number: int,
        operation: str | None = None,
        request_hash: str | None = None,
    ) -> RevisionWriteResult:
        self._validate_payload(updated_artifact, revision, content)
        current = self.get_artifact(
            updated_artifact.workspace_id,
            updated_artifact.artifact_id,
        )
        if operation is not None or request_hash is not None:
            if (
                operation not in {
                    "mutate",
                    "restore",
                    "spreadsheet_cell_patch",
                    "slides_slide_patch",
                }
                or request_hash is None
                or len(request_hash) != 64
            ):
                self._raise_schema_invalid("revision operation replay binding is invalid")
            return self._commit_append_operation(
                updated_artifact,
                revision,
                content,
                expected_revision_number=expected_revision_number,
                operation=operation,
                request_hash=request_hash,
            )
        replay = self._find_idempotent_result(
            updated_artifact.workspace_id,
            updated_artifact.artifact_id,
            revision.idempotency_key,
            revision.content_sha256,
        )
        if replay is not None:
            return replay
        if current.current_revision_number != expected_revision_number:
            self._raise_conflict(
                "artifact revision is stale",
                actual_revision=current.current_revision_number,
                expected_revision=expected_revision_number,
            )

        current_revision = self._get_revision_descriptor(
            current.workspace_id,
            current.artifact_id,
            current.current_revision_id,
        )
        if current_revision.content_sha256 == revision.content_sha256:
            return RevisionWriteResult(current, current_revision, False, "no_op")

        self._validate_append_contract(
            current,
            updated_artifact,
            revision,
            expected_revision_number,
        )
        self._reserve_journal(updated_artifact, revision)
        self._publish_content(revision, content)
        self._commit_append(updated_artifact, revision, expected_revision_number)
        return RevisionWriteResult(updated_artifact, revision, True, "created")

    def restore_revision(
        self,
        updated_artifact: ArtifactDescriptor,
        revision: ArtifactRevisionDescriptor,
        *,
        source_revision_id: str,
        expected_revision_number: int,
        operation: str | None = None,
        request_hash: str | None = None,
    ) -> RevisionWriteResult:
        if (
            revision.mutation_type is not ArtifactMutationType.RESTORE
            or revision.base_revision_id != source_revision_id
        ):
            self._raise_schema_invalid("restore revision must identify its source revision")
        source = self.get_revision(
            updated_artifact.workspace_id,
            updated_artifact.artifact_id,
            source_revision_id,
        )
        return self.append_revision(
            updated_artifact,
            revision,
            source.content,
            expected_revision_number=expected_revision_number,
            operation=operation,
            request_hash=request_hash,
        )

    def get_artifact(self, workspace_id: str, artifact_id: str) -> ArtifactDescriptor:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM artifacts WHERE artifact_id = ? AND workspace_id = ?",
                (artifact_id, workspace_id),
            ).fetchone()
        if row is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_NOT_FOUND,
                "artifact does not exist",
            )
        return _artifact_from_row(row)

    def get_revision(
        self,
        workspace_id: str,
        artifact_id: str,
        revision_id: str,
    ) -> StoredRevision:
        descriptor = self._get_revision_descriptor(workspace_id, artifact_id, revision_id)
        try:
            content = self.filesystem.read_bytes(
                descriptor.content_relpath,
                expected_sha256=descriptor.content_sha256,
            )
        except ArtifactDomainError as exc:
            if exc.code is ArtifactErrorCode.ARTIFACT_HASH_MISMATCH:
                self._mark_artifact_corrupt(artifact_id, revision_id)
            raise
        return StoredRevision(descriptor, content)

    def list_revisions(
        self,
        workspace_id: str,
        artifact_id: str,
    ) -> tuple[ArtifactRevisionDescriptor, ...]:
        self.get_artifact(workspace_id, artifact_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM artifact_revisions
                WHERE artifact_id = ? ORDER BY revision_number DESC
                """,
                (artifact_id,),
            ).fetchall()
        return tuple(_revision_from_row(row) for row in rows)

    def list_artifacts(
        self,
        workspace_id: str,
        *,
        kind: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[ArtifactDescriptor, ...]:
        clauses = ["workspace_id = ?"]
        parameters: list[object] = [workspace_id]
        if kind is not None:
            clauses.append("kind = ?")
            parameters.append(kind)
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status)
        parameters.extend((limit, offset))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM artifacts WHERE {' AND '.join(clauses)}
                ORDER BY updated_at_utc DESC, artifact_id
                LIMIT ? OFFSET ?
                """,
                parameters,
            ).fetchall()
        return tuple(_artifact_from_row(row) for row in rows)

    def update_artifact_metadata(
        self,
        artifact: ArtifactDescriptor,
        *,
        expected_revision_number: int,
    ) -> ArtifactDescriptor:
        if artifact.current_revision_number != expected_revision_number:
            self._raise_conflict(
                "metadata update revision is inconsistent",
                actual_revision=artifact.current_revision_number,
                expected_revision=expected_revision_number,
            )
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                record = _artifact_record(artifact)
                record["expected_revision_number"] = expected_revision_number
                cursor = connection.execute(_ARTIFACT_UPDATE_SQL, record)
                if cursor.rowcount != 1:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_REVISION_CONFLICT,
                        "artifact revision changed during metadata update",
                    )
                connection.commit()
            except ArtifactDomainError:
                connection.rollback()
                raise
            except sqlite3.Error as exc:
                connection.rollback()
                self._raise_storage_failure(exc, "metadata_update_failed")
        return artifact

    def reconcile_storage(self) -> StorageReconciliationReport:
        with self._connect() as connection:
            pending = connection.execute(
                """
                SELECT * FROM artifact_write_journal
                WHERE state = 'pending' ORDER BY created_at_utc
                """
            ).fetchall()
            referenced = {
                row[0]
                for row in connection.execute(
                    "SELECT content_relpath FROM artifact_revisions"
                ).fetchall()
            }

        recovered_commits = 0
        quarantined_files = 0
        for journal in pending:
            if journal["content_relpath"] in referenced:
                self._set_journal_state(journal["journal_id"], "committed")
                recovered_commits += 1
                continue
            candidate = self.filesystem.resolve_relative(journal["content_relpath"])
            if candidate.exists():
                self.filesystem.quarantine(
                    journal["content_relpath"],
                    reason="pending-write-orphan",
                )
                quarantined_files += 1
            self._set_journal_state(journal["journal_id"], "quarantined")

        for candidate in list(self.filesystem.content_root.rglob("*")):
            if not candidate.is_file():
                continue
            relative_path = candidate.relative_to(self.filesystem.root).as_posix()
            if relative_path not in referenced:
                self.filesystem.quarantine(relative_path, reason="unreferenced-content")
                quarantined_files += 1

        removed_temp_files = 0
        for candidate in list(self.filesystem.tmp_root.rglob("*")):
            if candidate.is_file():
                candidate.unlink()
                removed_temp_files += 1
        return StorageReconciliationReport(
            pending_journals=len(pending),
            recovered_commits=recovered_commits,
            quarantined_files=quarantined_files,
            removed_temp_files=removed_temp_files,
        )

    def _connect(self) -> sqlite3.Connection:
        return connect_artifact_metadata(
            self.database_path,
            busy_timeout_ms=self.busy_timeout_ms,
        )

    def _artifact_exists(self, artifact_id: str) -> bool:
        with self._connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM artifacts WHERE artifact_id = ?",
                    (artifact_id,),
                ).fetchone()
                is not None
            )

    def _find_idempotent_result(
        self,
        workspace_id: str,
        artifact_id: str,
        idempotency_key: str,
        content_sha256: str,
    ) -> RevisionWriteResult | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM artifact_revisions
                WHERE artifact_id = ? AND idempotency_key = ?
                """,
                (artifact_id, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        existing = _revision_from_row(row)
        if existing.content_sha256 != content_sha256:
            self._raise_idempotency_mismatch("idempotency key payload mismatch")
        artifact = self.get_artifact(workspace_id, artifact_id)
        return RevisionWriteResult(artifact, existing, False, "idempotent_replay")

    def _get_revision_descriptor(
        self,
        workspace_id: str,
        artifact_id: str,
        revision_id: str,
    ) -> ArtifactRevisionDescriptor:
        self.get_artifact(workspace_id, artifact_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM artifact_revisions
                WHERE artifact_id = ? AND revision_id = ?
                """,
                (artifact_id, revision_id),
            ).fetchone()
        if row is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_NOT_FOUND,
                "artifact revision does not exist",
            )
        return _revision_from_row(row)

    def _reserve_journal(
        self,
        artifact: ArtifactDescriptor,
        revision: ArtifactRevisionDescriptor,
    ) -> None:
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT * FROM artifact_write_journal WHERE revision_id = ?",
                    (revision.revision_id,),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO artifact_write_journal (
                            journal_id, workspace_id, artifact_id, revision_id,
                            content_relpath, content_sha256, state, created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                        """,
                        (
                            revision.revision_id,
                            artifact.workspace_id,
                            artifact.artifact_id,
                            revision.revision_id,
                            revision.content_relpath,
                            revision.content_sha256,
                            datetime.now(UTC).isoformat(),
                        ),
                    )
                elif existing["state"] == "quarantined":
                    expected = (
                        revision.revision_id,
                        artifact.workspace_id,
                        artifact.artifact_id,
                        revision.revision_id,
                        revision.content_relpath,
                        revision.content_sha256,
                    )
                    observed = (
                        existing["journal_id"],
                        existing["workspace_id"],
                        existing["artifact_id"],
                        existing["revision_id"],
                        existing["content_relpath"],
                        existing["content_sha256"],
                    )
                    if observed != expected:
                        self._raise_conflict(
                            "quarantined journal payload mismatch",
                            actual_revision=None,
                        )
                    cursor = connection.execute(
                        """
                        UPDATE artifact_write_journal
                        SET state = 'pending', completed_at_utc = NULL
                        WHERE revision_id = ? AND state = 'quarantined'
                        """,
                        (revision.revision_id,),
                    )
                    if cursor.rowcount != 1:
                        raise ArtifactDomainError(
                            ArtifactErrorCode.ARTIFACT_STORAGE_LOCKED,
                            "artifact recovery reservation changed concurrently",
                            retryable=True,
                        )
                elif existing["state"] == "pending":
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_STORAGE_LOCKED,
                        "artifact revision write is already pending",
                        retryable=True,
                    )
                else:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                        "artifact journal is committed without a revision replay",
                    )
                connection.commit()
            except ArtifactDomainError:
                connection.rollback()
                raise
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise ArtifactDomainError(
                    ArtifactErrorCode.ARTIFACT_REVISION_CONFLICT,
                    "artifact revision journal already exists",
                ) from exc

    def _publish_content(self, revision: ArtifactRevisionDescriptor, content: bytes) -> None:
        target = self.filesystem.resolve_relative(revision.content_relpath)
        if target.exists():
            self.filesystem.read_bytes(
                revision.content_relpath,
                expected_sha256=revision.content_sha256,
            )
            return
        self.filesystem.atomic_write_bytes(
            revision.content_relpath,
            content,
            expected_sha256=revision.content_sha256,
        )

    def _commit_create(
        self,
        artifact: ArtifactDescriptor,
        revision: ArtifactRevisionDescriptor,
    ) -> None:
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(_ARTIFACT_INSERT_SQL, _artifact_record(artifact))
                connection.execute(_REVISION_INSERT_SQL, _revision_record(revision))
                self._commit_journal(connection, revision.revision_id)
                connection.commit()
            except sqlite3.Error as exc:
                connection.rollback()
                self._raise_storage_failure(exc, "create_commit_failed")

    def _commit_create_operation(
        self,
        artifact: ArtifactDescriptor,
        revision: ArtifactRevisionDescriptor,
        content: bytes,
        *,
        operation: str,
        request_hash: str,
        source_link_type: str | None = None,
        source_target_id: str | None = None,
    ) -> RevisionWriteResult:
        if (source_link_type is None) != (source_target_id is None):
            self._raise_schema_invalid("create source link binding is invalid")
        if source_link_type not in {None, "source_evidence"}:
            self._raise_schema_invalid("create source link type is invalid")
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                replay_row = connection.execute(
                    """
                    SELECT * FROM artifact_operation_dedup
                    WHERE workspace_id = ? AND idempotency_key = ?
                    """,
                    (artifact.workspace_id, revision.idempotency_key),
                ).fetchone()
                if replay_row is not None:
                    if (
                        replay_row["operation"] != operation
                        or replay_row["request_sha256"] != request_hash
                    ):
                        self._raise_idempotency_mismatch(
                            "idempotency key payload mismatch"
                        )
                    result = json.loads(replay_row["result_json"])
                    artifact_row = connection.execute(
                        "SELECT * FROM artifacts WHERE artifact_id = ? AND workspace_id = ?",
                        (result["artifactId"], artifact.workspace_id),
                    ).fetchone()
                    revision_row = connection.execute(
                        """
                        SELECT * FROM artifact_revisions
                        WHERE artifact_id = ? AND revision_id = ?
                        """,
                        (result["artifactId"], result["revisionId"]),
                    ).fetchone()
                    if artifact_row is None or revision_row is None:
                        raise ArtifactDomainError(
                            ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                            "create replay metadata is missing or inconsistent",
                        )
                    if source_link_type is not None:
                        link_row = connection.execute(
                            """
                            SELECT target_id FROM artifact_links
                            WHERE artifact_id = ? AND link_type = ?
                            """,
                            (result["artifactId"], source_link_type),
                        ).fetchone()
                        if link_row is None or link_row["target_id"] != source_target_id:
                            raise ArtifactDomainError(
                                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                                "create source link is missing or inconsistent",
                            )
                    connection.commit()
                    return RevisionWriteResult(
                        _artifact_from_row(artifact_row),
                        _revision_from_row(revision_row),
                        False,
                        "idempotent_replay",
                    )
                connection.execute(
                    """
                    INSERT INTO artifact_write_journal (
                        journal_id, workspace_id, artifact_id, revision_id,
                        content_relpath, content_sha256, state, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        revision.revision_id,
                        artifact.workspace_id,
                        artifact.artifact_id,
                        revision.revision_id,
                        revision.content_relpath,
                        revision.content_sha256,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                self._publish_content(revision, content)
                connection.execute(_ARTIFACT_INSERT_SQL, _artifact_record(artifact))
                connection.execute(_REVISION_INSERT_SQL, _revision_record(revision))
                if source_link_type is not None and source_target_id is not None:
                    connection.execute(
                        _GENERIC_LINK_INSERT_SQL,
                        {
                            "link_id": self._link_id(
                                artifact.artifact_id,
                                source_link_type,
                                source_target_id,
                            ),
                            "artifact_id": artifact.artifact_id,
                            "link_type": source_link_type,
                            "target_id": source_target_id,
                            "created_by_id": artifact.created_by_id,
                            "created_at_utc": artifact.created_at_utc.isoformat(),
                        },
                    )
                self._commit_journal(connection, revision.revision_id)
                connection.execute(
                    """
                    INSERT INTO artifact_operation_dedup (
                        workspace_id, idempotency_key, operation, request_sha256,
                        result_json, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact.workspace_id,
                        revision.idempotency_key,
                        operation,
                        request_hash,
                        canonical_json(
                            {
                                "artifactId": artifact.artifact_id,
                                "revisionId": revision.revision_id,
                            }
                        ),
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.commit()
                return RevisionWriteResult(artifact, revision, True, "created")
            except ArtifactDomainError:
                connection.rollback()
                raise
            except sqlite3.Error as exc:
                connection.rollback()
                self._raise_storage_failure(exc, "create_commit_failed")

    def _commit_duplicate(
        self,
        artifact: ArtifactDescriptor,
        revision: ArtifactRevisionDescriptor,
        content: bytes,
        source_artifact_id: str,
        *,
        operation: str,
        request_hash: str,
    ) -> RevisionWriteResult:
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                replay_row = connection.execute(
                    """
                    SELECT * FROM artifact_operation_dedup
                    WHERE workspace_id = ? AND idempotency_key = ?
                    """,
                    (artifact.workspace_id, revision.idempotency_key),
                ).fetchone()
                if replay_row is not None:
                    if (
                        replay_row["operation"] != operation
                        or replay_row["request_sha256"] != request_hash
                    ):
                        self._raise_idempotency_mismatch(
                            "idempotency key payload mismatch"
                        )
                    result = json.loads(replay_row["result_json"])
                    artifact_row = connection.execute(
                        "SELECT * FROM artifacts WHERE artifact_id = ? AND workspace_id = ?",
                        (result["artifactId"], artifact.workspace_id),
                    ).fetchone()
                    revision_row = connection.execute(
                        """
                        SELECT * FROM artifact_revisions
                        WHERE artifact_id = ? AND revision_id = ?
                        """,
                        (result["artifactId"], result["revisionId"]),
                    ).fetchone()
                    link_row = connection.execute(
                        """
                        SELECT target_id FROM artifact_links
                        WHERE artifact_id = ? AND link_type = 'source'
                        """,
                        (result["artifactId"],),
                    ).fetchone()
                    if (
                        artifact_row is None
                        or revision_row is None
                        or link_row is None
                        or link_row["target_id"] != source_artifact_id
                    ):
                        raise ArtifactDomainError(
                            ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                            "duplicate replay metadata is missing or inconsistent",
                        )
                    connection.commit()
                    return RevisionWriteResult(
                        _artifact_from_row(artifact_row),
                        _revision_from_row(revision_row),
                        False,
                        "idempotent_replay",
                    )
                source_row = connection.execute(
                    "SELECT workspace_id FROM artifacts WHERE artifact_id = ?",
                    (source_artifact_id,),
                ).fetchone()
                base_row = connection.execute(
                    "SELECT artifact_id FROM artifact_revisions WHERE revision_id = ?",
                    (revision.base_revision_id,),
                ).fetchone()
                if (
                    source_row is None
                    or source_row["workspace_id"] != artifact.workspace_id
                    or base_row is None
                    or base_row["artifact_id"] != source_artifact_id
                ):
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_REVISION_CONFLICT,
                        "duplicate source changed before commit",
                    )
                connection.execute(
                    """
                    INSERT INTO artifact_write_journal (
                        journal_id, workspace_id, artifact_id, revision_id,
                        content_relpath, content_sha256, state, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        revision.revision_id,
                        artifact.workspace_id,
                        artifact.artifact_id,
                        revision.revision_id,
                        revision.content_relpath,
                        revision.content_sha256,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                self._publish_content(revision, content)
                connection.execute(_ARTIFACT_INSERT_SQL, _artifact_record(artifact))
                connection.execute(_REVISION_INSERT_SQL, _revision_record(revision))
                connection.execute(
                    _SOURCE_LINK_INSERT_SQL,
                    {
                        "link_id": self._source_link_id(
                            artifact.artifact_id,
                            source_artifact_id,
                        ),
                        "artifact_id": artifact.artifact_id,
                        "source_artifact_id": source_artifact_id,
                        "created_by_id": artifact.created_by_id,
                        "created_at_utc": artifact.created_at_utc.isoformat(),
                    },
                )
                self._commit_journal(connection, revision.revision_id)
                connection.execute(
                    """
                    INSERT INTO artifact_operation_dedup (
                        workspace_id, idempotency_key, operation, request_sha256,
                        result_json, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact.workspace_id,
                        revision.idempotency_key,
                        operation,
                        request_hash,
                        canonical_json(
                            {
                                "artifactId": artifact.artifact_id,
                                "revisionId": revision.revision_id,
                            }
                        ),
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.commit()
                return RevisionWriteResult(artifact, revision, True, "created")
            except ArtifactDomainError:
                connection.rollback()
                raise
            except sqlite3.Error as exc:
                connection.rollback()
                self._raise_storage_failure(exc, "duplicate_commit_failed")

    def _commit_append(
        self,
        artifact: ArtifactDescriptor,
        revision: ArtifactRevisionDescriptor,
        expected_revision_number: int,
    ) -> None:
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(_REVISION_INSERT_SQL, _revision_record(revision))
                record = _artifact_record(artifact)
                record["expected_revision_number"] = expected_revision_number
                cursor = connection.execute(_ARTIFACT_UPDATE_SQL, record)
                if cursor.rowcount != 1:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_REVISION_CONFLICT,
                        "artifact revision changed during commit",
                    )
                self._commit_journal(connection, revision.revision_id)
                connection.commit()
            except ArtifactDomainError:
                connection.rollback()
                raise
            except sqlite3.Error as exc:
                connection.rollback()
                self._raise_storage_failure(exc, "revision_commit_failed")

    def _commit_append_operation(
        self,
        artifact: ArtifactDescriptor,
        revision: ArtifactRevisionDescriptor,
        content: bytes,
        *,
        expected_revision_number: int,
        operation: str,
        request_hash: str,
    ) -> RevisionWriteResult:
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                replay_row = connection.execute(
                    """
                    SELECT * FROM artifact_operation_dedup
                    WHERE workspace_id = ? AND idempotency_key = ?
                    """,
                    (artifact.workspace_id, revision.idempotency_key),
                ).fetchone()
                if replay_row is not None:
                    if (
                        replay_row["operation"] != operation
                        or replay_row["request_sha256"] != request_hash
                    ):
                        self._raise_idempotency_mismatch(
                            "idempotency key payload mismatch"
                        )
                    result = json.loads(replay_row["result_json"])
                    artifact_row = connection.execute(
                        "SELECT * FROM artifacts WHERE artifact_id = ? AND workspace_id = ?",
                        (result["artifactId"], artifact.workspace_id),
                    ).fetchone()
                    revision_row = connection.execute(
                        """
                        SELECT * FROM artifact_revisions
                        WHERE artifact_id = ? AND revision_id = ?
                        """,
                        (result["artifactId"], result["revisionId"]),
                    ).fetchone()
                    if artifact_row is None or revision_row is None:
                        raise ArtifactDomainError(
                            ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                            "revision replay metadata is missing or inconsistent",
                        )
                    connection.commit()
                    return RevisionWriteResult(
                        _artifact_from_row(artifact_row),
                        _revision_from_row(revision_row),
                        False,
                        "idempotent_replay",
                    )
                current_row = connection.execute(
                    "SELECT * FROM artifacts WHERE artifact_id = ? AND workspace_id = ?",
                    (artifact.artifact_id, artifact.workspace_id),
                ).fetchone()
                if current_row is None:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_NOT_FOUND,
                        "artifact does not exist",
                    )
                current = _artifact_from_row(current_row)
                if current.current_revision_number != expected_revision_number:
                    self._raise_conflict(
                        "artifact revision is stale",
                        actual_revision=current.current_revision_number,
                        expected_revision=expected_revision_number,
                    )
                current_revision_row = connection.execute(
                    """
                    SELECT * FROM artifact_revisions
                    WHERE artifact_id = ? AND revision_id = ?
                    """,
                    (current.artifact_id, current.current_revision_id),
                ).fetchone()
                if current_revision_row is None:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                        "current artifact revision metadata is missing",
                    )
                current_revision = _revision_from_row(current_revision_row)
                if current_revision.content_sha256 == revision.content_sha256:
                    connection.execute(
                        _OPERATION_DEDUP_INSERT_SQL,
                        (
                            artifact.workspace_id,
                            revision.idempotency_key,
                            operation,
                            request_hash,
                            canonical_json(
                                {
                                    "artifactId": current.artifact_id,
                                    "revisionId": current_revision.revision_id,
                                }
                            ),
                            datetime.now(UTC).isoformat(),
                        ),
                    )
                    connection.commit()
                    return RevisionWriteResult(
                        current,
                        current_revision,
                        False,
                        "no_op",
                    )
                self._validate_append_contract(
                    current,
                    artifact,
                    revision,
                    expected_revision_number,
                )
                connection.execute(
                    """
                    INSERT INTO artifact_write_journal (
                        journal_id, workspace_id, artifact_id, revision_id,
                        content_relpath, content_sha256, state, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        revision.revision_id,
                        artifact.workspace_id,
                        artifact.artifact_id,
                        revision.revision_id,
                        revision.content_relpath,
                        revision.content_sha256,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                self._publish_content(revision, content)
                connection.execute(_REVISION_INSERT_SQL, _revision_record(revision))
                record = _artifact_record(artifact)
                record["expected_revision_number"] = expected_revision_number
                cursor = connection.execute(_ARTIFACT_UPDATE_SQL, record)
                if cursor.rowcount != 1:
                    self._raise_conflict(
                        "artifact revision changed during commit",
                        actual_revision=None,
                        expected_revision=expected_revision_number,
                    )
                self._commit_journal(connection, revision.revision_id)
                connection.execute(
                    _OPERATION_DEDUP_INSERT_SQL,
                    (
                        artifact.workspace_id,
                        revision.idempotency_key,
                        operation,
                        request_hash,
                        canonical_json(
                            {
                                "artifactId": artifact.artifact_id,
                                "revisionId": revision.revision_id,
                            }
                        ),
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.commit()
                return RevisionWriteResult(artifact, revision, True, "created")
            except ArtifactDomainError:
                connection.rollback()
                raise
            except sqlite3.Error as exc:
                connection.rollback()
                self._raise_storage_failure(exc, "revision_commit_failed")

    @staticmethod
    def _commit_journal(connection: sqlite3.Connection, revision_id: str) -> None:
        cursor = connection.execute(
            """
            UPDATE artifact_write_journal
            SET state = 'committed', completed_at_utc = ?
            WHERE revision_id = ? AND state = 'pending'
            """,
            (datetime.now(UTC).isoformat(), revision_id),
        )
        if cursor.rowcount != 1:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "artifact write journal is not pending",
            )

    def _set_journal_state(self, journal_id: str, state: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE artifact_write_journal
                SET state = ?, completed_at_utc = ? WHERE journal_id = ?
                """,
                (state, datetime.now(UTC).isoformat(), journal_id),
            )
            connection.commit()

    def _mark_artifact_corrupt(self, artifact_id: str, revision_id: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE artifacts
                SET status = 'corrupt', updated_at_utc = ?, etag = ?
                WHERE artifact_id = ?
                """,
                (
                    datetime.now(UTC).isoformat(),
                    f"corrupt-{revision_id}",
                    artifact_id,
                ),
            )
            connection.commit()

    @staticmethod
    def _validate_payload(
        artifact: ArtifactDescriptor,
        revision: ArtifactRevisionDescriptor,
        content: bytes,
    ) -> None:
        digest = hashlib.sha256(content).hexdigest()
        expected_path = revision_content_relpath(
            artifact.workspace_id,
            artifact.artifact_id,
            revision.revision_number,
            revision.revision_id,
            revision.content_encoding,
        )
        if (
            revision.artifact_id != artifact.artifact_id
            or revision.content_relpath != expected_path
        ):
            ArtifactStore._raise_schema_invalid("revision identity or content path is invalid")
        if revision.content_sha256 != digest or revision.content_size_bytes != len(content):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_HASH_MISMATCH,
                "revision payload hash or size does not match its descriptor",
            )

    @staticmethod
    def _validate_append_contract(
        current: ArtifactDescriptor,
        updated: ArtifactDescriptor,
        revision: ArtifactRevisionDescriptor,
        expected_revision_number: int,
    ) -> None:
        if (
            updated.workspace_id != current.workspace_id
            or updated.artifact_id != current.artifact_id
            or updated.created_at_utc != current.created_at_utc
            or updated.created_by_id != current.created_by_id
            or revision.revision_number != expected_revision_number + 1
            or revision.parent_revision_id != current.current_revision_id
            or updated.current_revision_id != revision.revision_id
            or updated.current_revision_number != revision.revision_number
        ):
            ArtifactStore._raise_schema_invalid("revision update contract is inconsistent")

    @staticmethod
    def _validate_duplicate_contract(
        source: ArtifactDescriptor,
        source_revision: ArtifactRevisionDescriptor,
        target: ArtifactDescriptor,
        revision: ArtifactRevisionDescriptor,
    ) -> None:
        if (
            target.artifact_id == source.artifact_id
            or target.workspace_id != source.workspace_id
            or target.kind is not source.kind
            or target.schema_version != source.schema_version
            or not can_transition_data_class(source.data_class, target.data_class)
            or revision.revision_number != 1
            or revision.parent_revision_id is not None
            or revision.mutation_type is not ArtifactMutationType.DUPLICATE
            or revision.base_revision_id != source_revision.revision_id
            or target.current_revision_id != revision.revision_id
            or target.current_revision_number != 1
        ):
            ArtifactStore._raise_schema_invalid("invalid duplicate artifact revision contract")

    def _validate_duplicate_replay(
        self,
        *,
        expected_artifact: ArtifactDescriptor,
        expected_revision: ArtifactRevisionDescriptor,
        existing: RevisionWriteResult,
        source_artifact_id: str,
    ) -> None:
        artifact = existing.artifact
        revision = existing.revision
        if (
            artifact.workspace_id != expected_artifact.workspace_id
            or artifact.kind is not expected_artifact.kind
            or artifact.title != expected_artifact.title
            or artifact.schema_version != expected_artifact.schema_version
            or artifact.data_class is not expected_artifact.data_class
            or artifact.source_session_id != expected_artifact.source_session_id
            or artifact.source_turn_id != expected_artifact.source_turn_id
            or artifact.metadata != expected_artifact.metadata
            or revision.mutation_type is not ArtifactMutationType.DUPLICATE
            or revision.base_revision_id != expected_revision.base_revision_id
            or revision.author_type is not expected_revision.author_type
            or revision.author_id != expected_revision.author_id
        ):
            self._raise_idempotency_mismatch("idempotency key payload mismatch")
        with self._connect() as connection:
            link = connection.execute(
                """
                SELECT target_id FROM artifact_links
                WHERE artifact_id = ? AND link_type = 'source'
                """,
                (artifact.artifact_id,),
            ).fetchone()
        if link is None or link["target_id"] != source_artifact_id:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "duplicate source link is missing or inconsistent",
            )

    @staticmethod
    def _source_link_id(artifact_id: str, source_artifact_id: str) -> str:
        return ArtifactStore._link_id(artifact_id, "source", source_artifact_id)

    @staticmethod
    def _link_id(artifact_id: str, link_type: str, target_id: str) -> str:
        digest = hashlib.sha256(
            f"{artifact_id}\x1f{link_type}\x1f{target_id}".encode()
        ).hexdigest()[:32]
        return f"link-{digest}"

    @staticmethod
    def _raise_schema_invalid(message: str) -> None:
        raise ArtifactDomainError(ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID, message)

    @staticmethod
    def _raise_conflict(
        message: str,
        *,
        actual_revision: int | None,
        expected_revision: int | None = None,
    ) -> None:
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_REVISION_CONFLICT,
            message,
            details={
                "actualRevision": actual_revision,
                "expectedRevision": expected_revision,
            },
        )

    @staticmethod
    def _raise_idempotency_mismatch(message: str) -> None:
        raise ArtifactDomainError(
            ArtifactErrorCode.IDEMPOTENCY_KEY_REUSE_MISMATCH,
            message,
        )

    @staticmethod
    def _raise_storage_failure(exc: sqlite3.Error, classification: str) -> None:
        if isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower():
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_LOCKED,
                "artifact metadata is temporarily locked",
                retryable=True,
                details={"classification": "storage_locked"},
            ) from exc
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
            "artifact metadata commit failed",
            details={"classification": classification},
        ) from exc


_ARTIFACT_INSERT_SQL = """
INSERT INTO artifacts (
    artifact_id, workspace_id, kind, title, status, schema_version, data_class,
    current_revision_id, current_revision_number, source_session_id, source_turn_id,
    created_by_type, created_by_id, updated_by_id, created_at_utc, updated_at_utc,
    archived_at_utc, etag, metadata_json
) VALUES (
    :artifact_id, :workspace_id, :kind, :title, :status, :schema_version, :data_class,
    :current_revision_id, :current_revision_number, :source_session_id, :source_turn_id,
    :created_by_type, :created_by_id, :updated_by_id, :created_at_utc, :updated_at_utc,
    :archived_at_utc, :etag, :metadata_json
)
"""

_OPERATION_DEDUP_INSERT_SQL = """
INSERT INTO artifact_operation_dedup (
    workspace_id, idempotency_key, operation, request_sha256,
    result_json, created_at_utc
) VALUES (?, ?, ?, ?, ?, ?)
"""

_ARTIFACT_UPDATE_SQL = """
UPDATE artifacts SET
    kind = :kind,
    title = :title,
    status = :status,
    schema_version = :schema_version,
    data_class = :data_class,
    current_revision_id = :current_revision_id,
    current_revision_number = :current_revision_number,
    source_session_id = :source_session_id,
    source_turn_id = :source_turn_id,
    updated_by_id = :updated_by_id,
    updated_at_utc = :updated_at_utc,
    archived_at_utc = :archived_at_utc,
    etag = :etag,
    metadata_json = :metadata_json
WHERE artifact_id = :artifact_id
  AND workspace_id = :workspace_id
  AND current_revision_number = :expected_revision_number
"""

_REVISION_INSERT_SQL = """
INSERT INTO artifact_revisions (
    revision_id, artifact_id, parent_revision_id, base_revision_id, revision_number,
    schema_version, mutation_type, content_relpath, content_sha256,
    content_size_bytes, content_encoding,
    change_summary, author_type, author_id, idempotency_key, created_at_utc
) VALUES (
    :revision_id, :artifact_id, :parent_revision_id, :base_revision_id, :revision_number,
    :schema_version, :mutation_type, :content_relpath, :content_sha256,
    :content_size_bytes, :content_encoding,
    :change_summary, :author_type, :author_id, :idempotency_key, :created_at_utc
)
"""

_SOURCE_LINK_INSERT_SQL = """
INSERT INTO artifact_links (
    link_id, artifact_id, link_type, target_id, created_by_id, created_at_utc
) VALUES (
    :link_id, :artifact_id, 'source', :source_artifact_id,
    :created_by_id, :created_at_utc
)
"""

_GENERIC_LINK_INSERT_SQL = """
INSERT INTO artifact_links (
    link_id, artifact_id, link_type, target_id, created_by_id, created_at_utc
) VALUES (
    :link_id, :artifact_id, :link_type, :target_id, :created_by_id, :created_at_utc
)
"""


def _artifact_record(artifact: ArtifactDescriptor) -> dict[str, object]:
    return {
        "artifact_id": artifact.artifact_id,
        "workspace_id": artifact.workspace_id,
        "kind": artifact.kind.value,
        "title": artifact.title,
        "status": artifact.status.value,
        "schema_version": artifact.schema_version,
        "data_class": artifact.data_class.value,
        "current_revision_id": artifact.current_revision_id,
        "current_revision_number": artifact.current_revision_number,
        "source_session_id": artifact.source_session_id,
        "source_turn_id": artifact.source_turn_id,
        "created_by_type": artifact.created_by_type.value,
        "created_by_id": artifact.created_by_id,
        "updated_by_id": artifact.updated_by_id,
        "created_at_utc": artifact.created_at_utc.isoformat(),
        "updated_at_utc": artifact.updated_at_utc.isoformat(),
        "archived_at_utc": artifact.archived_at_utc.isoformat()
        if artifact.archived_at_utc
        else None,
        "etag": artifact.etag,
        "metadata_json": canonical_json(artifact.metadata),
    }


def _revision_record(revision: ArtifactRevisionDescriptor) -> dict[str, object]:
    return {
        "revision_id": revision.revision_id,
        "artifact_id": revision.artifact_id,
        "parent_revision_id": revision.parent_revision_id,
        "base_revision_id": revision.base_revision_id,
        "revision_number": revision.revision_number,
        "schema_version": revision.schema_version,
        "mutation_type": revision.mutation_type.value,
        "content_relpath": revision.content_relpath,
        "content_sha256": revision.content_sha256,
        "content_size_bytes": revision.content_size_bytes,
        "content_encoding": revision.content_encoding,
        "change_summary": revision.change_summary,
        "author_type": revision.author_type.value,
        "author_id": revision.author_id,
        "idempotency_key": revision.idempotency_key,
        "created_at_utc": revision.created_at_utc.isoformat(),
    }


def _artifact_from_row(row: sqlite3.Row) -> ArtifactDescriptor:
    return ArtifactDescriptor(
        artifact_id=row["artifact_id"],
        workspace_id=row["workspace_id"],
        kind=row["kind"],
        title=row["title"],
        status=row["status"],
        schema_version=row["schema_version"],
        data_class=row["data_class"],
        current_revision_id=row["current_revision_id"],
        current_revision_number=row["current_revision_number"],
        source_session_id=row["source_session_id"],
        source_turn_id=row["source_turn_id"],
        created_by_type=row["created_by_type"],
        created_by_id=row["created_by_id"],
        updated_by_id=row["updated_by_id"],
        created_at_utc=datetime.fromisoformat(row["created_at_utc"]),
        updated_at_utc=datetime.fromisoformat(row["updated_at_utc"]),
        archived_at_utc=datetime.fromisoformat(row["archived_at_utc"])
        if row["archived_at_utc"]
        else None,
        etag=row["etag"],
        metadata=json.loads(row["metadata_json"]),
    )


def _revision_from_row(row: sqlite3.Row) -> ArtifactRevisionDescriptor:
    return ArtifactRevisionDescriptor(
        revision_id=row["revision_id"],
        artifact_id=row["artifact_id"],
        parent_revision_id=row["parent_revision_id"],
        base_revision_id=row["base_revision_id"],
        revision_number=row["revision_number"],
        schema_version=row["schema_version"],
        mutation_type=row["mutation_type"],
        content_relpath=row["content_relpath"],
        content_sha256=row["content_sha256"],
        content_size_bytes=row["content_size_bytes"],
        content_encoding=row["content_encoding"],
        change_summary=row["change_summary"],
        author_type=row["author_type"],
        author_id=row["author_id"],
        idempotency_key=row["idempotency_key"],
        created_at_utc=datetime.fromisoformat(row["created_at_utc"]),
    )


def _export_from_row(row: sqlite3.Row) -> ArtifactExportRecord:
    return ArtifactExportRecord(
        export_id=row["export_id"],
        workspace_id=row["workspace_id"],
        artifact_id=row["artifact_id"],
        revision_id=row["revision_id"],
        format=row["format"],
        status=row["status"],
        basename=row["basename"],
        sha256=row["sha256"],
        size_bytes=row["size_bytes"],
        actor_type=row["actor_type"],
        actor_id=row["actor_id"],
        reason_code=row["reason_code"],
    )
