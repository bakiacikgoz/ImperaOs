from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from threading import RLock
from typing import Literal

ARTIFACT_METRIC_NAMES = (
    "imperaos_artifact_create_total",
    "imperaos_artifact_mutation_total",
    "imperaos_artifact_revision_conflict_total",
    "imperaos_artifact_autosave_latency_ms",
    "imperaos_artifact_open_latency_ms",
    "imperaos_artifact_rpc_request_latency_ms",
    "imperaos_artifact_rpc_restart_total",
    "imperaos_artifact_storage_integrity_failure_total",
    "imperaos_artifact_export_total",
    "imperaos_artifact_export_bytes",
    "imperaos_artifact_form_validation_failure_total",
    "imperaos_artifact_policy_denied_total",
    "imperaos_artifact_quota_rejected_total",
    "imperaos_artifact_editor_load_failure_total",
    "imperaos_artifact_license_block_total",
)

_MUTATION_OPERATIONS = {
    "artifact.mutate",
    "artifact.restore",
    "artifact.archive",
    "artifact.duplicate",
    "artifact.spreadsheet.cell_patch",
    "artifact.slides.slide_patch",
    "artifact.apply_proposal",
}


class ArtifactOperationMetrics:
    """Process-local bounded metric accumulator for the artifact subsystem."""

    def __init__(self) -> None:
        self._values = {name: 0.0 for name in ARTIFACT_METRIC_NAMES}
        self._series: dict[str, dict[tuple[tuple[str, str], ...], float]] = {
            name: {} for name in ARTIFACT_METRIC_NAMES
        }
        self._lock = RLock()

    def add(
        self,
        name: str,
        value: float = 1.0,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        if name not in self._values:
            raise ValueError("unknown artifact metric")
        if value < 0:
            raise ValueError("artifact metric increments must be non-negative")
        with self._lock:
            self._values[name] += float(value)
            key = tuple(sorted((str(label), str(item)) for label, item in (labels or {}).items()))
            self._series[name][key] = self._series[name].get(key, 0.0) + float(value)

    def observe_operation(
        self,
        *,
        operation: str,
        reason_code: str,
        latency_ms: float,
        success: bool,
        artifact_kind: str = "unknown",
        actor_type: str = "system",
        result: str | None = None,
        format_name: str = "unknown",
        content_size_bytes: int | None = None,
    ) -> None:
        result = result or ("success" if success else "error")
        if operation == "artifact.create":
            self.add(
                "imperaos_artifact_create_total",
                labels={"kind": artifact_kind, "result": result},
            )
        if operation in _MUTATION_OPERATIONS:
            self.add(
                "imperaos_artifact_mutation_total",
                labels={"kind": artifact_kind, "actor": actor_type, "result": result},
            )
            if success:
                self.add("imperaos_artifact_autosave_latency_ms", max(0.0, latency_ms))
        if operation == "artifact.get":
            self.add(
                "imperaos_artifact_open_latency_ms",
                max(0.0, latency_ms),
                labels={"kind": artifact_kind},
            )
        if operation.startswith("artifact.export."):
            self.add(
                "imperaos_artifact_export_total",
                labels={
                    "kind": artifact_kind,
                    "format": format_name,
                    "result": result,
                },
            )
        if operation == "artifact.export.completed" and success and content_size_bytes is not None:
            self.add("imperaos_artifact_export_bytes", content_size_bytes)
        reason_metric = {
            "ARTIFACT_REVISION_CONFLICT": "imperaos_artifact_revision_conflict_total",
            "FORM_VALIDATION_FAILED": "imperaos_artifact_form_validation_failure_total",
            "ARTIFACT_PERMISSION_DENIED": "imperaos_artifact_policy_denied_total",
            "ARTIFACT_POLICY_UNAVAILABLE": "imperaos_artifact_policy_denied_total",
            "ARTIFACT_QUOTA_EXCEEDED": "imperaos_artifact_quota_rejected_total",
            "ARTIFACT_LICENSE_UNAVAILABLE": "imperaos_artifact_license_block_total",
        }.get(reason_code)
        if reason_metric is not None:
            labels: dict[str, str] = {}
            if reason_metric in {
                "imperaos_artifact_revision_conflict_total",
                "imperaos_artifact_license_block_total",
            }:
                labels["kind"] = artifact_kind
            if reason_metric == "imperaos_artifact_policy_denied_total":
                labels["operation"] = operation
            self.add(reason_metric, labels=labels)

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            return {
                name: int(value) if value.is_integer() else round(value, 3)
                for name, value in self._values.items()
            }

    def series_snapshot(self) -> list[dict[str, object]]:
        with self._lock:
            return [
                {
                    "name": name,
                    "labels": dict(labels),
                    "value": int(value) if value.is_integer() else round(value, 3),
                }
                for name in ARTIFACT_METRIC_NAMES
                for labels, value in sorted(self._series[name].items())
                if value > 0
            ]


def safe_artifact_log_event(
    *,
    component: str,
    operation: str,
    workspace_id: str,
    artifact_id: str | None,
    artifact_kind: str | None,
    revision_number: int | None,
    actor_type: str,
    result: Literal["success", "denied", "error"],
    reason_code: str,
    latency_ms: float,
    content_size_bytes: int | None,
    trace_id: str,
    request_id: str,
    sidecar_restart_count: int,
    level: Literal["INFO", "WARNING", "ERROR"] = "INFO",
) -> dict[str, object]:
    """Build the exact safe-log envelope; payloads, paths and credentials are unrepresentable."""

    return {
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "level": level,
        "component": _bounded(component, 64),
        "operation": _bounded(operation, 100),
        "workspace_id_hash": hashlib.sha256(workspace_id.encode("utf-8")).hexdigest(),
        "artifact_id": _optional_bounded(artifact_id, 200),
        "artifact_kind": _optional_bounded(artifact_kind, 32),
        "revision_number": revision_number,
        "actor_type": _bounded(actor_type, 32),
        "result": result,
        "reason_code": _bounded(reason_code, 100),
        "latency_ms": round(max(0.0, latency_ms), 3),
        "content_size_bucket": _content_size_bucket(content_size_bytes),
        "trace_id": _bounded(trace_id, 128),
        "request_id": _bounded(request_id, 128),
        "sidecar_restart_count": max(0, sidecar_restart_count),
    }


def _bounded(value: str, limit: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > limit or any(ord(char) < 32 for char in normalized):
        raise ValueError("artifact log field is invalid")
    return normalized


def _optional_bounded(value: str | None, limit: int) -> str | None:
    return None if value is None else _bounded(value, limit)


def _content_size_bucket(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "unknown"
    if size_bytes < 1024:
        return "lt1KiB"
    if size_bytes < 1024 * 1024:
        return "lt1MiB"
    if size_bytes < 5 * 1024 * 1024:
        return "lt5MiB"
    return "gte5MiB"
