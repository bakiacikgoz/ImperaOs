from imperaos.memory.semantic.index_router import (
    AllowedSemanticScope,
    build_semantic_query_plan,
    parse_requested_scope,
)


def test_query_plan_blocks_without_allowed_scopes() -> None:
    plan = build_semantic_query_plan(
        allowed_scopes=(),
        denied_reason_codes=("MEMORY_SCOPE_DENIED",),
    )

    assert plan.status == "blocked"
    assert plan.reason_codes == ("MEMORY_SCOPE_DENIED",)


def test_query_plan_accepts_allowed_scope() -> None:
    plan = build_semantic_query_plan(
        allowed_scopes=(AllowedSemanticScope("personal", "agent-local", "ok"),),
        denied_reason_codes=(),
    )

    assert plan.status == "pass"
    assert parse_requested_scope("personal:agent-local") == ("personal", "agent-local")
