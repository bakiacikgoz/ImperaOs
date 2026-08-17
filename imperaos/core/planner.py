from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import Any, Literal

from imperaos.core.llm_ollama import LLMClient
from imperaos.schemas.models import ExpertName, PlannerOutput, ResponseMode, TaskType
from imperaos.schemas.reason_codes import ReasonCode

PLANNER_SYSTEM_PROMPTS: dict[str, str] = {
    "strict_v1": (
        "You are a strict planner. Output only a valid JSON object with required fields. "
        "No markdown. No extra keys."
    ),
    "strict_v2": (
        "Return ONLY a JSON object.\n"
        "Do not include markdown fences.\n"
        "Do not add extra keys.\n"
        "Use valid enums and primitive types."
    ),
    "strict_v3": (
        "You are PlannerJSON.\n"
        "Output one JSON object only.\n"
        "task_type in {chat,code,research,plan,mixed}\n"
        "response_mode in {direct,tool-first,ask-clarify}\n"
        "confidence must be float in [0,1].\n"
        "No prose. No comments. No markdown."
    ),
}


@dataclass(slots=True)
class PlannerRun:
    output: PlannerOutput
    raw_output: str
    parse_failed: bool
    error: str | None
    elapsed_ms: int
    reason_code: ReasonCode


class PlannerJSONExtractError(ValueError):
    pass


class PlannerRepairError(ValueError):
    pass


class Planner:
    def __init__(
        self,
        llm: LLMClient,
        default_latency_budget_ms: int = 3500,
        llm_timeout_ms: int = 60_000,
        *,
        repair_enabled: bool = True,
        repair_max_attempts: int = 1,
        prompt_variant: Literal["strict_v1", "strict_v2", "strict_v3"] = "strict_v2",
    ):
        self._llm = llm
        self._default_latency_budget_ms = default_latency_budget_ms
        self._llm_timeout_ms = llm_timeout_ms
        self._repair_enabled = repair_enabled
        self._repair_max_attempts = max(0, repair_max_attempts)
        self._prompt_variant = prompt_variant

    def plan(self, user_input: str) -> PlannerRun:
        prompt = self._build_prompt(user_input)

        started = time.perf_counter()
        raw_output = ""
        try:
            raw_output = self._generate_with_timeout(
                prompt=prompt,
                system=self._system_prompt(),
                json_mode=True,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            fallback = self._heuristic_plan(user_input=user_input, intent="planner_llm_failure")
            return PlannerRun(
                output=fallback,
                raw_output=raw_output,
                parse_failed=True,
                error=str(exc),
                elapsed_ms=elapsed_ms,
                reason_code=ReasonCode.PLANNER_LLM_FAILURE,
            )

        try:
            payload, repaired = self._parse_json_payload(raw_output)
        except PlannerJSONExtractError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            fallback = self._heuristic_plan(
                user_input=user_input,
                intent="planner_json_extract_failed",
            )
            return PlannerRun(
                output=fallback,
                raw_output=raw_output,
                parse_failed=True,
                error=str(exc),
                elapsed_ms=elapsed_ms,
                reason_code=ReasonCode.PLANNER_JSON_EXTRACT_FAILED,
            )
        except PlannerRepairError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            fallback = self._heuristic_plan(user_input=user_input, intent="planner_repair_failed")
            return PlannerRun(
                output=fallback,
                raw_output=raw_output,
                parse_failed=True,
                error=str(exc),
                elapsed_ms=elapsed_ms,
                reason_code=ReasonCode.PLANNER_REPAIR_FAILED,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            fallback = self._heuristic_plan(user_input=user_input, intent="planner_parse_fallback")
            return PlannerRun(
                output=fallback,
                raw_output=raw_output,
                parse_failed=True,
                error=str(exc),
                elapsed_ms=elapsed_ms,
                reason_code=ReasonCode.PLANNER_PARSE_FALLBACK,
            )

        try:
            payload = self._normalize_payload(payload)
            output = PlannerOutput.model_validate(payload)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return PlannerRun(
                output=output,
                raw_output=raw_output,
                parse_failed=False,
                error=None,
                elapsed_ms=elapsed_ms,
                reason_code=(
                    ReasonCode.PLANNER_REPAIR_APPLIED if repaired else ReasonCode.PLANNER_OK
                ),
            )
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            fallback = self._heuristic_plan(user_input=user_input, intent="planner_schema_invalid")
            return PlannerRun(
                output=fallback,
                raw_output=raw_output,
                parse_failed=True,
                error=str(exc),
                elapsed_ms=elapsed_ms,
                reason_code=ReasonCode.PLANNER_SCHEMA_INVALID,
            )

    def _build_prompt(self, user_input: str) -> str:
        return (
            "Analyze user request and return strict JSON only.\n"
            f"User input: {user_input}\n"
            "Task types: chat, code, research, plan, mixed.\n"
            "Response modes: direct, tool-first, ask-clarify.\n"
            "Expert candidates: code_expert, research_expert, plan_expert.\n"
            "Return exactly this structure with valid values:\n"
            "{"
            '"task_type":"chat|code|research|plan|mixed",'
            '"intent":"...",'
            '"needs_expert":true,'
            '"expert_candidates":["research_expert","plan_expert","code_expert"],'
            '"confidence":0.0,'
            '"latency_budget_ms":3000,'
            '"can_fallback":true,'
            '"response_mode":"direct|tool-first|ask-clarify"'
            "}"
        )

    def _system_prompt(self) -> str:
        return PLANNER_SYSTEM_PROMPTS.get(self._prompt_variant, PLANNER_SYSTEM_PROMPTS["strict_v2"])

    def _parse_json_payload(self, raw_output: str) -> tuple[dict[str, object], bool]:
        text = raw_output.strip()
        if not text:
            raise PlannerJSONExtractError("empty planner output")

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed, False
        except json.JSONDecodeError:
            pass

        candidate = self._extract_json_object(text)
        try:
            parsed = json.loads(candidate)
            repaired = candidate.strip() != text.strip()
        except json.JSONDecodeError:
            if not self._repair_enabled or self._repair_max_attempts <= 0:
                raise PlannerRepairError("planner repair disabled") from None
            parsed = None
            repaired = False
            current = candidate
            for _attempt in range(self._repair_max_attempts):
                current = self._repair_json_object(current)
                try:
                    maybe = json.loads(current)
                    if isinstance(maybe, dict):
                        parsed = maybe
                        repaired = True
                        break
                except json.JSONDecodeError:
                    continue
            if parsed is None:
                raise PlannerRepairError("planner repair attempts exhausted") from None
        if not isinstance(parsed, dict):
            raise ValueError("planner output JSON is not an object")
        return parsed, repaired

    @staticmethod
    def _extract_json_object(text: str) -> str:
        cleaned = text.replace("```json", "```").replace("```JSON", "```")
        if "```" in cleaned:
            parts = cleaned.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("{") and part.endswith("}"):
                    return part

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise PlannerJSONExtractError("no JSON object found in planner output")
        return cleaned[start : end + 1]

    @staticmethod
    def _repair_json_object(text: str) -> str:
        repaired = text.strip()
        repaired = repaired.replace("```json", "").replace("```JSON", "").replace("```", "")
        repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
        repaired = repaired.replace("“", '"').replace("”", '"').replace("’", "'")
        repaired = re.sub(r"\bTrue\b", "true", repaired)
        repaired = re.sub(r"\bFalse\b", "false", repaired)
        repaired = re.sub(r"\bNone\b", "null", repaired)
        repaired = re.sub(r"(?<!\\)'([^'\\]*(?:\\.[^'\\]*)*)'", r'"\1"', repaired)
        return repaired

    @staticmethod
    def _normalize_payload(payload: dict[str, object]) -> dict[str, object]:
        allowed = {
            "task_type",
            "intent",
            "needs_expert",
            "expert_candidates",
            "confidence",
            "latency_budget_ms",
            "can_fallback",
            "response_mode",
        }
        extra = sorted(set(payload.keys()) - allowed)
        if extra:
            raise ValueError(f"unknown planner fields: {', '.join(extra)}")

        normalized = dict(payload)
        normalized["task_type"] = Planner._coerce_task_type(normalized.get("task_type", "chat"))
        normalized["response_mode"] = Planner._coerce_response_mode(
            normalized.get("response_mode", "direct")
        )
        normalized["intent"] = str(normalized.get("intent", "unknown_intent"))
        normalized["needs_expert"] = Planner._coerce_bool(normalized.get("needs_expert", False))
        normalized["can_fallback"] = Planner._coerce_bool(normalized.get("can_fallback", True))
        normalized["confidence"] = Planner._coerce_float(normalized.get("confidence", 0.0))
        normalized["latency_budget_ms"] = Planner._coerce_int(
            normalized.get("latency_budget_ms", 3000)
        )

        candidates = normalized.get("expert_candidates", [])
        if isinstance(candidates, list):
            normalized["expert_candidates"] = [
                Planner._coerce_expert_name(item) for item in candidates
            ]
        else:
            raise ValueError("expert_candidates must be a list")

        return normalized

    @staticmethod
    def _coerce_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "y", "on"}:
                return True
            if lowered in {"false", "0", "no", "n", "off"}:
                return False
        raise ValueError(f"invalid bool: {value!r}")

    @staticmethod
    def _coerce_float(value: object) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return float(value.strip())
        raise ValueError(f"invalid float: {value!r}")

    @staticmethod
    def _coerce_int(value: object) -> int:
        if isinstance(value, bool):
            raise ValueError(f"invalid int: {value!r}")
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            return int(value.strip())
        raise ValueError(f"invalid int: {value!r}")

    @staticmethod
    def _coerce_task_type(value: object) -> TaskType:
        text = str(value)
        if text not in TaskType._value2member_map_:
            raise ValueError(f"invalid task_type: {value!r}")
        return TaskType(text)

    @staticmethod
    def _coerce_response_mode(value: object) -> ResponseMode:
        text = str(value)
        if text not in ResponseMode._value2member_map_:
            raise ValueError(f"invalid response_mode: {value!r}")
        return ResponseMode(text)

    @staticmethod
    def _coerce_expert_name(value: Any) -> ExpertName:
        text = str(value)
        if text not in ExpertName._value2member_map_:
            raise ValueError(f"invalid expert candidate: {value!r}")
        return ExpertName(text)

    def _heuristic_plan(self, user_input: str, intent: str) -> PlannerOutput:
        text = user_input.lower()
        code_tokens = ("python", "bug", "hata", "test", "refactor", "kod")
        research_tokens = (
            "özet",
            "summary",
            "araştır",
            "doküman",
            "document",
            "compare",
            "karşılaştır",
        )
        plan_tokens = ("plan", "adım", "takvim", "roadmap", "schedule", "hafta", "faz")

        is_code = any(token in text for token in code_tokens)
        is_research = any(token in text for token in research_tokens)
        is_plan = any(token in text for token in plan_tokens)

        if sum((is_code, is_research, is_plan)) >= 2:
            task_type = TaskType.MIXED
            candidates = [ExpertName.RESEARCH, ExpertName.PLAN, ExpertName.CODE]
            needs_expert = True
            response_mode = ResponseMode.TOOL_FIRST
            confidence = 0.62
        elif is_code:
            task_type = TaskType.CODE
            candidates = [ExpertName.CODE, ExpertName.PLAN]
            needs_expert = True
            response_mode = ResponseMode.TOOL_FIRST
            confidence = 0.62
        elif is_research:
            task_type = TaskType.RESEARCH
            candidates = [ExpertName.RESEARCH, ExpertName.PLAN]
            needs_expert = True
            response_mode = ResponseMode.TOOL_FIRST
            confidence = 0.62
        elif is_plan:
            task_type = TaskType.PLAN
            candidates = [ExpertName.PLAN, ExpertName.RESEARCH]
            needs_expert = True
            response_mode = ResponseMode.TOOL_FIRST
            confidence = 0.60
        else:
            task_type = TaskType.CHAT
            candidates = []
            needs_expert = False
            response_mode = ResponseMode.DIRECT
            confidence = 0.50

        return PlannerOutput(
            task_type=task_type,
            intent=intent,
            needs_expert=needs_expert,
            expert_candidates=candidates,
            confidence=confidence,
            latency_budget_ms=self._default_latency_budget_ms,
            can_fallback=True,
            response_mode=response_mode,
        )

    def _generate_with_timeout(self, prompt: str, system: str, json_mode: bool) -> str:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            self._llm.generate,
            prompt,
            system,
            json_mode,
        )
        try:
            return future.result(timeout=self._llm_timeout_ms / 1000)
        except TimeoutError as exc:
            future.cancel()
            raise TimeoutError("planner llm timeout") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
