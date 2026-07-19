from __future__ import annotations

import pytest

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import ArtifactDataClass, OperationContext, PrincipalType
from imperaos.artifacts.policy import (
    ArtifactPermission,
    ArtifactPolicyAction,
    ArtifactPolicyGateway,
)
from imperaos.enterprise.identity import ROLE_PERMISSIONS


def context(
    principal_type: PrincipalType,
    *roles: str,
    workspace_id: str = "workspace-1",
) -> OperationContext:
    return OperationContext(
        workspace_id=workspace_id,
        principal_type=principal_type,
        principal_id=f"{principal_type.value}-1",
        roles=roles,
        request_id="request-1",
    )


def test_viewer_is_read_only_and_editor_can_mutate_within_workspace() -> None:
    gateway = ArtifactPolicyGateway()

    viewer_read = gateway.decide(
        ArtifactPermission.READ,
        context(PrincipalType.USER, "artifact_viewer"),
        artifact_workspace_id="workspace-1",
    )
    viewer_update = gateway.decide(
        ArtifactPermission.UPDATE,
        context(PrincipalType.USER, "artifact_viewer"),
        artifact_workspace_id="workspace-1",
    )
    editor_update = gateway.decide(
        ArtifactPermission.UPDATE,
        context(PrincipalType.USER, "artifact_editor"),
        artifact_workspace_id="workspace-1",
    )

    assert viewer_read.action is ArtifactPolicyAction.ALLOW
    assert viewer_update.action is ArtifactPolicyAction.DENY
    assert editor_update.action is ArtifactPolicyAction.ALLOW


def test_cross_workspace_is_denied_before_role_permission() -> None:
    gateway = ArtifactPolicyGateway()

    decision = gateway.decide(
        ArtifactPermission.READ,
        context(PrincipalType.USER, "artifact_admin"),
        artifact_workspace_id="workspace-2",
    )

    assert decision.action is ArtifactPolicyAction.DENY
    assert decision.reason_code == "ARTIFACT_WORKSPACE_MISMATCH"


def test_assistant_can_propose_but_apply_requires_approval_and_export_is_denied() -> None:
    gateway = ArtifactPolicyGateway()
    assistant = context(PrincipalType.ASSISTANT, "artifact_editor")

    proposal = gateway.decide(ArtifactPermission.AI_PROPOSE, assistant)
    apply_without_approval = gateway.decide(ArtifactPermission.AI_APPLY, assistant)
    apply_with_approval = gateway.decide(
        ArtifactPermission.AI_APPLY,
        assistant,
        approval_granted=True,
    )
    export = gateway.decide(
        ArtifactPermission.EXPORT,
        assistant,
        approval_granted=True,
    )

    assert proposal.action is ArtifactPolicyAction.ALLOW
    assert apply_without_approval.action is ArtifactPolicyAction.REQUIRE_APPROVAL
    assert apply_with_approval.action is ArtifactPolicyAction.ALLOW
    assert export.action is ArtifactPolicyAction.DENY


def test_policy_is_fail_closed_when_unavailable_or_role_is_unknown() -> None:
    unavailable = ArtifactPolicyGateway(policy_available=False)
    gateway = ArtifactPolicyGateway()

    with pytest.raises(ArtifactDomainError) as unavailable_error:
        unavailable.authorize(
            ArtifactPermission.READ,
            context(PrincipalType.USER, "artifact_admin"),
        )
    with pytest.raises(ArtifactDomainError) as unknown_role_error:
        gateway.authorize(
            ArtifactPermission.UPDATE,
            context(PrincipalType.USER, "unknown_role"),
        )

    assert unavailable_error.value.code is ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE
    assert unknown_role_error.value.code is ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED


def test_classification_downgrade_is_denied_and_regulated_export_requires_approval() -> None:
    gateway = ArtifactPolicyGateway()
    admin = context(PrincipalType.USER, "artifact_admin")

    downgrade = gateway.decide(
        ArtifactPermission.UPDATE,
        admin,
        current_data_class=ArtifactDataClass.CONFIDENTIAL,
        target_data_class=ArtifactDataClass.INTERNAL,
    )
    regulated_export = gateway.decide(
        ArtifactPermission.EXPORT,
        admin,
        current_data_class=ArtifactDataClass.REGULATED,
    )
    approved_export = gateway.decide(
        ArtifactPermission.EXPORT,
        admin,
        current_data_class=ArtifactDataClass.REGULATED,
        approval_granted=True,
    )

    assert downgrade.action is ArtifactPolicyAction.DENY
    assert downgrade.reason_code == "ARTIFACT_CLASSIFICATION_DOWNGRADE_DENIED"
    assert regulated_export.action is ArtifactPolicyAction.REQUIRE_APPROVAL
    assert approved_export.action is ArtifactPolicyAction.ALLOW


def test_enterprise_identity_roles_publish_artifact_permissions() -> None:
    assert {permission.value for permission in ArtifactPermission} <= ROLE_PERMISSIONS[
        "artifact_admin"
    ]
    assert ROLE_PERMISSIONS["artifact_viewer"] == {ArtifactPermission.READ.value}
    assert ArtifactPermission.UPDATE.value in ROLE_PERMISSIONS["operator"]
