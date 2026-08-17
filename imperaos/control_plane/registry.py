from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from imperaos.control_plane.errors import (
    AgentAlreadyExistsWithDifferentSpec,
    AgentNotFound,
    AgentSpecValidationError,
)
from imperaos.control_plane.models import (
    AgentReadiness,
    AgentRecord,
    AgentRegisterResult,
    AgentSpec,
    AgentStatus,
)
from imperaos.control_plane.storage import ControlPlaneStore, canonical_json_hash
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT

REGISTRY_FILE = "agents.json"


def load_agent_spec(path: str | Path) -> AgentSpec:
    source = Path(path)
    if not source.exists():
        raise AgentSpecValidationError("AGENT_SPEC_NOT_FOUND", f"agent spec not found: {source}")
    try:
        if source.suffix.lower() in {".yaml", ".yml"}:
            payload = yaml.safe_load(source.read_text(encoding="utf-8"))
        else:
            payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("agent spec must be an object")
        return AgentSpec.model_validate(payload)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        raise AgentSpecValidationError("AGENT_SPEC_INVALID", str(exc)) from exc


class AgentRegistry:
    def __init__(self, *, root_dir: str | Path = CONTROL_PLANE_STATE_ROOT):
        self.store = ControlPlaneStore(root_dir)

    @property
    def registry_path(self) -> Path:
        return self.store.path(REGISTRY_FILE)

    def register(self, spec: AgentSpec, *, actor: str) -> AgentRegisterResult:
        payload = self._read_registry()
        agents = payload.setdefault("agents", {})
        spec_payload = spec.model_dump(mode="json")
        spec_hash = canonical_json_hash(spec_payload)
        now = datetime.now(UTC)

        existing = agents.get(spec.agent_id)
        if isinstance(existing, dict):
            record = AgentRecord.model_validate(existing)
            if record.spec_hash != spec_hash:
                raise AgentAlreadyExistsWithDifferentSpec(
                    "AGENT_ID_CONFLICT",
                    f"agent_id '{spec.agent_id}' already exists with a different spec",
                )
            return AgentRegisterResult(
                status="unchanged",
                agent_id=spec.agent_id,
                spec_hash=spec_hash,
                record_path=str(self.registry_path),
                record=record,
            )

        record = AgentRecord(
            agent_id=spec.agent_id,
            spec_hash=spec_hash,
            status=AgentStatus.REGISTERED,
            readiness=AgentReadiness.NOT_EVALUATED,
            created_at=now,
            updated_at=now,
            spec=spec,
        )
        agents[spec.agent_id] = record.model_dump(mode="json")
        payload["updated_at"] = now.isoformat()
        payload["last_actor"] = actor
        self.store.write_json_atomic(REGISTRY_FILE, payload)
        return AgentRegisterResult(
            status="registered",
            agent_id=spec.agent_id,
            spec_hash=spec_hash,
            record_path=str(self.registry_path),
            record=record,
        )

    def list_agents(self) -> list[AgentRecord]:
        payload = self._read_registry()
        agents = payload.get("agents", {})
        if not isinstance(agents, dict):
            return []
        return [
            AgentRecord.model_validate(item)
            for _agent_id, item in sorted(agents.items(), key=lambda pair: pair[0])
            if isinstance(item, dict)
        ]

    def get(self, agent_id: str) -> AgentRecord:
        payload = self._read_registry()
        agents = payload.get("agents", {})
        item = agents.get(agent_id) if isinstance(agents, dict) else None
        if not isinstance(item, dict):
            raise AgentNotFound("AGENT_NOT_FOUND", f"agent '{agent_id}' is not registered")
        return AgentRecord.model_validate(item)

    def update_record(self, record: AgentRecord) -> AgentRecord:
        payload = self._read_registry()
        agents = payload.setdefault("agents", {})
        if record.agent_id not in agents:
            raise AgentNotFound("AGENT_NOT_FOUND", f"agent '{record.agent_id}' is not registered")
        next_record = record.model_copy(update={"updated_at": datetime.now(UTC)})
        agents[record.agent_id] = next_record.model_dump(mode="json")
        payload["updated_at"] = datetime.now(UTC).isoformat()
        self.store.write_json_atomic(REGISTRY_FILE, payload)
        return next_record

    def disable(self, agent_id: str, *, reason: str, actor: str) -> AgentRecord:
        record = self.get(agent_id)
        next_record = record.model_copy(
            update={
                "status": AgentStatus.DISABLED,
                "readiness": AgentReadiness.BLOCKED,
                "disabled_reason": reason,
                "updated_at": datetime.now(UTC),
            }
        )
        payload = self._read_registry()
        payload["agents"][agent_id] = next_record.model_dump(mode="json")
        payload["updated_at"] = datetime.now(UTC).isoformat()
        payload["last_actor"] = actor
        self.store.write_json_atomic(REGISTRY_FILE, payload)
        return next_record

    def _read_registry(self) -> dict[str, Any]:
        payload = self.store.read_json(
            REGISTRY_FILE,
            default={
                "version": "control-plane.registry/v1",
                "agents": {},
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )
        if not isinstance(payload, dict):
            return {"version": "control-plane.registry/v1", "agents": {}}
        payload.setdefault("version", "control-plane.registry/v1")
        payload.setdefault("agents", {})
        return payload
