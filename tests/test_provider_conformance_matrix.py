from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from imperaos.model_providers.conformance import build_provider_conformance_matrix
from imperaos.model_providers.registry import resolve_model_provider_registry
from imperaos.runtime.config import RuntimeConfig


def test_provider_conformance_matrix_covers_configured_profiles() -> None:
    registry = resolve_model_provider_registry(
        config=RuntimeConfig.from_profile("enterprise"),
        profile="enterprise",
    )

    matrix = build_provider_conformance_matrix(
        registry=registry,
        profile="enterprise",
        mode="offline",
    )

    provider_ids = {item.provider_id for item in matrix.providers}
    assert {
        "local-ollama",
        "local-transformers",
        "company-internal",
        "openai-public",
        "deepseek-public",
        "gemini-openai-compatible",
    }.issubset(provider_ids)
    assert all(item.fail_count == 0 for item in matrix.providers)
    assert all(
        next(check for check in item.checks if check.check_id == "live_canary").reason_code
        == "PROVIDER_LIVE_CANARY_DISABLED"
        for item in matrix.providers
    )


def test_provider_conformance_matrix_script_writes_json_and_markdown(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_provider_conformance_matrix.py",
            "--profile",
            "enterprise",
            "--mode",
            "offline",
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
    assert (tmp_path / "provider_conformance_matrix.json").exists()
    assert (tmp_path / "PROVIDER_CONFORMANCE_MATRIX.md").exists()
