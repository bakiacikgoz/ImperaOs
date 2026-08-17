from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, ParamSpec, TypeVar, cast

from pydantic import Field

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.migrations import (
    DEFAULT_BUSY_TIMEOUT_MS,
    connect_artifact_metadata,
)
from imperaos.artifacts.models import ArtifactModel, OperationContext, canonical_json
from imperaos.artifacts.operations import safe_artifact_log_event

P = ParamSpec("P")
R = TypeVar("R")
EvidenceStatus = Literal["success", "denied", "error"]


class ArtifactEvidenceEvent(ArtifactModel):
    event_sequence: int = Field(ge=1)
    event_id: str
    workspace_ref: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation: str = Field(min_length=1, max_length=100)
    status: EvidenceStatus
    reason_code: str = Field(min_length=1, max_length=100)
    artifact_ref: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    revision_ref: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    principal_ref: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_ref: str = Field(pattern=r"^[0-9a-f]{64}$")
    latency_bucket: Literal["lt10ms", "lt50ms", "lt250ms", "lt1s", "gte1s"]
    previous_event_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at_utc: datetime


class ArtifactEvidenceRecorder:
    """Append-only, hash-chained artifact metadata recorder with safe bundle output."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        self.database_path = Path(database_path)
        self.busy_timeout_ms = busy_timeout_ms

    def record(
        self,
        *,
        operation: str,
        context: OperationContext,
        status: EvidenceStatus,
        reason_code: str,
        latency_ms: float,
        artifact_id: str | None = None,
        revision_id: str | None = None,
        content_sha256: str | None = None,
    ) -> ArtifactEvidenceEvent:
        event_id = "event-" + _ref(
            "event",
            context.workspace_id,
            context.request_id,
            operation,
            artifact_id or "none",
            revision_id or "none",
            status,
            reason_code,
        )[:32]
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT * FROM artifact_evidence_events WHERE event_id = ?",
                    (event_id,),
                ).fetchone()
                if existing is not None:
                    connection.commit()
                    return _event_from_row(existing)
                previous = connection.execute(
                    """
                    SELECT event_hash FROM artifact_evidence_events
                    WHERE workspace_id = ? ORDER BY event_sequence DESC LIMIT 1
                    """,
                    (context.workspace_id,),
                ).fetchone()
                previous_hash = previous["event_hash"] if previous is not None else None
                created_at = datetime.now(UTC)
                created_at_json = created_at.isoformat().replace("+00:00", "Z")
                safe_payload: dict[str, Any] = {
                    "eventId": event_id,
                    "workspaceRef": _ref("workspace", context.workspace_id),
                    "operation": operation,
                    "status": status,
                    "reasonCode": reason_code,
                    "artifactRef": _optional_ref("artifact", artifact_id),
                    "revisionRef": _optional_ref("revision", revision_id),
                    "contentSha256": content_sha256,
                    "principalRef": _ref(
                        "principal", context.principal_type.value, context.principal_id
                    ),
                    "requestRef": _ref("request", context.request_id),
                    "latencyBucket": _latency_bucket(latency_ms),
                    "previousEventHash": previous_hash,
                    "createdAtUtc": created_at_json,
                }
                event_hash = hashlib.sha256(
                    canonical_json(safe_payload).encode("utf-8")
                ).hexdigest()
                cursor = connection.execute(
                    """
                    INSERT INTO artifact_evidence_events (
                        event_id, workspace_id, workspace_ref, operation, status,
                        reason_code, artifact_ref, revision_ref, content_sha256,
                        principal_ref, request_ref, latency_bucket, previous_event_hash,
                        event_hash, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        context.workspace_id,
                        safe_payload["workspaceRef"],
                        operation,
                        status,
                        reason_code,
                        safe_payload["artifactRef"],
                        safe_payload["revisionRef"],
                        content_sha256,
                        safe_payload["principalRef"],
                        safe_payload["requestRef"],
                        safe_payload["latencyBucket"],
                        previous_hash,
                        event_hash,
                        created_at.isoformat(),
                    ),
                )
                sequence = cast(int, cursor.lastrowid)
                connection.commit()
            except sqlite3.Error as exc:
                connection.rollback()
                raise ArtifactDomainError(
                    ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                    "artifact evidence could not be committed",
                    details={"classification": "evidence_commit_failed"},
                ) from exc
        return ArtifactEvidenceEvent(
            event_sequence=sequence,
            event_hash=event_hash,
            event_id=event_id,
            workspace_ref=cast(str, safe_payload["workspaceRef"]),
            operation=operation,
            status=status,
            reason_code=reason_code,
            artifact_ref=cast(str | None, safe_payload["artifactRef"]),
            revision_ref=cast(str | None, safe_payload["revisionRef"]),
            content_sha256=content_sha256,
            principal_ref=cast(str, safe_payload["principalRef"]),
            request_ref=cast(str, safe_payload["requestRef"]),
            latency_bucket=cast(Any, safe_payload["latencyBucket"]),
            previous_event_hash=previous_hash,
            created_at_utc=created_at,
        )

    def list_events(self, workspace_id: str) -> tuple[ArtifactEvidenceEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM artifact_evidence_events
                WHERE workspace_id = ? ORDER BY event_sequence
                """,
                (workspace_id,),
            ).fetchall()
        return tuple(_event_from_row(row) for row in rows)

    def verify_chain(self, workspace_id: str) -> bool:
        previous_hash: str | None = None
        for event in self.list_events(workspace_id):
            if event.previous_event_hash != previous_hash:
                return False
            safe_payload = event.model_dump(
                mode="json",
                by_alias=True,
                exclude={"event_sequence", "event_hash"},
            )
            observed = hashlib.sha256(
                canonical_json(safe_payload).encode("utf-8")
            ).hexdigest()
            if observed != event.event_hash:
                return False
            previous_hash = event.event_hash
        return True

    def support_bundle_snapshot(self, workspace_id: str) -> dict[str, Any]:
        events = self.list_events(workspace_id)
        return {
            "schemaVersion": "artifact-evidence-support/v1",
            "workspaceRef": _ref("workspace", workspace_id),
            "chainVerified": self.verify_chain(workspace_id),
            "eventCount": len(events),
            "events": [event.model_dump(mode="json", by_alias=True) for event in events],
        }

    def _connect(self) -> sqlite3.Connection:
        return connect_artifact_metadata(
            self.database_path,
            busy_timeout_ms=self.busy_timeout_ms,
        )


def record_artifact_evidence(
    operation: str,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Record safe success/failure evidence around a service operation."""

    def decorate(method: Callable[P, R]) -> Callable[P, R]:
        @wraps(method)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            service = args[0]
            subject = args[1] if len(args) > 1 else kwargs.get("command") or kwargs.get("query")
            context = args[2] if len(args) > 2 else kwargs.get("context")
            if not isinstance(context, OperationContext):
                raise TypeError("artifact evidence requires an operation context")
            started = perf_counter()
            try:
                service.require_operation_enabled(operation, subject, context)
                result = method(*args, **kwargs)
            except ArtifactDomainError as exc:
                latency_ms = (perf_counter() - started) * 1_000
                status: EvidenceStatus = (
                    "denied"
                    if exc.code
                    in {
                        ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
                        ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE,
                        ArtifactErrorCode.ARTIFACT_WORKSPACE_MISMATCH,
                    }
                    else "error"
                )
                service.evidence.record(
                    operation=operation,
                    context=context,
                    status=status,
                    reason_code=exc.code.value,
                    latency_ms=latency_ms,
                    artifact_id=_subject_artifact_id(subject),
                )
                service.operations.observe_operation(
                    operation=operation,
                    reason_code=exc.code.value,
                    latency_ms=latency_ms,
                    success=False,
                    artifact_kind=_operation_kind(service, context, None, subject),
                    actor_type=context.principal_type.value,
                    result=status,
                    format_name=_operation_format(None, subject),
                )
                _append_safe_operation_log(
                    service=service,
                    operation=operation,
                    context=context,
                    result=None,
                    subject=subject,
                    status=status,
                    reason_code=exc.code.value,
                    latency_ms=latency_ms,
                )
                raise
            artifact_id, revision_id, content_sha256 = _result_bindings(result, subject)
            latency_ms = (perf_counter() - started) * 1_000
            service.evidence.record(
                operation=operation,
                context=context,
                status="success",
                reason_code="ARTIFACT_OPERATION_SUCCEEDED",
                latency_ms=latency_ms,
                artifact_id=artifact_id,
                revision_id=revision_id,
                content_sha256=content_sha256,
            )
            service.operations.observe_operation(
                operation=operation,
                reason_code="ARTIFACT_OPERATION_SUCCEEDED",
                latency_ms=latency_ms,
                success=True,
                artifact_kind=_operation_kind(service, context, result, subject),
                actor_type=context.principal_type.value,
                result="success",
                format_name=_operation_format(result, subject),
                content_size_bytes=_result_content_size(result),
            )
            _append_safe_operation_log(
                service=service,
                operation=operation,
                context=context,
                result=result,
                subject=subject,
                status="success",
                reason_code="ARTIFACT_OPERATION_SUCCEEDED",
                latency_ms=latency_ms,
            )
            return result

        return wrapped

    return decorate


def _subject_artifact_id(subject: object) -> str | None:
    for name in ("artifact_id", "source_artifact_id"):
        value = getattr(subject, name, None)
        if isinstance(value, str):
            return value
    return None


def _result_bindings(result: object, subject: object) -> tuple[str | None, str | None, str | None]:
    artifact = getattr(result, "artifact", None)
    revision = getattr(result, "revision", None)
    artifact_id = getattr(artifact, "artifact_id", None) or getattr(result, "artifact_id", None)
    revision_id = getattr(revision, "revision_id", None) or getattr(result, "revision_id", None)
    content_sha256 = (
        getattr(revision, "content_sha256", None)
        or getattr(result, "content_sha256", None)
        or getattr(result, "response_sha256", None)
        or getattr(result, "sha256", None)
    )
    return artifact_id or _subject_artifact_id(subject), revision_id, content_sha256


def _operation_kind(
    service: Any,
    context: OperationContext,
    result: object | None,
    subject: object,
) -> str:
    artifact = getattr(result, "artifact", None)
    value = getattr(artifact, "kind", None) or getattr(subject, "kind", None)
    if value is None:
        artifact_id = getattr(result, "artifact_id", None) or _subject_artifact_id(subject)
        if isinstance(artifact_id, str):
            try:
                value = service.store.get_artifact(context.workspace_id, artifact_id).kind
            except ArtifactDomainError:
                value = None
    return str(getattr(value, "value", value) or "unknown")


def _operation_format(result: object | None, subject: object) -> str:
    value = getattr(result, "format", None) or getattr(subject, "format", None)
    return str(getattr(value, "value", value) or "unknown")


def _result_content_size(result: object | None) -> int | None:
    value = getattr(result, "size_bytes", None)
    if isinstance(value, int):
        return value
    revision = getattr(result, "revision", None)
    revision_size = getattr(revision, "content_size_bytes", None)
    return revision_size if isinstance(revision_size, int) else None


def _append_safe_operation_log(
    *,
    service: Any,
    operation: str,
    context: OperationContext,
    result: object | None,
    subject: object,
    status: EvidenceStatus,
    reason_code: str,
    latency_ms: float,
) -> None:
    artifact_id, _, _ = _result_bindings(result, subject)
    revision = getattr(result, "revision", None)
    revision_number = getattr(revision, "revision_number", None)
    service.operation_logs.append(
        safe_artifact_log_event(
            component="artifact.service",
            operation=operation,
            workspace_id=context.workspace_id,
            artifact_id=artifact_id,
            artifact_kind=_operation_kind(service, context, result, subject),
            revision_number=(
                revision_number if isinstance(revision_number, int) else None
            ),
            actor_type=context.principal_type.value,
            result=status,
            reason_code=reason_code,
            latency_ms=latency_ms,
            content_size_bytes=_result_content_size(result),
            trace_id=context.request_id,
            request_id=context.request_id,
            sidecar_restart_count=0,
            level="INFO" if status == "success" else "WARNING",
        )
    )


def _event_from_row(row: sqlite3.Row) -> ArtifactEvidenceEvent:
    return ArtifactEvidenceEvent(
        event_sequence=row["event_sequence"],
        event_id=row["event_id"],
        workspace_ref=row["workspace_ref"],
        operation=row["operation"],
        status=row["status"],
        reason_code=row["reason_code"],
        artifact_ref=row["artifact_ref"],
        revision_ref=row["revision_ref"],
        content_sha256=row["content_sha256"],
        principal_ref=row["principal_ref"],
        request_ref=row["request_ref"],
        latency_bucket=row["latency_bucket"],
        previous_event_hash=row["previous_event_hash"],
        event_hash=row["event_hash"],
        created_at_utc=datetime.fromisoformat(row["created_at_utc"]),
    )


def _ref(namespace: str, *parts: str) -> str:
    payload = "\x1f".join((namespace, *parts)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _optional_ref(namespace: str, value: str | None) -> str | None:
    return None if value is None else _ref(namespace, value)


def _latency_bucket(latency_ms: float) -> str:
    if latency_ms < 10:
        return "lt10ms"
    if latency_ms < 50:
        return "lt50ms"
    if latency_ms < 250:
        return "lt250ms"
    if latency_ms < 1_000:
        return "lt1s"
    return "gte1s"
