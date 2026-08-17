from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import (
    ArtifactDataClass,
    OperationContext,
    PrincipalType,
    can_transition_data_class,
)


class ArtifactPermission(StrEnum):
    READ = "artifact.read"
    CREATE = "artifact.create"
    UPDATE = "artifact.update"
    RESTORE = "artifact.restore"
    ARCHIVE = "artifact.archive"
    DUPLICATE = "artifact.duplicate"
    EXPORT = "artifact.export"
    ASSET_IMPORT = "artifact.asset.import"
    IMPORT_EVIDENCE = "artifact.import_evidence"
    FORM_SUBMIT = "artifact.form.submit"
    AI_PROPOSE = "artifact.ai.propose"
    AI_APPLY = "artifact.ai.apply"


class ArtifactPolicyAction(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass(frozen=True, slots=True)
class ArtifactPolicyDecision:
    permission: ArtifactPermission
    action: ArtifactPolicyAction
    reason_code: str
    approval_required: bool = False


_VIEWER_PERMISSIONS = {ArtifactPermission.READ}
_EDITOR_PERMISSIONS = _VIEWER_PERMISSIONS | {
    ArtifactPermission.CREATE,
    ArtifactPermission.UPDATE,
    ArtifactPermission.RESTORE,
    ArtifactPermission.DUPLICATE,
    ArtifactPermission.EXPORT,
    ArtifactPermission.ASSET_IMPORT,
    ArtifactPermission.IMPORT_EVIDENCE,
    ArtifactPermission.FORM_SUBMIT,
    ArtifactPermission.AI_PROPOSE,
}
_ADMIN_PERMISSIONS = set(ArtifactPermission)
ROLE_ARTIFACT_PERMISSIONS: dict[str, frozenset[ArtifactPermission]] = {
    "artifact_viewer": frozenset(_VIEWER_PERMISSIONS),
    "artifact_editor": frozenset(_EDITOR_PERMISSIONS),
    "artifact_admin": frozenset(_ADMIN_PERMISSIONS),
    "observer": frozenset(_VIEWER_PERMISSIONS),
    "auditor": frozenset(_VIEWER_PERMISSIONS),
    "operator": frozenset(_EDITOR_PERMISSIONS | {ArtifactPermission.ARCHIVE}),
    "platform_admin": frozenset(_ADMIN_PERMISSIONS),
    "security_admin": frozenset(
        _VIEWER_PERMISSIONS | {ArtifactPermission.AI_APPLY}
    ),
    "policy_admin": frozenset(_VIEWER_PERMISSIONS),
}

_ASSISTANT_ALWAYS_DENIED = {
    ArtifactPermission.UPDATE,
    ArtifactPermission.RESTORE,
    ArtifactPermission.ARCHIVE,
    ArtifactPermission.DUPLICATE,
    ArtifactPermission.EXPORT,
    ArtifactPermission.ASSET_IMPORT,
    ArtifactPermission.IMPORT_EVIDENCE,
    ArtifactPermission.FORM_SUBMIT,
}


class ArtifactPolicyGateway:
    def __init__(self, *, policy_available: bool = True) -> None:
        self.policy_available = policy_available

    def decide(
        self,
        permission: ArtifactPermission,
        context: OperationContext,
        *,
        artifact_workspace_id: str | None = None,
        current_data_class: ArtifactDataClass | None = None,
        target_data_class: ArtifactDataClass | None = None,
        approval_granted: bool = False,
    ) -> ArtifactPolicyDecision:
        if not self.policy_available:
            return self._decision(
                permission,
                ArtifactPolicyAction.DENY,
                "ARTIFACT_POLICY_UNAVAILABLE",
            )
        if (
            artifact_workspace_id is not None
            and artifact_workspace_id != context.workspace_id
        ):
            return self._decision(
                permission,
                ArtifactPolicyAction.DENY,
                "ARTIFACT_WORKSPACE_MISMATCH",
            )
        if (
            current_data_class is not None
            and target_data_class is not None
            and not can_transition_data_class(current_data_class, target_data_class)
        ):
            return self._decision(
                permission,
                ArtifactPolicyAction.DENY,
                "ARTIFACT_CLASSIFICATION_DOWNGRADE_DENIED",
            )

        if context.principal_type is PrincipalType.ASSISTANT:
            assistant_decision = self._decide_assistant(
                permission,
                context,
                approval_granted=approval_granted,
            )
            if assistant_decision is not None:
                return assistant_decision

        allowed_permissions = self._permissions_for_roles(context.roles)
        if permission not in allowed_permissions:
            return self._decision(
                permission,
                ArtifactPolicyAction.DENY,
                "ARTIFACT_PERMISSION_DENIED",
            )
        if (
            permission is ArtifactPermission.EXPORT
            and current_data_class is ArtifactDataClass.REGULATED
            and not approval_granted
        ):
            return self._decision(
                permission,
                ArtifactPolicyAction.REQUIRE_APPROVAL,
                "ARTIFACT_REGULATED_EXPORT_APPROVAL_REQUIRED",
                approval_required=True,
            )
        return self._decision(
            permission,
            ArtifactPolicyAction.ALLOW,
            "ARTIFACT_POLICY_ALLOW",
        )

    def authorize(
        self,
        permission: ArtifactPermission,
        context: OperationContext,
        **decision_inputs: object,
    ) -> ArtifactPolicyDecision:
        decision = self.decide(permission, context, **decision_inputs)
        if decision.action is ArtifactPolicyAction.ALLOW:
            return decision
        if decision.reason_code == "ARTIFACT_POLICY_UNAVAILABLE":
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE,
                "artifact policy is unavailable and fail-closed",
            )
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
            "artifact operation is not authorized",
            details={
                "permission": permission.value,
                "reasonCode": decision.reason_code,
                "approvalRequired": decision.approval_required,
            },
        )

    def _decide_assistant(
        self,
        permission: ArtifactPermission,
        context: OperationContext,
        *,
        approval_granted: bool,
    ) -> ArtifactPolicyDecision | None:
        if permission in _ASSISTANT_ALWAYS_DENIED:
            return self._decision(
                permission,
                ArtifactPolicyAction.DENY,
                "ARTIFACT_AI_DIRECT_ACTION_DENIED",
            )
        if permission in {ArtifactPermission.AI_PROPOSE, ArtifactPermission.CREATE}:
            return self._decision(
                permission,
                ArtifactPolicyAction.ALLOW,
                "ARTIFACT_AI_PROPOSAL_ALLOW",
            )
        if permission is ArtifactPermission.AI_APPLY:
            allowed_permissions = self._permissions_for_roles(context.roles)
            if ArtifactPermission.UPDATE not in allowed_permissions:
                return self._decision(
                    permission,
                    ArtifactPolicyAction.DENY,
                    "ARTIFACT_PERMISSION_DENIED",
                )
            if not approval_granted:
                return self._decision(
                    permission,
                    ArtifactPolicyAction.REQUIRE_APPROVAL,
                    "ARTIFACT_AI_APPLY_APPROVAL_REQUIRED",
                    approval_required=True,
                )
            return self._decision(
                permission,
                ArtifactPolicyAction.ALLOW,
                "ARTIFACT_APPROVAL_SATISFIED",
            )
        return None

    @staticmethod
    def _permissions_for_roles(roles: tuple[str, ...]) -> set[ArtifactPermission]:
        permissions: set[ArtifactPermission] = set()
        for role in roles:
            permissions.update(ROLE_ARTIFACT_PERMISSIONS.get(role, ()))
        return permissions

    @staticmethod
    def _decision(
        permission: ArtifactPermission,
        action: ArtifactPolicyAction,
        reason_code: str,
        *,
        approval_required: bool = False,
    ) -> ArtifactPolicyDecision:
        return ArtifactPolicyDecision(
            permission=permission,
            action=action,
            reason_code=reason_code,
            approval_required=approval_required,
        )
