from __future__ import annotations

import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from imperaos.control_plane.agent_enrollment import (
    AgentEnrollmentTokenCreateRequest,
    create_enrollment_token,
)
from imperaos.control_plane.enterprise_workspace import (
    EnterpriseWorkspaceBootstrapRequest,
    bootstrap_enterprise_workspace,
)
from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore
from imperaos.runtime.config import RuntimeConfig

REPO_ROOT = Path(__file__).resolve().parents[1]


def _prepare(root: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "prepare_enterprise_fixture.py"),
            "--root",
            str(root),
            "--permission",
            "workspace.bootstrap",
            "--permission",
            "agent.enrollment.create",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_enrollment_token_evidence_is_hash_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _prepare(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    bootstrap_enterprise_workspace(
        config=config,
        request=EnterpriseWorkspaceBootstrapRequest(
            organizationId="local-org",
            workspaceId="pilot-workspace",
            displayName="Pilot Workspace",
        ),
    )
    from imperaos.enterprise.identity import resolve_actor_context

    result = create_enrollment_token(
        config=config,
        actor=resolve_actor_context(config),
        request=AgentEnrollmentTokenCreateRequest(
            workspaceId="pilot-workspace",
            intendedAgentId="ops-agent",
            intendedDeviceLabel="ops-host-01",
            allowedCapabilities=("read",),
            ttlMinutes=15,
        ),
    )

    assert result.raw_token is not None
    evidence = (tmp_path / ".imperaos" / "control-plane" / result.evidence_ref).read_text(
        encoding="utf-8"
    )
    stored_token = EnterpriseWorkspaceStore().get_enrollment_token(result.token_id)
    assert stored_token.expires_at_utc - stored_token.created_at_utc <= timedelta(minutes=15)
    assert result.raw_token not in evidence
    assert "rawToken" not in evidence
