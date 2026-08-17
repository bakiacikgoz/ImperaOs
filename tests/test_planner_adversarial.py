from __future__ import annotations

from imperaos.core.llm_ollama import StubLLM
from imperaos.core.planner import Planner
from imperaos.schemas.reason_codes import ReasonCode


def test_planner_repairs_single_quoted_json_once() -> None:
    llm = StubLLM(
        responses=[
            (
                "{'task_type':'plan','intent':'x','needs_expert':'true',"
                "'expert_candidates':['plan_expert'],'confidence':'0.7',"
                "'latency_budget_ms':'2000','can_fallback':'true','response_mode':'tool-first'}"
            )
        ]
    )
    planner = Planner(llm=llm, default_latency_budget_ms=1200)
    run = planner.plan("plan yap")

    assert run.parse_failed is False
    assert run.reason_code == ReasonCode.PLANNER_REPAIR_APPLIED


def test_planner_rejects_extra_keys_as_schema_invalid() -> None:
    llm = StubLLM(
        responses=[
            (
                '{"task_type":"chat","intent":"x","needs_expert":false,'
                '"expert_candidates":[],"confidence":0.6,"latency_budget_ms":2000,'
                '"can_fallback":true,"response_mode":"direct","extra":"nope"}'
            )
        ]
    )
    planner = Planner(llm=llm, default_latency_budget_ms=1200)
    run = planner.plan("selam")

    assert run.parse_failed is True
    assert run.reason_code == ReasonCode.PLANNER_SCHEMA_INVALID


def test_planner_rejects_invalid_enum_as_schema_invalid() -> None:
    llm = StubLLM(
        responses=[
            (
                '{"task_type":"unknown","intent":"x","needs_expert":false,'
                '"expert_candidates":[],"confidence":0.6,"latency_budget_ms":2000,'
                '"can_fallback":true,"response_mode":"direct"}'
            )
        ]
    )
    planner = Planner(llm=llm, default_latency_budget_ms=1200)
    run = planner.plan("selam")

    assert run.parse_failed is True
    assert run.reason_code == ReasonCode.PLANNER_SCHEMA_INVALID


def test_planner_reports_json_extract_failed() -> None:
    planner = Planner(llm=StubLLM(responses=["no braces here"]), default_latency_budget_ms=1200)
    run = planner.plan("selam")
    assert run.parse_failed is True
    assert run.reason_code == ReasonCode.PLANNER_JSON_EXTRACT_FAILED


def test_planner_reports_repair_failed_when_disabled() -> None:
    planner = Planner(
        llm=StubLLM(responses=["{'broken': yes}"]),
        default_latency_budget_ms=1200,
        repair_enabled=False,
    )
    run = planner.plan("selam")
    assert run.parse_failed is True
    assert run.reason_code == ReasonCode.PLANNER_REPAIR_FAILED
