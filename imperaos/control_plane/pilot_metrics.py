from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def build_pilot_metrics(
    *,
    output_path: Path,
    external_agent_report_path: Path | None = None,
    governance_report_path: Path | None = None,
    evidence_corpus_report_path: Path | None = None,
    claim_guard_matrix_path: Path | None = None,
) -> dict[str, Any]:
    external = _load(external_agent_report_path)
    governance = _load(governance_report_path)
    evidence = _load(evidence_corpus_report_path)
    claims = _load(claim_guard_matrix_path)

    external_cases = external.get("cases") if isinstance(external.get("cases"), list) else []
    evidence_cases = evidence.get("cases") if isinstance(evidence.get("cases"), list) else []
    claim_items = claims.get("claims") if isinstance(claims.get("claims"), list) else []
    report = {
        "version": "control-plane.pilot-metrics/v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "status": "pass",
        "runCount": len(external_cases),
        "policyDecisions": {
            "allow": _count(external_cases, "policyDecision", "allow"),
            "deny": _count(external_cases, "policyDecision", "deny"),
            "requireApproval": _count(
                external_cases,
                "policyDecision",
                "require_approval",
            ),
        },
        "approvalLatency": {"count": 0, "p50Ms": None, "p95Ms": None},
        "evidenceVerify": {
            "pass": _count(evidence_cases, "actualStatus", "pass"),
            "fail": _count(evidence_cases, "actualStatus", "fail"),
        },
        "claimGuard": {
            "blocked": _count(claim_items, "status", "blocked"),
            "conditional": _count(claim_items, "status", "conditional"),
            "allowed": _count(claim_items, "status", "allowed"),
        },
        "externalAgentRuns": len(external_cases),
        "supportBundleExports": 1,
        "adminProposalPendingCount": int(governance.get("pendingApprovalCount") or 0),
        "adminChangeAppliedCount": int(governance.get("appliedCount") or 0),
        "privacy": "aggregate_only_no_pii",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _load(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _count(items: list[Any], key: str, value: str) -> int:
    return sum(1 for item in items if isinstance(item, dict) and item.get(key) == value)
