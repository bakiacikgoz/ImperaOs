from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from imperaos.control_plane.models import PolicyPackManifest
from imperaos.control_plane.policy_packs import validate_policy_pack
from imperaos.control_plane.storage import ControlPlaneStore, canonical_json_hash
from imperaos.enterprise.signing import write_signed_json
from imperaos.runtime.config import RuntimeConfig

PolicyPackLifecycleStatus = Literal[
    "draft",
    "validated",
    "staged",
    "promoted",
    "active",
    "superseded",
    "rollback_planned",
    "rolled_back",
    "rejected",
]


class PolicyPackLifecycleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: str = "control-plane.policy-pack-lifecycle/v1"
    policy_pack_id: str = Field(alias="policyPackId")
    policy_version: str = Field(alias="policyVersion")
    status: PolicyPackLifecycleStatus
    content_hash: str = Field(alias="contentHash")
    diff_summary: dict[str, Any] = Field(default_factory=dict, alias="diffSummary")
    simulation_summary: dict[str, Any] = Field(default_factory=dict, alias="simulationSummary")
    activation_audit: dict[str, Any] | None = Field(default=None, alias="activationAudit")
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )


def validate_lifecycle_policy_pack(
    *,
    manifest: PolicyPackManifest,
    store_root: Path,
) -> PolicyPackLifecycleRecord:
    validation = validate_policy_pack(manifest)
    status: PolicyPackLifecycleStatus = "validated" if validation.status == "pass" else "rejected"
    record = _record(manifest=manifest, status=status, simulation_summary={
        "validationStatus": validation.status,
        "blockingReasons": validation.blocking_reasons,
        "warnings": validation.warnings,
    })
    _write_record(store_root, record)
    return record


def stage_policy_pack(
    *,
    manifest: PolicyPackManifest,
    store_root: Path,
) -> PolicyPackLifecycleRecord:
    validation = validate_policy_pack(manifest)
    status: PolicyPackLifecycleStatus = "staged" if validation.status == "pass" else "rejected"
    record = _record(manifest=manifest, status=status, simulation_summary={
        "validationStatus": validation.status,
        "wouldStage": validation.status == "pass",
    })
    _write_record(store_root, record)
    return record


def promote_policy_pack(
    *,
    manifest: PolicyPackManifest,
    store_root: Path,
    config: RuntimeConfig | None = None,
) -> PolicyPackLifecycleRecord:
    validation = validate_policy_pack(manifest)
    status: PolicyPackLifecycleStatus = "active" if validation.status == "pass" else "rejected"
    audit = {
        "promotedAt": datetime.now(UTC).isoformat(),
        "policyPackId": manifest.policy_pack_id,
        "policyVersion": manifest.version,
        "contentHash": canonical_json_hash(manifest.model_dump(mode="json", by_alias=True)),
    }
    record = _record(
        manifest=manifest,
        status=status,
        activation_audit=audit if status == "active" else None,
        simulation_summary={"validationStatus": validation.status},
    )
    store = ControlPlaneStore(store_root)
    if status == "active":
        active = store.read_json("policy-packs/active.json", default=None)
        if isinstance(active, dict):
            previous = PolicyPackLifecycleRecord.model_validate(active)
            _write_record(store_root, previous.model_copy(update={"status": "superseded"}))
        store.write_json_atomic(
            "policy-packs/active.json",
            record.model_dump(mode="json", by_alias=True),
        )
        write_signed_json(
            path=store.path(
                f"policy-packs/audit/{manifest.policy_pack_id}-{manifest.version}.json"
            ),
            artifact="policy_pack_activation_audit",
            data=audit,
            config=config,
            purpose="policy-pack-activation",
        )
    _write_record(store_root, record)
    return record


def plan_policy_pack_rollback(
    *,
    policy_pack_id: str,
    store_root: Path,
) -> PolicyPackLifecycleRecord:
    store = ControlPlaneStore(store_root)
    active = store.read_json("policy-packs/active.json", default=None)
    if not isinstance(active, dict):
        raise ValueError("active policy pack not found")
    record = PolicyPackLifecycleRecord.model_validate(active)
    if record.policy_pack_id != policy_pack_id:
        raise ValueError("requested policy pack is not active")
    planned = record.model_copy(update={"status": "rollback_planned"})
    _write_record(store_root, planned)
    return planned


def _record(
    *,
    manifest: PolicyPackManifest,
    status: PolicyPackLifecycleStatus,
    diff_summary: dict[str, Any] | None = None,
    simulation_summary: dict[str, Any] | None = None,
    activation_audit: dict[str, Any] | None = None,
) -> PolicyPackLifecycleRecord:
    return PolicyPackLifecycleRecord(
        policyPackId=manifest.policy_pack_id,
        policyVersion=manifest.version,
        status=status,
        contentHash=canonical_json_hash(manifest.model_dump(mode="json", by_alias=True)),
        diffSummary=diff_summary or {},
        simulationSummary=simulation_summary or {},
        activationAudit=activation_audit,
    )


def _write_record(store_root: Path, record: PolicyPackLifecycleRecord) -> None:
    store = ControlPlaneStore(store_root)
    safe_version = record.policy_version.replace("/", "-")
    store.write_json_atomic(
        f"policy-packs/records/{record.policy_pack_id}-{safe_version}.json",
        record.model_dump(mode="json", by_alias=True),
    )


def build_policy_pack_lifecycle_report(
    *,
    store_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    store = ControlPlaneStore(store_root)
    records_root = store.path("policy-packs/records")
    records = []
    if records_root.exists():
        for path in sorted(records_root.glob("*.json")):
            records.append(json.loads(path.read_text(encoding="utf-8")))
    report = {
        "version": "control-plane.policy-pack-lifecycle-report/v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "status": "pass" if records else "conditional",
        "recordCount": len(records),
        "records": records,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
