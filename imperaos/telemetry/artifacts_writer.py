from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ARTIFACT_FILENAMES = {
    "status": "status.json",
    "test_summary": "test_summary.json",
    "benchmark_summary": "benchmark_summary.json",
    "router_shadow_summary": "router_shadow_summary.json",
    "research_summary": "research_summary.json",
    "governance_summary": "governance_summary.json",
    "team_summary": "team_summary.json",
    "team_pilot_report": "team_pilot_report.json",
    "security_posture": "security_posture.json",
    "metrics_snapshot": "metrics_snapshot.json",
    "support_bundle_manifest": "support_bundle_manifest.json",
    "ga_readiness_report": "ga_readiness_report.json",
}


def ensure_artifact_scaffold(artifacts_dir: str | Path = "artifacts") -> dict[str, str]:
    root = Path(artifacts_dir)
    root.mkdir(parents=True, exist_ok=True)
    created: dict[str, str] = {}
    for name, filename in ARTIFACT_FILENAMES.items():
        path = root / filename
        if path.exists():
            created[name] = str(path)
            continue
        payload = {
            "artifact": name,
            "generated_at": _now_iso(),
            "status": "placeholder",
            "data": {},
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        created[name] = str(path)
    return created


def write_artifact(
    name: str,
    payload: dict[str, Any],
    *,
    artifacts_dir: str | Path = "artifacts",
) -> str:
    if name not in ARTIFACT_FILENAMES:
        raise ValueError(f"unknown artifact type: {name}")
    ensure_artifact_scaffold(artifacts_dir)
    path = Path(artifacts_dir) / ARTIFACT_FILENAMES[name]
    body = {
        "artifact": name,
        "generated_at": _now_iso(),
        "status": "ok",
        "data": payload,
    }
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
