from __future__ import annotations

import ast
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from imperaos.governance.runtime import GovernanceRuntime
from imperaos.tools.sandbox_runner import SandboxRunner


def verify_python_snippet(
    code: str,
    *,
    workdir: str | Path = ".",
    run_lint: bool = True,
    run_test_collect: bool = True,
    run_targeted_tests: bool = False,
    targeted_test_args: list[str] | None = None,
    timeout_s: float = 15,
    governance_runtime: GovernanceRuntime | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "parse_ok": False,
        "lint_ok": None,
        "tests_ok": None,
        "stage_reached": 0,
        "failure_reason": None,
        "retry_count": 0,
        "retry_strategy": None,
        "details": {},
    }
    if not code.strip():
        result["failure_reason"] = "EMPTY_SNIPPET"
        return result

    try:
        ast.parse(code)
        result["parse_ok"] = True
        result["stage_reached"] = 1
    except SyntaxError as exc:
        result["details"]["parse_error"] = {
            "message": str(exc),
            "line": exc.lineno,
            "offset": exc.offset,
        }
        if isinstance(exc, IndentationError):
            result["failure_reason"] = "INDENTATION_ERROR"
        else:
            result["failure_reason"] = "SYNTAX_INVALID"
        return result

    runner = SandboxRunner(
        workdir=workdir,
        timeout_s=timeout_s,
        governance_runtime=governance_runtime,
        governance_run_id=run_id,
    )

    # Use an ephemeral file for syntax/lint checks and avoid mutating the repo.
    with NamedTemporaryFile("w", suffix=".py", delete=True) as tmp:
        tmp.write(code)
        tmp.flush()
        py_compile = runner.run(["python", "-m", "py_compile", tmp.name])
        result["details"]["py_compile_exit_code"] = py_compile.exit_code
        if py_compile.exit_code != 0:
            result["lint_ok"] = False
            result["details"]["py_compile_stderr"] = py_compile.stderr.strip()
            result["failure_reason"] = _classify_runner_failure(
                py_compile,
                default="IMPORT_PARSE_FAIL",
            )
            return result

        result["stage_reached"] = 2
        if run_lint:
            lint_run = runner.run(["ruff", "check", "--select", "E,F", "--quiet", tmp.name])
            # ruff not installed should not fail the full verification; keep explicit detail.
            if lint_run.exit_code == 127:
                result["lint_ok"] = None
                result["details"]["lint_skipped"] = "ruff not found"
            else:
                result["lint_ok"] = lint_run.exit_code == 0
                result["details"]["lint_exit_code"] = lint_run.exit_code
                if lint_run.exit_code != 0:
                    result["details"]["lint_stderr"] = lint_run.stderr.strip()
                    result["failure_reason"] = _classify_runner_failure(
                        lint_run,
                        default="LINT_FAILED",
                    )
                    return result
        else:
            result["lint_ok"] = None

    if run_test_collect:
        test_run = runner.run(
            ["uv", "run", "--extra", "dev", "python", "-m", "pytest", "--collect-only", "-q"]
        )
        if test_run.exit_code == 127:
            result["tests_ok"] = None
            result["details"]["tests_skipped"] = "uv not found"
        else:
            result["stage_reached"] = 3
            result["details"]["test_collect_exit_code"] = test_run.exit_code
            if test_run.exit_code != 0:
                result["tests_ok"] = False
                result["details"]["test_collect_stderr"] = test_run.stderr.strip()
                result["failure_reason"] = _classify_runner_failure(
                    test_run,
                    default="TEST_COLLECT_FAILED",
                )
                return result

    if run_targeted_tests:
        args = targeted_test_args or ["-q", "-k", "not slow", "--maxfail=1"]
        target_run = runner.run(["uv", "run", "--extra", "dev", "python", "-m", "pytest", *args])
        result["stage_reached"] = 4
        result["details"]["targeted_tests_exit_code"] = target_run.exit_code
        if target_run.exit_code == 127:
            result["tests_ok"] = None
            result["details"]["targeted_tests_skipped"] = "uv not found"
            result["failure_reason"] = "TARGETED_TESTS_SKIPPED"
            return result
        if target_run.exit_code != 0:
            result["tests_ok"] = False
            result["details"]["targeted_tests_stderr"] = target_run.stderr.strip()
            result["failure_reason"] = _classify_runner_failure(
                target_run,
                default="TARGETED_TEST_FAILED",
            )
            return result
        result["tests_ok"] = True
        result["stage_reached"] = 5
    elif run_test_collect:
        result["tests_ok"] = True

    return result


def _classify_runner_failure(run: Any, *, default: str) -> str:
    exit_code = int(getattr(run, "exit_code", -1))
    stderr = str(getattr(run, "stderr", "")).lower()
    if exit_code == 124:
        return "VERIFICATION_TIMEOUT"
    if exit_code == 126:
        return "COMMAND_NOT_ALLOWED"
    if exit_code == 125:
        return "APPROVAL_REQUIRED"
    if "indentation" in stderr:
        return "INDENTATION_ERROR"
    if "syntax" in stderr:
        return "SYNTAX_INVALID"
    if "import" in stderr or "module" in stderr:
        return "IMPORT_PARSE_FAIL"
    if "collect" in stderr:
        return "TEST_COLLECT_FAILED"
    return default
