from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from imperaos.memory.authority import build_memory_authority, proposal_from_cli
from imperaos.memory.models import MemoryRetrievalRequest, hash_identity
from imperaos.runtime.config import RuntimeConfig


def run_memory_retrieval_eval(
    *,
    config: RuntimeConfig,
    suite: str | Path,
) -> dict[str, Any]:
    authority = build_memory_authority(config)
    path = Path(suite)
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    total = 0
    hits = 0
    denied = 0
    latencies: list[float] = []
    actor_hash = hash_identity("eval-operator")
    owner_hash = hash_identity("eval-operator")
    for row in rows:
        if row.get("seedMemory"):
            proposal = proposal_from_cli(
                actor="eval-operator",
                scope=str(row.get("scope", "personal")),
                owner_type=str(row.get("ownerType", "user")),
                owner="eval-operator",
                visibility=str(row.get("visibility", "private")),
                text=str(row["seedMemory"]),
                role="Eval Agent",
                reason="retrieval eval seed",
            )
            authority.propose_write(proposal)
        start = time.perf_counter()
        result = authority.retrieve(
            MemoryRetrievalRequest(
                actorIdHash=actor_hash,
                requesterRole=str(row.get("requesterRole", "Eval Agent")),
                query=str(row.get("query", "")),
                allowedScopes=list(row.get("allowedScopes", ["personal"])),
                scopeFilters=[
                    {
                        "scope": row.get("scope", "personal"),
                        "ownerType": row.get("ownerType", "user"),
                        "ownerIdHash": owner_hash,
                        "namespace": "default",
                    }
                ],
                visibilityFilters=[str(row.get("visibility", "private"))],
                includeContent=True,
                purpose="eval",
            )
        )
        latencies.append((time.perf_counter() - start) * 1000)
        total += 1
        if result.status == "denied":
            denied += 1
        expected = str(row.get("expectedContains", "")).lower()
        if expected and any(
            expected in str(hit.content_summary or "").lower() for hit in result.hits
        ):
            hits += 1
    p95 = sorted(latencies)[int(max(0, len(latencies) - 1) * 0.95)] if latencies else 0
    return {
        "status": "pass",
        "total": total,
        "hits": hits,
        "recallAtK": hits / total if total else 0,
        "deniedRetrievalCount": denied,
        "p95LatencyMs": round(p95, 3),
    }
