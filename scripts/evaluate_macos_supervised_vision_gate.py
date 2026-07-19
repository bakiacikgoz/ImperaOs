from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.runtime.platform import current_platform as runtime_current_platform  # noqa: E402

SCHEMA_VERSION = "1.0"
QUALIFICATION_LEVEL = "supervised_vision_v2"
EVIDENCE_FILES = {
    "provider_doctor": "provider_doctor_ollama_macos.json",
    "qualification_report": "macos_qualification_report.json",
    "runtime_summary": "vision_runtime_summary.json",
    "replay_verify": "replay_verify_report.json",
    "platform_matrix": "platform_matrix.json",
}


def evaluate_macos_supervised_v2_gate(
    *,
    evidence_root: Path,
    current_platform: str | None = None,
) -> dict[str, Any]:
    evidence_root = Path(evidence_root)
    platform_label = current_platform or runtime_current_platform().label
    payloads = _load_evidence(evidence_root)
    evidence = {
        "provider_doctor_present": payloads["provider_doctor"] is not None,
        "qualification_report_present": payloads["qualification_report"] is not None,
        "runtime_summary_present": payloads["runtime_summary"] is not None,
        "replay_verify_present": payloads["replay_verify"] is not None,
        "platform_matrix_present": payloads["platform_matrix"] is not None,
    }

    if platform_label != "macos":
        return _report(
            evidence_root=evidence_root,
            current_platform=platform_label,
            status="blocked",
            blocking_reasons=["MACOS_LIVE_QUALIFICATION_NOT_RUN_IN_THIS_ENV"],
            evidence=evidence,
            safety=_safety_summary(payloads),
        )

    blocking_reasons = _missing_evidence_reasons(evidence)
    fail_reasons: list[str] = []
    if not blocking_reasons:
        fail_reasons.extend(_provider_reasons(_as_mapping(payloads["provider_doctor"])))
        qualification_report = _as_mapping(payloads["qualification_report"])
        runtime_summary = _as_mapping(payloads["runtime_summary"])
        replay_verify = _as_mapping(payloads["replay_verify"])
        platform_matrix = _as_mapping(payloads["platform_matrix"])
        blocking_reasons.extend(_qualification_blocking_reasons(qualification_report))
        fail_reasons.extend(_qualification_fail_reasons(qualification_report))
        fail_reasons.extend(_runtime_summary_fail_reasons(runtime_summary))
        fail_reasons.extend(_replay_fail_reasons(qualification_report, replay_verify))
        fail_reasons.extend(_platform_matrix_fail_reasons(platform_matrix))

    safety = _safety_summary(payloads)
    if safety["raw_screenshot_persistence"] or safety["raw_screenshot_count"] > 0:
        fail_reasons.append("RAW_SCREENSHOT_PERSISTENCE_DETECTED")
    if not safety["sensitive_surface_stop_verified"] and not blocking_reasons:
        fail_reasons.append("SENSITIVE_SURFACE_STOP_NOT_VERIFIED")
    if not safety["approval_freshness_verified"] and not blocking_reasons:
        fail_reasons.append("APPROVAL_FRESHNESS_NOT_VERIFIED")
    if not safety["semantic_verifier_verified"] and not blocking_reasons:
        fail_reasons.append("SEMANTIC_VERIFIER_NOT_VERIFIED")
    if not safety["replay_integrity_verified"] and not blocking_reasons:
        fail_reasons.append("REPLAY_INTEGRITY_NOT_VERIFIED")

    unique_fail_reasons = _unique(fail_reasons)
    unique_blocking_reasons = _unique(blocking_reasons)
    if unique_fail_reasons:
        status = "fail"
        reasons = [*unique_blocking_reasons, *unique_fail_reasons]
    elif unique_blocking_reasons:
        status = "blocked"
        reasons = unique_blocking_reasons
    else:
        status = "pass"
        reasons = []

    return _report(
        evidence_root=evidence_root,
        current_platform=platform_label,
        status=status,
        blocking_reasons=_unique(reasons),
        evidence=evidence,
        safety=safety,
    )


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# macOS Supervised Vision v2 Gate",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Current platform: `{report.get('current_platform')}`",
        f"- Public live claim allowed: `{str(report.get('public_live_claim_allowed')).lower()}`",
        f"- Evidence root: `{report.get('evidence_root')}`",
        "",
        "## Evidence",
        "",
        "| Evidence | Present |",
        "| --- | --- |",
    ]
    evidence = report.get("evidence", {})
    if isinstance(evidence, Mapping):
        for key, value in evidence.items():
            lines.append(f"| `{key}` | `{'yes' if value else 'no'}` |")

    safety = report.get("safety", {})
    lines.extend(["", "## Safety", "", "| Check | Value |", "| --- | --- |"])
    if isinstance(safety, Mapping):
        for key, value in safety.items():
            lines.append(f"| `{key}` | `{value}` |")

    reasons = report.get("blocking_reasons", [])
    lines.extend(["", "## Blocking Reasons", ""])
    if isinstance(reasons, list) and reasons:
        lines.extend(f"- `{reason}`" for reason in reasons)
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate macOS supervised vision v2 gate.")
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=REPO_ROOT / "artifacts" / "computer_use",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument(
        "--current-platform",
        choices=("macos", "windows", "linux", "unknown"),
        default=None,
        help="Test override. Defaults to the current host platform.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = evaluate_macos_supervised_v2_gate(
        evidence_root=args.evidence_root,
        current_platform=args.current_platform,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.markdown.write_text(render_markdown(report), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report["status"] == "fail" else 0


def _load_evidence(evidence_root: Path) -> dict[str, Any | None]:
    payloads: dict[str, Any | None] = {}
    for key, filename in EVIDENCE_FILES.items():
        path = evidence_root / filename
        if not path.exists():
            payloads[key] = None
            continue
        try:
            payloads[key] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            payloads[key] = {
                "_invalid_json": True,
                "error": f"{type(exc).__name__}: {exc}",
            }
    return payloads


def _report(
    *,
    evidence_root: Path,
    current_platform: str,
    status: str,
    blocking_reasons: list[str],
    evidence: dict[str, bool],
    safety: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "platform": "macos",
        "current_platform": current_platform,
        "qualification_level": QUALIFICATION_LEVEL,
        "status": status,
        "public_live_claim_allowed": False,
        "blocking_reasons": blocking_reasons,
        "evidence_root": str(evidence_root),
        "evidence": evidence,
        "safety": safety,
    }


def _missing_evidence_reasons(evidence: Mapping[str, bool]) -> list[str]:
    reason_by_key = {
        "provider_doctor_present": "PROVIDER_DOCTOR_EVIDENCE_MISSING",
        "qualification_report_present": "MACOS_QUALIFICATION_REPORT_MISSING",
        "runtime_summary_present": "VISION_RUNTIME_SUMMARY_MISSING",
        "replay_verify_present": "REPLAY_VERIFY_REPORT_MISSING",
        "platform_matrix_present": "PLATFORM_MATRIX_EVIDENCE_MISSING",
    }
    return [
        reason
        for key, reason in reason_by_key.items()
        if evidence.get(key) is not True
    ]


def _provider_reasons(provider: Mapping[str, Any]) -> list[str]:
    if provider.get("_invalid_json") is True:
        return ["PROVIDER_DOCTOR_EVIDENCE_INVALID"]
    checks = (
        provider.get("status") == "pass",
        provider.get("ready") is True,
        provider.get("strictJsonPass") is True,
        provider.get("schemaValidationPass") is True,
        provider.get("strictJsonValidated") is True,
        provider.get("visionInputAccepted") is True,
    )
    return [] if all(checks) else ["PROVIDER_DOCTOR_NOT_READY"]


def _qualification_blocking_reasons(report: Mapping[str, Any]) -> list[str]:
    if report.get("_invalid_json") is True:
        return []
    if report.get("platform") != "macos":
        return ["MACOS_QUALIFICATION_REPORT_PLATFORM_MISMATCH"]
    return []


def _qualification_fail_reasons(report: Mapping[str, Any]) -> list[str]:
    if report.get("_invalid_json") is True:
        return ["MACOS_QUALIFICATION_REPORT_INVALID"]
    reasons: list[str] = []
    if report.get("platform") == "macos":
        status_ok = report.get("status") in {"pass", "controlled_pass"}
        qualification_ok = (
            report.get("qualificationPassed") is True
            or report.get("qualificationStatus") == "passed"
        )
        fixture_ok = report.get("fixtureQualified") is True
        if not (status_ok and qualification_ok and fixture_ok):
            reasons.append("MACOS_QUALIFICATION_REPORT_NOT_PASSING")
    if report.get("liveEnabled") is True or report.get("productionQualified") is True:
        reasons.append("PUBLIC_LIVE_CLAIM_NOT_ALLOWED")
    provider = _as_mapping(report.get("provider"))
    if provider and not (
        provider.get("ready") is True
        and provider.get("strictJson") is True
        and provider.get("strictJsonValidated") is True
    ):
        reasons.append("MACOS_QUALIFICATION_PROVIDER_NOT_READY")
    artifacts = _as_mapping(report.get("artifacts"))
    if artifacts and artifacts.get("screenshotHashesOnly") is False:
        reasons.append("RAW_SCREENSHOT_PERSISTENCE_DETECTED")
    return reasons


def _runtime_summary_fail_reasons(summary: Mapping[str, Any]) -> list[str]:
    if summary.get("_invalid_json") is True:
        return ["VISION_RUNTIME_SUMMARY_INVALID"]
    semantic = _as_mapping(summary.get("semantic_verification"))
    failed = _safe_int(semantic.get("failed"), default=0)
    satisfied = _safe_int(semantic.get("satisfied"), default=0)
    if failed > 0 or satisfied <= 0:
        return ["SEMANTIC_VERIFIER_NOT_VERIFIED"]
    if _safe_int(summary.get("no_progress_stops"), default=0) > 0:
        return ["VISION_NO_PROGRESS_STOP_DETECTED"]
    return []


def _replay_fail_reasons(
    qualification_report: Mapping[str, Any],
    replay_report: Mapping[str, Any],
) -> list[str]:
    if replay_report.get("_invalid_json") is True:
        return ["REPLAY_VERIFY_REPORT_INVALID"]
    replay_ok = (
        replay_report.get("verified") is True
        or replay_report.get("replayIntegrityVerified") is True
    )
    qualification_replay_ok = (
        qualification_report.get("replayIntegrityVerified") is True
        or qualification_report.get("replayIntegrityStatus") == "passed"
    )
    audit_ok = (
        replay_report.get("auditHashChainVerified") in {None, True}
        and qualification_report.get("auditHashChainVerified") in {None, True}
    )
    if replay_ok and qualification_replay_ok and audit_ok:
        return []
    return ["REPLAY_INTEGRITY_NOT_VERIFIED"]


def _platform_matrix_fail_reasons(matrix: Mapping[str, Any]) -> list[str]:
    if matrix.get("_invalid_json") is True:
        return ["PLATFORM_MATRIX_EVIDENCE_INVALID"]
    if matrix.get("status") != "pass":
        return ["PLATFORM_MATRIX_NOT_PASSING"]
    if matrix.get("liveAutomationDefault") is not False:
        return ["LIVE_AUTOMATION_DEFAULT_ENABLED"]
    if matrix.get("rawScreenshotPersistenceDefault") is not False:
        return ["RAW_SCREENSHOT_PERSISTENCE_DETECTED"]
    return []


def _safety_summary(payloads: Mapping[str, Any | None]) -> dict[str, Any]:
    qualification = _as_mapping(payloads.get("qualification_report"))
    runtime_summary = _as_mapping(payloads.get("runtime_summary"))
    replay_verify = _as_mapping(payloads.get("replay_verify"))
    platform_matrix = _as_mapping(payloads.get("platform_matrix"))
    qualification_safety = _as_mapping(qualification.get("safety"))
    qualification_artifacts = _as_mapping(qualification.get("artifacts"))
    runtime_semantic = _as_mapping(runtime_summary.get("semantic_verification"))

    raw_counts = [
        _safe_int(qualification_safety.get("rawScreenshotPersistedCount"), default=0),
        _safe_int(qualification_safety.get("rawScreenshotsPersisted"), default=0),
        _safe_int(qualification_artifacts.get("rawScreenshotCount"), default=0),
        _safe_int(runtime_summary.get("raw_screenshot_persisted"), default=0),
    ]
    raw_count = max(raw_counts)
    raw_persistence = (
        raw_count > 0
        or qualification_safety.get("rawScreenshotPersistence") is True
        or qualification_safety.get("rawScreenshotPersistenceDefault") is True
        or qualification_safety.get("rawScreenshotRetention") not in {None, "disabled"}
        or platform_matrix.get("rawScreenshotPersistenceDefault") is True
    )
    semantic_satisfied = _safe_int(runtime_semantic.get("satisfied"), default=0)
    semantic_failed = _safe_int(runtime_semantic.get("failed"), default=0)
    return {
        "raw_screenshot_persistence": raw_persistence,
        "raw_screenshot_count": raw_count,
        "sensitive_surface_stop_verified": _sensitive_surface_verified(qualification),
        "approval_freshness_verified": (
            qualification_safety.get("approvalFreshnessEnforced") is True
        ),
        "semantic_verifier_verified": semantic_satisfied > 0 and semantic_failed == 0,
        "replay_integrity_verified": (
            replay_verify.get("verified") is True
            or replay_verify.get("replayIntegrityVerified") is True
        )
        and (
            qualification.get("replayIntegrityVerified") is True
            or qualification.get("replayIntegrityStatus") == "passed"
        ),
    }


def _sensitive_surface_verified(qualification: Mapping[str, Any]) -> bool:
    safety = _as_mapping(qualification.get("safety"))
    if safety.get("sensitiveSurfaceBlocked") is True:
        return True
    fixtures = qualification.get("fixtures")
    if not isinstance(fixtures, list):
        return False
    for fixture in fixtures:
        item = _as_mapping(fixture)
        if item.get("id") != "sensitive_surface_stop":
            continue
        return (
            item.get("status") == "blocked_expected"
            and item.get("inputExecuted") is not True
            and item.get("osInputExecuted") is not True
        )
    return False


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
