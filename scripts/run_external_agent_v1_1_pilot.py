from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.external_contracts import ExternalAgentRequestV11
from imperaos.control_plane.external_gateway import ExternalAgentGateway
from imperaos.control_plane.registry import AgentRegistry, load_agent_spec
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Run External Agent Gateway v1.1 pilot suite.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--examples-root", default="examples/external_agents/v1_1")
    parser.add_argument(
        "--root-dir",
        default="artifacts/external-agent-v1-1/control-plane",
    )
    parser.add_argument("--output", default="artifacts/external-agent-v1-1/results.json")
    parser.add_argument("--markdown", default="artifacts/external-agent-v1-1/RESULTS.md")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root_dir = REPO_ROOT / args.root_dir
    if root_dir.exists():
        shutil.rmtree(root_dir)
    config = RuntimeConfig.from_profile(args.profile)
    config.governance.approval_store_path = str(root_dir / "approvals.sqlite3")
    registry = AgentRegistry(root_dir=root_dir)
    registry.register(
        load_agent_spec(REPO_ROOT / "examples/control_plane/agent_external_gateway.yaml"),
        actor="external-agent-v1-1-pilot",
    )
    gateway = ExternalAgentGateway(config=config, registry=registry, root_dir=root_dir)

    report = run_suite(
        gateway=gateway,
        examples_root=REPO_ROOT / args.examples_root,
        root_dir=root_dir,
    )
    output_path = REPO_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path = REPO_ROOT / args.markdown
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(report["status"])
    if report["status"] != "pass":
        raise SystemExit(1)


def run_suite(
    *,
    gateway: ExternalAgentGateway,
    examples_root: Path,
    root_dir: Path,
) -> dict[str, Any]:
    expected = {
        "read_only_inspector": ("accepted", "allow"),
        "approval_required_writer": ("blocked_pending_approval", "require_approval"),
        "destructive_denied_agent": ("denied", "deny"),
    }
    cases: list[dict[str, Any]] = []
    requests: dict[str, ExternalAgentRequestV11] = {}
    first_results: dict[str, Any] = {}
    for request_path in sorted(examples_root.glob("*.json")):
        case_name = request_path.stem
        request = ExternalAgentRequestV11.model_validate(
            json.loads(request_path.read_text(encoding="utf-8"))
        )
        requests[case_name] = request
        response = gateway.submit_action_v1_1(request)
        expected_status, expected_decision = expected[case_name]
        first_results[case_name] = response
        cases.append(
            {
                "case": case_name,
                "requestId": response.request_id,
                "status": response.status,
                "expectedStatus": expected_status,
                "policyDecision": response.policy_decision,
                "expectedPolicyDecision": expected_decision,
                "reasonCode": response.reason_code,
                "runId": response.run_id,
                "approvalId": response.approval_id,
                "evidenceRef": response.evidence_ref,
                "replayStatus": response.replay_status,
                "idempotencyStatus": response.idempotency_status,
                "passed": response.status == expected_status
                and response.policy_decision == expected_decision,
            }
        )

    read_request = requests["read_only_inspector"]
    first_read = first_results["read_only_inspector"]
    duplicate = gateway.submit_action_v1_1(read_request)
    cases.append(
        {
            "case": "idempotent_replay",
            "requestId": duplicate.request_id,
            "status": duplicate.status,
            "replayStatus": duplicate.replay_status,
            "idempotencyStatus": duplicate.idempotency_status,
            "runIdStable": duplicate.run_id == first_read.run_id,
            "passed": duplicate.status == "accepted"
            and duplicate.replay_status == "replayed"
            and duplicate.run_id == first_read.run_id,
        }
    )

    conflict_request = read_request.model_copy(update={"intent": f"{read_request.intent} Changed."})
    conflict = gateway.submit_action_v1_1(conflict_request)
    cases.append(
        {
            "case": "idempotency_conflict",
            "requestId": conflict.request_id,
            "status": conflict.status,
            "reasonCode": conflict.reason_code,
            "replayStatus": conflict.replay_status,
            "idempotencyStatus": conflict.idempotency_status,
            "passed": conflict.status == "invalid_request"
            and conflict.reason_code == "EXTERNAL_AGENT_DUPLICATE_REQUEST",
        }
    )

    verified = gateway.replay_v1_1(
        request_id=read_request.request_id,
        expected_request_hash=first_read.request_hash,
    )
    mismatch = gateway.replay_v1_1(
        request_id=read_request.request_id,
        expected_request_hash="sha256:mismatch",
    )
    cases.append(
        {
            "case": "replay_verify",
            "requestId": read_request.request_id,
            "status": verified["status"],
            "mismatchStatus": mismatch["status"],
            "passed": verified["status"] == "verified" and mismatch["status"] == "mismatch",
        }
    )

    return {
        "version": "control-plane.external-agent-v1-1-pilot/v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "status": "pass" if cases and all(case["passed"] for case in cases) else "fail",
        "rootDir": str(root_dir),
        "cases": cases,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# External Agent Gateway v1.1 Pilot Results",
        "",
        f"- Status: `{report['status']}`",
        f"- Generated at UTC: `{report['generatedAtUtc']}`",
        f"- Root dir: `{report['rootDir']}`",
        "",
        "| Case | Status | Decision | Result |",
        "|---|---|---|---|",
    ]
    for case in report["cases"]:
        lines.append(
            "| {case} | {status} | {decision} | {result} |".format(
                case=case["case"],
                status=case.get("status", ""),
                decision=case.get("policyDecision", ""),
                result="pass" if case["passed"] else "fail",
            )
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
