from __future__ import annotations

from typing import Any

from imperaos.experts.code_expert import CodeExpert
from imperaos.runtime.config import CodeVerifyConfig
from imperaos.schemas.models import ExpertRequest, ExpertStatus, TaskType
from imperaos.tools.code_verify import verify_python_snippet


def _request(text: str) -> ExpertRequest:
    return ExpertRequest(
        request_id="code-loop-1",
        task_type=TaskType.CODE,
        intent="bugfix",
        user_input=text,
        context={},
        latency_budget_ms=2_000,
    )


def test_verify_python_snippet_reports_syntax_error() -> None:
    result = verify_python_snippet(
        "def broken(:\n    pass\n",
        run_lint=False,
        run_test_collect=False,
    )

    assert result["parse_ok"] is False
    assert int(result["stage_reached"]) == 0
    assert result["failure_reason"] in {"SYNTAX_INVALID", "INDENTATION_ERROR"}


def test_verify_python_snippet_collects_tests_with_python_module(monkeypatch) -> None:
    commands: list[list[str]] = []

    class FakeRunner:
        def __init__(self, **_: Any) -> None:
            pass

        def run(self, command: list[str]) -> Any:
            commands.append(command)

            class Result:
                exit_code = 0
                stdout = ""
                stderr = ""

            return Result()

    monkeypatch.setattr("imperaos.tools.code_verify.SandboxRunner", FakeRunner)

    result = verify_python_snippet(
        "def ok():\n    return 1\n",
        run_lint=False,
        run_test_collect=True,
    )

    assert result["tests_ok"] is True
    assert [
        "uv",
        "run",
        "--extra",
        "dev",
        "python",
        "-m",
        "pytest",
        "--collect-only",
        "-q",
    ] in commands


def test_code_expert_retries_and_recovers(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_verify(_: str, **__: Any) -> dict[str, Any]:
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "parse_ok": False,
                "lint_ok": None,
                "tests_ok": None,
                "stage_reached": 1,
                "failure_reason": "SYNTAX_INVALID",
                "retry_count": 0,
                "retry_strategy": "failure_aware",
                "details": {},
            }
        return {
            "parse_ok": True,
            "lint_ok": True,
            "tests_ok": True,
            "stage_reached": 5,
            "failure_reason": None,
            "retry_count": 0,
            "retry_strategy": "failure_aware",
            "details": {},
        }

    monkeypatch.setattr("imperaos.experts.code_expert.verify_python_snippet", fake_verify)

    expert = CodeExpert(
        verify_config=CodeVerifyConfig(
            enabled=True,
            lint_enabled=True,
            test_collect_enabled=True,
            targeted_tests_enabled=True,
            timeout_s=10,
            retry_max=1,
            retry_strategy="failure_aware",
        )
    )
    result = expert.run(_request("runtime error fix"))

    assert result.status == ExpertStatus.OK
    assert calls["count"] == 2
    verification = result.payload["verification"]
    assert int(verification["retry_count"]) == 1
    assert int(verification["stage_reached"]) == 5


def test_code_expert_returns_partial_after_retry_exhausted(monkeypatch) -> None:
    def always_fail(_: str, **__: Any) -> dict[str, Any]:
        return {
            "parse_ok": True,
            "lint_ok": True,
            "tests_ok": False,
            "stage_reached": 4,
            "failure_reason": "TARGETED_TEST_FAILED",
            "retry_count": 0,
            "retry_strategy": "failure_aware",
            "details": {},
        }

    monkeypatch.setattr("imperaos.experts.code_expert.verify_python_snippet", always_fail)

    expert = CodeExpert(
        verify_config=CodeVerifyConfig(
            enabled=True,
            lint_enabled=True,
            test_collect_enabled=True,
            targeted_tests_enabled=True,
            timeout_s=10,
            retry_max=1,
            retry_strategy="failure_aware",
        )
    )
    result = expert.run(_request("runtime error fix"))

    assert result.status == ExpertStatus.PARTIAL
    verification = result.payload["verification"]
    assert int(verification["retry_count"]) == 1
    assert verification["failure_reason"] == "TARGETED_TEST_FAILED"
