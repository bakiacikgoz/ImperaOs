from __future__ import annotations

from dataclasses import dataclass

from imperaos.memory.workspace_models import WorkspaceScopeType


@dataclass(frozen=True, slots=True)
class AllowedSemanticScope:
    scope_type: WorkspaceScopeType
    scope_id: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class SemanticQueryPlan:
    status: str
    scopes: tuple[AllowedSemanticScope, ...]
    reason_codes: tuple[str, ...]


def parse_requested_scope(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise ValueError("requested scope must use scope_type:scope_id")
    scope_type, scope_id = value.split(":", 1)
    if not scope_type or not scope_id:
        raise ValueError("requested scope must include scope_type and scope_id")
    return scope_type, scope_id


def build_semantic_query_plan(
    *,
    allowed_scopes: tuple[AllowedSemanticScope, ...],
    denied_reason_codes: tuple[str, ...],
) -> SemanticQueryPlan:
    if not allowed_scopes:
        return SemanticQueryPlan(
            status="blocked",
            scopes=(),
            reason_codes=denied_reason_codes or ("MEMORY_SCOPE_DENIED",),
        )
    return SemanticQueryPlan(status="pass", scopes=allowed_scopes, reason_codes=())
