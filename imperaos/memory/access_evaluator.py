from __future__ import annotations

from imperaos.memory.workspace_models import (
    MemoryAccessDecision,
    MemoryAccessRequest,
    MemoryScopeAclRule,
)
from imperaos.memory.workspace_store import WorkspaceMemoryStore

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {
        "memory.read.personal",
        "memory.write.personal",
        "memory.read.agent",
        "memory.write.agent",
        "memory.read.team",
        "memory.write.team",
        "memory.read.project",
        "memory.write.project",
        "memory.read.case",
        "memory.write.case",
        "memory.read.organization",
        "memory.write.organization",
        "memory.admin.acl",
        "memory.admin.sync",
        "memory.admin.retention",
        "memory.audit.read",
    },
    "admin": {
        "memory.read.team",
        "memory.write.team",
        "memory.read.project",
        "memory.write.project",
        "memory.read.case",
        "memory.write.case",
        "memory.admin.acl",
        "memory.admin.sync",
        "memory.admin.retention",
        "memory.audit.read",
    },
    "operator": {
        "memory.read.team",
        "memory.read.project",
        "memory.read.case",
        "memory.admin.sync",
        "memory.audit.read",
    },
    "agent": {
        "memory.read.agent",
        "memory.write.agent",
    },
    "viewer": {
        "memory.read.team",
        "memory.read.project",
        "memory.read.case",
    },
    "auditor": {
        "memory.audit.read",
    },
}


class MemoryAccessEvaluator:
    def __init__(self, *, store: WorkspaceMemoryStore):
        self.store = store

    def evaluate(self, request: MemoryAccessRequest) -> MemoryAccessDecision:
        workspace = self.store.get_workspace(request.workspace_id)
        if workspace is None:
            return _deny("MEMORY_WORKSPACE_UNKNOWN")
        if workspace.status != "active":
            return _deny("MEMORY_WORKSPACE_NOT_ACTIVE")
        principal = self.store.get_principal(request.principal_id)
        if principal is None:
            return _deny("MEMORY_PRINCIPAL_UNKNOWN")
        if principal.status != "active":
            return _deny("MEMORY_PRINCIPAL_DISABLED")
        if request.classification == "secret_like":
            return _deny("MEMORY_CLASSIFICATION_SECRET_LIKE_DENIED")

        membership = self.store.get_membership(
            workspace_id=request.workspace_id,
            principal_id=request.principal_id,
        )
        if membership is None or membership.status != "active":
            if _personal_owner_shortcut(request):
                return _allow("MEMORY_PERSONAL_OWNER_ALLOWED", ("personal_owner",))
            return _deny("MEMORY_MEMBERSHIP_MISSING")

        if _personal_owner_shortcut(request):
            return _allow("MEMORY_PERSONAL_OWNER_ALLOWED", ("personal_owner",))

        rules = self.store.acl_rules(
            workspace_id=request.workspace_id,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
        )
        matching_rules = [
            rule for rule in rules if _rule_matches(rule, request, set(membership.roles))
        ]
        for rule in matching_rules:
            if rule.effect == "deny":
                return _deny("MEMORY_SCOPE_ACL_DENY", (rule.acl_id,))
        for rule in matching_rules:
            if rule.effect == "allow":
                return _shared_scope_decision(request, rule.acl_id)

        if request.permission in _role_permissions(set(membership.roles)):
            return _shared_scope_decision(request, "role_default")

        return _deny("MEMORY_SCOPE_ACL_MISSING")


def _rule_matches(
    rule: MemoryScopeAclRule,
    request: MemoryAccessRequest,
    roles: set[str],
) -> bool:
    if request.permission not in rule.permissions:
        return False
    if rule.principal_id is not None and rule.principal_id == request.principal_id:
        return True
    return rule.role is not None and rule.role in roles


def _personal_owner_shortcut(request: MemoryAccessRequest) -> bool:
    return (
        request.scope_type == "personal"
        and request.scope_id == request.principal_id
        and request.permission in {"memory.read.personal", "memory.write.personal"}
    )


def _role_permissions(roles: set[str]) -> set[str]:
    permissions: set[str] = set()
    for role in roles:
        permissions.update(ROLE_PERMISSIONS.get(role, set()))
    return permissions


def _shared_scope_decision(request: MemoryAccessRequest, rule: str) -> MemoryAccessDecision:
    if request.action == "write" and request.scope_type == "organization":
        return MemoryAccessDecision(
            action="requires_approval",
            reasonCode="MEMORY_ORGANIZATION_WRITE_APPROVAL_REQUIRED",
            matchedRules=(rule,),
            requiresApproval=True,
        )
    if request.action == "write" and request.scope_type in {"team", "project", "case"}:
        return MemoryAccessDecision(
            action="proposal_only",
            reasonCode="MEMORY_SHARED_WRITE_PROPOSAL_ONLY",
            matchedRules=(rule,),
        )
    return _allow("MEMORY_ACCESS_ALLOWED", (rule,))


def _allow(reason: str, matched: tuple[str, ...]) -> MemoryAccessDecision:
    return MemoryAccessDecision(
        action="allow",
        reasonCode=reason,
        matchedRules=matched,
    )


def _deny(reason: str, matched: tuple[str, ...] = ()) -> MemoryAccessDecision:
    return MemoryAccessDecision(
        action="deny",
        reasonCode=reason,
        matchedRules=matched,
    )
