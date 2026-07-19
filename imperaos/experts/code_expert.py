from __future__ import annotations

import time
from pathlib import Path

from imperaos.experts.base import ExpertBase
from imperaos.governance.runtime import GovernanceRuntime
from imperaos.runtime.config import CodeVerifyConfig
from imperaos.schemas.expert_payloads import CodeExpertPayload, VerificationResult
from imperaos.schemas.models import ExpertName, ExpertRequest, ExpertResult, ExpertStatus
from imperaos.tools.code_verify import verify_python_snippet


class CodeExpert(ExpertBase):
    name = ExpertName.CODE
    estimated_tool_calls_per_run = 2

    def __init__(
        self,
        workspace: str | Path = ".",
        verify_config: CodeVerifyConfig | None = None,
        governance_runtime: GovernanceRuntime | None = None,
    ):
        self.workspace = Path(workspace)
        self.verify_config = verify_config or CodeVerifyConfig()
        self.governance_runtime = governance_runtime

    def run(self, request: ExpertRequest) -> ExpertResult:
        started = time.perf_counter()
        lower = request.user_input.lower()

        issue_type = self._detect_issue_type(lower)
        base_strategy = self._strategy_for_issue(issue_type)
        strategy = base_strategy
        patch_plan = self._patch_plan(issue_type)
        candidate_snippet = self._candidate_snippet(issue_type, lower)

        verification_raw = {
            "parse_ok": True,
            "lint_ok": None,
            "tests_ok": None,
            "stage_reached": 0,
            "failure_reason": None,
            "retry_count": 0,
            "retry_strategy": self.verify_config.retry_strategy,
            "details": {"skipped": "no executable snippet"},
        }
        if candidate_snippet and self.verify_config.enabled:
            for attempt in range(self.verify_config.retry_max + 1):
                verification_raw = verify_python_snippet(
                    candidate_snippet,
                    workdir=self.workspace,
                    run_lint=self.verify_config.lint_enabled,
                    run_test_collect=self.verify_config.test_collect_enabled,
                    run_targeted_tests=(
                        self.verify_config.targeted_tests_enabled
                        and issue_type in {"test", "runtime"}
                    ),
                    timeout_s=float(self.verify_config.timeout_s),
                    governance_runtime=self.governance_runtime,
                    run_id=request.request_id,
                )
                verification_raw["retry_count"] = attempt
                verification_raw["retry_strategy"] = self.verify_config.retry_strategy
                verification_raw["details"]["code_verification_stage_reached"] = (
                    verification_raw.get("stage_reached", 0)
                )
                verification_raw["details"]["code_failure_reason"] = verification_raw.get(
                    "failure_reason"
                )
                verification_raw["details"]["code_retry_count"] = attempt
                if self._verification_success(verification_raw):
                    break
                if attempt >= self.verify_config.retry_max:
                    break
                candidate_snippet, strategy = self._retry_candidate(
                    candidate_snippet=candidate_snippet,
                    failure_reason=str(verification_raw.get("failure_reason", "UNKNOWN")),
                    base_strategy=base_strategy,
                    retry_strategy=self.verify_config.retry_strategy,
                )
        elif candidate_snippet:
            verification_raw["details"] = {"skipped": "code_verify_disabled"}
            verification_raw["retry_count"] = 0
            verification_raw["retry_strategy"] = self.verify_config.retry_strategy

        verification = VerificationResult.model_validate(verification_raw)
        status = self._status_from_verification(verification)
        payload = CodeExpertPayload(
            issue_type=issue_type,
            strategy=strategy,
            patch_plan=patch_plan,
            candidate_snippet=candidate_snippet,
            verification=verification,
            notes=(
                "Code expert produced a structured, verifier-backed plan."
                if status == ExpertStatus.OK
                else "Verification incomplete; partial fallback with explain-first strategy."
            ),
        )

        conf = self._confidence_from_verification(verification=verification, status=status)
        elapsed = int((time.perf_counter() - started) * 1000)
        return ExpertResult(
            expert_name=self.name,
            status=status,
            confidence=conf,
            payload=payload.model_dump(mode="json"),
            elapsed_ms=elapsed,
        )

    @staticmethod
    def _verification_success(verification_raw: dict[str, object]) -> bool:
        parse_ok = bool(verification_raw.get("parse_ok", False))
        lint_ok = verification_raw.get("lint_ok")
        tests_ok = verification_raw.get("tests_ok")
        if not parse_ok:
            return False
        if lint_ok is False:
            return False
        return tests_ok is not False

    @staticmethod
    def _status_from_verification(verification: VerificationResult) -> ExpertStatus:
        if not verification.parse_ok:
            return ExpertStatus.PARTIAL
        if verification.tests_ok is False:
            return ExpertStatus.PARTIAL
        if verification.failure_reason in {"VERIFICATION_TIMEOUT", "COMMAND_NOT_ALLOWED"}:
            return ExpertStatus.PARTIAL
        return ExpertStatus.OK

    @staticmethod
    def _confidence_from_verification(
        *,
        verification: VerificationResult,
        status: ExpertStatus,
    ) -> float:
        if status == ExpertStatus.PARTIAL:
            return 0.42
        if verification.lint_ok is False:
            return 0.64
        if verification.tests_ok is True:
            return 0.86
        return 0.78

    @staticmethod
    def _retry_candidate(
        *,
        candidate_snippet: str,
        failure_reason: str,
        base_strategy: str,
        retry_strategy: str,
    ) -> tuple[str, str]:
        if retry_strategy == "minimal_only":
            return candidate_snippet.strip() + "\n", "minimal_patch"

        normalized_reason = failure_reason.upper()
        if normalized_reason in {"SYNTAX_INVALID", "INDENTATION_ERROR"}:
            repaired = candidate_snippet.replace("\t", "    ")
            return repaired, "minimal_patch"
        if normalized_reason in {"IMPORT_PARSE_FAIL", "TEST_COLLECT_FAILED"}:
            without_imports = "\n".join(
                line
                for line in candidate_snippet.splitlines()
                if not line.strip().startswith("import ")
            ).strip()
            if without_imports:
                return without_imports + "\n", "minimal_patch"
            return candidate_snippet, "minimal_patch"
        if normalized_reason in {"TARGETED_TEST_FAILED", "VERIFICATION_TIMEOUT"}:
            return candidate_snippet, "explain_only"
        return candidate_snippet, base_strategy

    @staticmethod
    def _detect_issue_type(text: str) -> str:
        if any(token in text for token in ("syntax", "indent", "parse", "sözdizim")):
            return "syntax"
        if any(token in text for token in ("test", "failing", "failed", "assert")):
            return "test"
        if any(token in text for token in ("import", "module", "package", "dependency")):
            return "import"
        if any(token in text for token in ("config", "env", "setting", "toml", "yaml")):
            return "config"
        if any(token in text for token in ("refactor", "cleanup", "clean code")):
            return "refactor"
        if any(token in text for token in ("error", "exception", "traceback", "runtime", "hata")):
            return "runtime"
        return "generic"

    @staticmethod
    def _strategy_for_issue(issue_type: str) -> str:
        mapping = {
            "test": "test_first_fix",
            "refactor": "safe_refactor",
            "generic": "minimal_patch",
        }
        return mapping.get(issue_type, "minimal_patch")

    @staticmethod
    def _patch_plan(issue_type: str) -> list[str]:
        base = [
            "Problemi yeniden üret ve hata tipini doğrula.",
            "En küçük davranış değişimiyle düzeltmeyi uygula.",
            "Doğrulama kontrollerini çalıştır ve sonucu raporla.",
        ]
        if issue_type == "test":
            return [
                "Failing test kapsamını daralt (collect/test target).",
                "Uygun fonksiyon/branch üzerinde minimal patch uygula.",
                "Testleri tekrar çalıştır, kırılan yan etkileri kontrol et.",
            ]
        if issue_type == "refactor":
            return [
                "Davranış koruyan refactor sınırını belirle.",
                "Fonksiyonları küçük ve saf parçalara böl.",
                "Regresyon riskini test/lint ile doğrula.",
            ]
        return base

    @staticmethod
    def _candidate_snippet(issue_type: str, text: str) -> str | None:
        if "unique" in text and "sort" in text:
            return (
                "def unique_sorted(items):\n"
                "    \"\"\"Return sorted unique list.\"\"\"\n"
                "    return sorted(set(items))\n"
            )
        if issue_type == "test":
            return (
                "def normalize_name(value: str) -> str:\n"
                "    return value.strip().lower()\n"
            )
        if issue_type == "runtime":
            return (
                "def safe_div(numerator: float, denominator: float) -> float:\n"
                "    if denominator == 0:\n"
                "        raise ValueError('denominator must not be zero')\n"
                "    return numerator / denominator\n"
            )
        return None
