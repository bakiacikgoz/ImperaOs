from __future__ import annotations

from imperaos.artifacts.operations import (
    ARTIFACT_METRIC_NAMES,
    ArtifactOperationMetrics,
    safe_artifact_log_event,
)


def test_artifact_metric_contract_contains_the_complete_phase_22_set() -> None:
    assert ARTIFACT_METRIC_NAMES == (
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
    assert set(ArtifactOperationMetrics().snapshot()) == set(ARTIFACT_METRIC_NAMES)


def test_artifact_log_contract_is_bounded_and_contains_no_payload_fields() -> None:
    event = safe_artifact_log_event(
        component="artifact.service",
        operation="artifact.create",
        workspace_id="workspace-secret",
        artifact_id="artifact-1",
        artifact_kind="document",
        revision_number=1,
        actor_type="user",
        result="success",
        reason_code="ARTIFACT_OPERATION_SUCCEEDED",
        latency_ms=12.4,
        content_size_bytes=1200,
        trace_id="trace-1",
        request_id="request-1",
        sidecar_restart_count=0,
    )

    assert set(event) == {
        "timestamp_utc", "level", "component", "operation", "workspace_id_hash",
        "artifact_id", "artifact_kind", "revision_number", "actor_type", "result",
        "reason_code", "latency_ms", "content_size_bucket", "trace_id", "request_id",
        "sidecar_restart_count",
    }
    assert event["workspace_id_hash"] != "workspace-secret"
    serialized = str(event).lower()
    for forbidden in ("raw_content", "prompt", "provider", "authorization", "secret", "file_path"):
        assert forbidden not in serialized
