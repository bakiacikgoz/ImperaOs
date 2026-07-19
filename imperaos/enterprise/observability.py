from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.runtime.config import RuntimeConfig
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT


def collect_metrics_snapshot(config: RuntimeConfig) -> dict[str, Any]:
    jobs_root = Path(config.team.artifact_dir)
    audit_dir = Path(config.governance.audit_dir)
    approvals_db = Path(config.governance.approval_store_path)

    job_counts = {"completed": 0, "failed": 0, "blocked": 0, "running": 0, "pending": 0}
    fallback_mode_count = 0
    memory_conflict_count = 0
    serialized_count = 0
    audit_inconsistency_count = 0
    replay_verify_failure_count = 0
    total_events = 0
    task_lag_count = 0

    if jobs_root.exists():
        for job_dir in sorted(item for item in jobs_root.iterdir() if item.is_dir()):
            status_path = job_dir / "status.json"
            if status_path.exists():
                payload = json.loads(status_path.read_text(encoding="utf-8"))
                status = str(payload.get("job", {}).get("status") or "pending").lower()
                if status in job_counts:
                    job_counts[status] += 1
            events_path = job_dir / "events.jsonl"
            if events_path.exists():
                for line in events_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    total_events += 1
                    item = json.loads(line)
                    event_name = str(item.get("event") or "")
                    if event_name == "fallback_mode_applied":
                        fallback_mode_count += 1
                    if event_name == "memory_conflict_rejected":
                        memory_conflict_count += 1
                    if item.get("serialized_due_to_policy"):
                        serialized_count += 1
            envelope_path = job_dir / "audit_envelope.json"
            if envelope_path.exists():
                envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
                consistency = envelope.get("consistency") or {}
                if not bool(consistency.get("verified", False)):
                    audit_inconsistency_count += 1
                    replay_verify_failure_count += 1
                if (
                    status_path.exists()
                    and str(payload.get("job", {}).get("status") or "").lower() == "running"
                ):
                    task_lag_count += 1

    pending_approvals = 0
    oldest_pending_age_s = 0
    operator_action_count = 0
    if approvals_db.exists():
        with sqlite3.connect(approvals_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT status, created_at, actor FROM approvals ORDER BY created_at ASC"
            ).fetchall()
        now = datetime.now(UTC)
        for row in rows:
            status = str(row["status"])
            actor = str(row["actor"] or "")
            if actor:
                operator_action_count += 1
            if status == "pending":
                pending_approvals += 1
                created_at = datetime.fromisoformat(str(row["created_at"]))
                oldest_pending_age_s = max(
                    oldest_pending_age_s,
                    int((now - created_at).total_seconds()),
                )

    snapshot = {
        "generated_at": datetime.now(UTC).isoformat(),
        "profile": config.profile_name,
        "provider": config.llm_provider,
        "job_counts": job_counts,
        "approval_queue": {
            "pending": pending_approvals,
            "oldest_pending_age_s": oldest_pending_age_s,
        },
        "audit": {
            "audit_file_count": len(list(audit_dir.glob("*.json"))) if audit_dir.exists() else 0,
            "audit_inconsistency_count": audit_inconsistency_count,
            "replay_verify_failure_count": replay_verify_failure_count,
        },
        "concurrency": {
            "fallback_mode_count": fallback_mode_count,
            "memory_conflict_count": memory_conflict_count,
            "serialized_due_to_policy_count": serialized_count,
        },
        "runtime": {
            "total_events": total_events,
            "task_lag_count": task_lag_count,
            "operator_action_count": operator_action_count,
        },
        "control_plane": _control_plane_metrics(),
        "backup_restore": _maintenance_timestamps(config),
        "dashboard_sections": [
            "runtime_health",
            "governance_approvals",
            "concurrency_conflicts",
            "provider_health",
            "storage_retention",
            "security_admin_actions",
        ],
        "incident_severities": {
            "SEV0": [
                "replay_verify_fail",
                "signature_verify_fail",
                "unauthorized_mutation",
                "audit_tamper",
            ],
            "SEV1": [
                "runtime_unavailable",
                "restore_failure",
                "migration_failure",
                "provider_unusable",
            ],
            "SEV2": ["high_fallback_rate", "high_conflict_rate", "approval_backlog"],
            "SEV3": ["dashboard_gap", "reporting_gap"],
        },
        "slo_targets": {
            "replay_verify_pass_rate": "100%",
            "audit_consistency_error_rate": "0",
            "completed_job_integrity_failures": "0",
            "provider_health_success_24h": ">=99.5%",
            "fallback_rate_target": "<5%",
            "fallback_rate_alert": ">10%",
            "memory_conflict_target": "<2%",
            "memory_conflict_alert": ">5%",
        },
    }
    return snapshot


def _control_plane_metrics() -> dict[str, Any]:
    root = Path(CONTROL_PLANE_STATE_ROOT)
    agents_file = root / "agents.json"
    runs_root = root / "runs"
    agents_registered = 0
    if agents_file.exists():
        try:
            payload = json.loads(agents_file.read_text(encoding="utf-8"))
            agents = payload.get("agents", {})
            if isinstance(agents, dict):
                agents_registered = len(agents)
        except json.JSONDecodeError:
            agents_registered = 0
    runs_submitted = 0
    runs_blocked = 0
    if runs_root.exists():
        for path in runs_root.glob("*.json"):
            runs_submitted += 1
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            status = str(payload.get("run", {}).get("status", ""))
            if status in {"policy_blocked", "blocked", "failed"}:
                runs_blocked += 1
    claim_blocked = 0
    claim_matrix = Path("artifacts/control_plane_claim_matrix.json")
    if claim_matrix.exists():
        try:
            payload = json.loads(claim_matrix.read_text(encoding="utf-8"))
            claims = payload.get("claims", [])
            if isinstance(claims, list):
                claim_blocked = sum(
                    1
                    for item in claims
                    if isinstance(item, dict) and item.get("status") == "blocked"
                )
        except json.JSONDecodeError:
            claim_blocked = 0
    return {
        "control_plane_agents_registered": agents_registered,
        "control_plane_runs_submitted": runs_submitted,
        "control_plane_runs_blocked": runs_blocked,
        "control_plane_policy_denies": 0,
        "control_plane_approval_pending_age_seconds": 0,
        "control_plane_evidence_verify_failures": 0,
        "control_plane_claims_blocked": claim_blocked,
        "control_plane_computer_use_live_claim_blocked": 1,
    }


def write_prometheus_textfile(snapshot: dict[str, Any], destination: str | Path) -> str:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"imperaos_approval_pending {snapshot['approval_queue']['pending']}",
        (
            "imperaos_approval_oldest_age_seconds "
            f"{snapshot['approval_queue']['oldest_pending_age_s']}"
        ),
        f"imperaos_audit_inconsistency_total {snapshot['audit']['audit_inconsistency_count']}",
        f"imperaos_replay_verify_failure_total {snapshot['audit']['replay_verify_failure_count']}",
        f"imperaos_memory_conflict_total {snapshot['concurrency']['memory_conflict_count']}",
        f"imperaos_fallback_mode_total {snapshot['concurrency']['fallback_mode_count']}",
        (
            "imperaos_control_plane_agents_registered "
            f"{snapshot['control_plane']['control_plane_agents_registered']}"
        ),
        (
            "imperaos_control_plane_claims_blocked "
            f"{snapshot['control_plane']['control_plane_claims_blocked']}"
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _maintenance_timestamps(config: RuntimeConfig) -> dict[str, str | None]:
    backup_dir = Path(config.maintenance.backup_dir)
    migration_dir = Path(config.maintenance.migration_dir)
    restore_dir = Path(config.maintenance.restore_dir)
    return {
        "last_backup": _latest_timestamp(backup_dir, "manifest.json"),
        "last_migration": _latest_timestamp(migration_dir, "*.json"),
        "last_restore_verify": _latest_timestamp(restore_dir, "*.json"),
    }


def _latest_timestamp(root: Path, pattern: str) -> str | None:
    if not root.exists():
        return None
    candidates = sorted(root.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        return None
    return datetime.fromtimestamp(candidates[0].stat().st_mtime, tz=UTC).isoformat()
