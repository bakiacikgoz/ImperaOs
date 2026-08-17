from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from imperaos.control_plane.models import (
    AgentRecord,
    AgentRegistryV2Item,
    AgentRegistryV2Snapshot,
    AgentStatus,
)
from imperaos.control_plane.registry import AgentRegistry

AgentType = Literal["internal", "external_stdio", "external_http", "computer_use_adapter"]
RiskProfile = Literal["read_only", "guarded", "restricted", "blocked"]
EvidenceStatus = Literal["missing", "pending", "valid", "invalid"]


def build_agent_registry_v2(registry: AgentRegistry) -> AgentRegistryV2Snapshot:
    return AgentRegistryV2Snapshot(
        generated_at_utc=datetime.now(UTC),
        agents=[agent_registry_v2_item(record) for record in registry.list_agents()],
    )


def agent_registry_v2_item(record: AgentRecord) -> AgentRegistryV2Item:
    metadata = record.spec.metadata
    return AgentRegistryV2Item(
        agent_id=record.agent_id,
        display_name=record.spec.display_name,
        runtime_kind=str(record.spec.runtime_kind),
        agent_type=agent_type_for_runtime(str(record.spec.runtime_kind)),
        owner_team=record.spec.owner.team,
        owner_contact=record.spec.owner.contact,
        policy_pack_id=_metadata_string(metadata, "policy_pack_id", "active-runtime-policy"),
        risk_profile=_risk_profile(metadata, record=record),
        adapter_contract_version=_metadata_string_or_none(metadata, "adapter_contract_version"),
        enabled=str(record.status) == AgentStatus.REGISTERED.value,
        status=str(record.status),
        readiness=str(record.readiness),
        last_run_id=record.last_run_id,
        last_evidence_pack_id=record.last_evidence_pack_id,
        last_evidence_status=last_evidence_status(record),
        workspace_id=_metadata_string_or_none(metadata, "workspace_id"),
        principal_id=_metadata_string_or_none(metadata, "principal_id"),
        device_id=_metadata_string_or_none(metadata, "device_id"),
        enrollment_id=_metadata_string_or_none(metadata, "enrollment_id"),
        enrollment_status=_metadata_string_or_none(metadata, "enrollment_status"),
        workspace_binding_status=_workspace_binding_status(metadata),
        updated_at=record.updated_at,
    )


def agent_type_for_runtime(runtime_kind: str) -> AgentType:
    if runtime_kind == "external_stdio":
        return "external_stdio"
    if runtime_kind == "external_http":
        return "external_http"
    if runtime_kind == "computer_use_adapter":
        return "computer_use_adapter"
    return "internal"


def risk_profile_for_record(record: AgentRecord) -> RiskProfile:
    return _risk_profile(record.spec.metadata, record=record)


def last_evidence_status(record: AgentRecord) -> EvidenceStatus:
    metadata_status = _metadata_string_or_none(record.spec.metadata, "last_evidence_status")
    if metadata_status in {"pending", "valid", "invalid"}:
        return metadata_status
    return "pending" if record.last_evidence_pack_id else "missing"


def _risk_profile(metadata: dict[str, object], *, record: AgentRecord) -> RiskProfile:
    metadata_profile = _metadata_string_or_none(metadata, "risk_profile")
    if metadata_profile in {"read_only", "guarded", "restricted", "blocked"}:
        return metadata_profile
    if str(record.status) != AgentStatus.REGISTERED.value:
        return "blocked"
    risk_classes = {str(action.risk_class) for action in record.spec.declared_actions}
    if not risk_classes or risk_classes == {"read_only"}:
        return "read_only"
    if risk_classes & {"destructive", "credential_sensitive", "financial_or_legal"}:
        return "restricted"
    return "guarded"


def _metadata_string(metadata: dict[str, object], key: str, default: str) -> str:
    value = _metadata_string_or_none(metadata, key)
    return value or default


def _metadata_string_or_none(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _workspace_binding_status(
    metadata: dict[str, object],
) -> Literal["unbound", "bound", "blocked"]:
    status = _metadata_string_or_none(metadata, "workspace_binding_status")
    if status in {"unbound", "bound", "blocked"}:
        return status
    if _metadata_string_or_none(metadata, "workspace_id") and _metadata_string_or_none(
        metadata,
        "enrollment_id",
    ):
        return "bound"
    return "unbound"
