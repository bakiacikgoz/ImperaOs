from pathlib import Path

from imperaos.authorization.action_manifest import ACTION_MANIFEST
from imperaos.enterprise.identity import ROLE_PERMISSIONS


def test_primary_manifest_permissions_exist_in_backend_roles() -> None:
    backend_permissions = set().union(*ROLE_PERMISSIONS.values())
    assert {item.permission for item in ACTION_MANIFEST.values()} <= backend_permissions | {
        "evidence.verify"
    }


def test_frontend_working_actions_match_canonical_manifest() -> None:
    source = Path("apps/operator-panel/src/routeCapabilityMatrix.ts").read_text(encoding="utf-8")
    for action in ACTION_MANIFEST.values():
        if action.bridge_command is None or f"actionId: '{action.action_id}'" not in source:
            continue
        assert f"actionId: '{action.action_id}'" in source
        assert f"requiredPermission: '{action.permission}'" in source
        assert f"bridgeCommand: '{action.bridge_command}'" in source
