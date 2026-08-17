from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.agent_enrollment import EnrolledAgent
from imperaos.control_plane.enterprise_workspace import utc_now
from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore
from imperaos.control_plane.external_contracts import ExternalActionRequest
from imperaos.control_plane.external_gateway import ExternalAgentGateway
from imperaos.control_plane.registry import AgentRegistry, load_agent_spec
from imperaos.runtime.config import RuntimeConfig


FIXTURES = [
    ("read_only", "external_agent_read_only_request.json", "accepted"),
    (
        "mutation_requires_approval",
        "external_agent_mutation_requires_approval.json",
        "blocked_pending_approval",
    ),
    ("denied_destructive", "external_agent_denied_destructive.json", "denied"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run External Agent Gateway smoke flow.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument(
        "--root-dir",
        default="artifacts/design-partner-rc/external-gateway/control-plane",
    )
    parser.add_argument(
        "--output",
        default="artifacts/design-partner-rc/external_gateway_smoke.json",
    )
    parser.add_argument(
        "--agent-spec",
        default="examples/control_plane/agent_external_gateway.yaml",
    )
    args = parser.parse_args()

    root_dir = REPO_ROOT / args.root_dir
    output = REPO_ROOT / args.output
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")

    config = RuntimeConfig.from_profile(args.profile)
    config.governance.approval_store_path = str(root_dir / "approvals.sqlite")
    registry = AgentRegistry(root_dir=root_dir)
    registered = registry.register(
        load_agent_spec(REPO_ROOT / args.agent_spec),
        actor="smoke:external-gateway",
    )
    _bind_active_enrollment(registry=registry, root_dir=root_dir)
    gateway = ExternalAgentGateway(config=config, registry=registry, root_dir=root_dir)

    cases: list[dict[str, Any]] = []
    for label, fixture_name, expected_status in FIXTURES:
        fixture_path = REPO_ROOT / "contracts" / "control_plane" / "fixtures" / fixture_name
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        payload["requestId"] = f"{payload['requestId']}-{timestamp}"
        request = ExternalActionRequest.model_validate(payload)
        response = gateway.submit_action(request)
        cases.append(
            {
                "case": label,
                "fixture": str(fixture_path.relative_to(REPO_ROOT)),
                "expectedStatus": expected_status,
                "status": response.status,
                "reasonCode": response.reason_code,
                "runId": response.run_id,
                "approvalId": response.approval_id,
                "evidenceRef": response.evidence_ref,
                "passed": response.status == expected_status,
            }
        )

    result = {
        "version": "control-plane.external-gateway-smoke/v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "status": "pass" if all(item["passed"] for item in cases) else "fail",
        "registeredAgent": registered.agent_id,
        "rootDir": str(root_dir.relative_to(REPO_ROOT)),
        "cases": cases,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    if result["status"] != "pass":
        raise SystemExit(1)


def _bind_active_enrollment(*, registry: AgentRegistry, root_dir: Path) -> None:
    record = registry.get("external-agent")
    registry.update_record(
        record.model_copy(
            update={
                "spec": record.spec.model_copy(
                    update={
                        "metadata": {
                            **record.spec.metadata,
                            "workspace_id": "pilot-workspace",
                            "principal_id": "principal-agent",
                            "device_id": "device-host-01",
                            "enrollment_id": "enr-test",
                            "enrollment_status": "active",
                        }
                    }
                )
            }
        )
    )
    EnterpriseWorkspaceStore(root_dir).write_enrolled_agent(
        EnrolledAgent(
            enrollmentId="enr-test",
            workspaceId="pilot-workspace",
            agentId="external-agent",
            principalId="principal-agent",
            deviceId="device-host-01",
            tokenId="enrtok-test",
            status="active",
            capabilities=("read", "external_write"),
            policyProfile="enterprise",
            createdAtUtc=utc_now(),
        )
    )


if __name__ == "__main__":
    main()
