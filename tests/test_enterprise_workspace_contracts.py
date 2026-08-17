from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from imperaos.control_plane.agent_enrollment import AgentEnrollmentToken
from imperaos.control_plane.enterprise_workspace import (
    EnterpriseOrganization,
    EnterpriseWorkspaceSnapshot,
)


def test_enterprise_workspace_schema_generator_writes_contracts() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/generate_enterprise_workspace_contract_schemas.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    root = Path("contracts/control_plane")
    assert json.loads((root / "enterprise_organization.schema.json").read_text())["title"] == (
        "EnterpriseOrganization"
    )
    assert (root / "enterprise_workspace.schema.json").exists()
    assert (root / "enterprise_principal.schema.json").exists()
    assert (root / "enterprise_membership.schema.json").exists()
    assert (root / "enterprise_device.schema.json").exists()
    assert (root / "agent_enrollment_token.schema.json").exists()
    assert (root / "agent_enrollment_request.schema.json").exists()
    assert (root / "agent_enrollment_decision.schema.json").exists()
    assert (root / "enrolled_agent.schema.json").exists()
    assert (root / "enterprise_workspace_snapshot.schema.json").exists()
    assert (root / "workspace_permission_decision.schema.json").exists()


def test_enterprise_workspace_fixtures_match_contract_models() -> None:
    root = Path("contracts/control_plane/fixtures")
    organization = json.loads((root / "enterprise_workspace_bootstrap_pass.json").read_text())
    token = json.loads((root / "agent_enrollment_token_pass.json").read_text())
    snapshot = json.loads((root / "enterprise_workspace_snapshot_ready.json").read_text())

    assert EnterpriseOrganization.model_validate(organization["organization"]).organization_id == (
        "local-org"
    )
    token_model = AgentEnrollmentToken.model_validate(token["token"])
    assert "rawToken" not in token_model.model_dump(mode="json", by_alias=True)
    assert EnterpriseWorkspaceSnapshot.model_validate(snapshot).status == "ready"
    assert "shown-once-token-test-value" not in json.dumps(snapshot)


def test_enterprise_workspace_raw_token_leak_fixture_is_negative_only() -> None:
    leak_fixture = json.loads(
        Path("contracts/control_plane/fixtures/agent_enrollment_raw_token_leak_fail.json").read_text()
    )

    with pytest.raises(ValidationError):
        AgentEnrollmentToken.model_validate(leak_fixture["token"])
    assert leak_fixture["expectedFailure"] == "RAW_TOKEN_FIELD_FORBIDDEN"
