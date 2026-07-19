from imperaos.experts.code_lite import CodeLiteExpert
from imperaos.schemas.models import ExpertRequest, TaskType


def test_code_lite_expert_returns_snippet() -> None:
    expert = CodeLiteExpert()
    req = ExpertRequest(
        request_id="r1",
        task_type=TaskType.CODE,
        intent="code_fix",
        user_input="Python'da unique ve sort yapan fonksiyon ver",
        context={},
        latency_budget_ms=1000,
    )

    result = expert.run(req)

    assert result.expert_name == "code_expert"
    assert result.status.value == "ok"
    assert "candidate_snippet" in result.payload
