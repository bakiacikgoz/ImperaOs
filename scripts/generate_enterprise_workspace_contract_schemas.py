from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.agent_enrollment import (  # noqa: E402
    AgentEnrollmentDecision,
    AgentEnrollmentRequest,
    AgentEnrollmentToken,
    EnrolledAgent,
)
from imperaos.control_plane.enterprise_rbac import WorkspacePermissionDecision  # noqa: E402
from imperaos.control_plane.enterprise_workspace import (  # noqa: E402
    EnterpriseDevice,
    EnterpriseOrganization,
    EnterprisePrincipal,
    EnterpriseWorkspace,
    EnterpriseWorkspaceMembership,
    EnterpriseWorkspaceSnapshot,
)

SCHEMAS = {
    "enterprise_organization": EnterpriseOrganization,
    "enterprise_workspace": EnterpriseWorkspace,
    "enterprise_principal": EnterprisePrincipal,
    "enterprise_membership": EnterpriseWorkspaceMembership,
    "enterprise_device": EnterpriseDevice,
    "agent_enrollment_token": AgentEnrollmentToken,
    "agent_enrollment_request": AgentEnrollmentRequest,
    "agent_enrollment_decision": AgentEnrollmentDecision,
    "enrolled_agent": EnrolledAgent,
    "enterprise_workspace_snapshot": EnterpriseWorkspaceSnapshot,
    "workspace_permission_decision": WorkspacePermissionDecision,
}


def main() -> None:
    root = REPO_ROOT / "contracts" / "control_plane"
    root.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMAS.items():
        (root / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
