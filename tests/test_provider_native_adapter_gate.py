from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from imperaos.model_providers.native.conformance import (
    run_anthropic_messages_native_conformance,
    run_openai_responses_native_conformance,
)


def test_native_conformance_matrix_openai_responses() -> None:
    report = run_openai_responses_native_conformance(profile="enterprise")

    assert report.status == "pass"
    assert report.total_cases >= 10
    assert report.pass_count >= 3
    assert report.expected_blocked_count >= 7
    assert report.unexpected_failure_count == 0


def test_native_conformance_matrix_anthropic_messages() -> None:
    report = run_anthropic_messages_native_conformance(profile="enterprise")

    assert report.status == "pass"
    assert report.total_cases >= 12
    assert report.pass_count >= 4
    assert report.expected_blocked_count >= 8
    assert report.unexpected_failure_count == 0


def test_provider_native_adapter_gate_script(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_provider_native_adapter_gate.py",
            "--profile",
            "enterprise",
            "--output-root",
            str(tmp_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["totalCases"] >= 22
    assert payload["nativeConformance"]["total_cases"] >= 10
    assert any(
        item["provider_kind"] == "anthropic_messages"
        for item in payload["nativeConformanceReports"]
    )
