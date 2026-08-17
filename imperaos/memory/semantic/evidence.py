from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from imperaos.memory.models import sha256_text, stable_id, utc_now

FORBIDDEN_KEYS = {"query", "raw", "summary", "redactedSummary", "content", "text"}


def write_semantic_evidence(
    *,
    evidence_root: str | Path,
    event_type: str,
    principal_id: str,
    workspace_id: str,
    query_hash: str | None = None,
    hit_ids: tuple[str, ...] = (),
    reason_codes: tuple[str, ...] = (),
) -> str:
    payload: dict[str, Any] = {
        "schemaVersion": "memory-semantic-evidence/v1",
        "eventType": event_type,
        "eventId": stable_id(
            "mem_sem_evt",
            event_type,
            workspace_id,
            principal_id,
            query_hash or "",
            utc_now().isoformat(),
        ),
        "workspaceId": workspace_id,
        "principalIdHash": sha256_text(principal_id),
        "queryHash": query_hash,
        "hitIds": list(hit_ids),
        "reasonCodes": list(reason_codes),
        "generatedAtUtc": utc_now().isoformat(),
        "rawContentIncluded": False,
    }
    _assert_hash_only(payload)
    root = Path(evidence_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{payload['eventId']}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(path)


def _assert_hash_only(payload: dict[str, Any]) -> None:
    lower_keys = {key.lower() for key in payload}
    if any(forbidden.lower() in lower_keys for forbidden in FORBIDDEN_KEYS):
        raise ValueError("semantic evidence may only include hashes and ids")
    if payload.get("rawContentIncluded") is not False:
        raise ValueError("semantic evidence must not include raw content")
