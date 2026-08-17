from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from imperaos.control_plane.provider_invocation import (
    ProviderInvocationCoordinator,
    ProviderInvocationRequest,
)


def test_provider_invocation_dry_run_writes_hash_only_evidence(tmp_path: Path) -> None:
    coordinator = ProviderInvocationCoordinator(output_dir=tmp_path)

    result = coordinator.invoke(
        ProviderInvocationRequest(
            provider_kind="openai_responses",
            model="gpt-placeholder",
            profile="enterprise",
            runtime_mode="dry_run",
            prompt="Inspect service alerts and draft read-only triage summary",
        )
    )

    assert result.status == "pass"
    assert result.raw_persistence is False
    assert result.evidence_mode == "hash_only"
    assert result.request_hash.startswith("sha256:")
    assert result.response_hash and result.response_hash.startswith("sha256:")
    assert result.artifact_path is not None
    payload = json.loads(Path(result.artifact_path).read_text(encoding="utf-8"))
    encoded = json.dumps(payload, sort_keys=True)
    assert "Inspect service alerts" not in encoded
    assert payload["runtimeMode"] == "dry_run"
    assert payload["toolPolicy"]["serverToolsPolicy"] == "denied"
    assert payload["toolPolicy"]["customToolsPolicy"] == "proposal_only"


def test_provider_invocation_unsupported_provider_fails_closed(tmp_path: Path) -> None:
    coordinator = ProviderInvocationCoordinator(output_dir=tmp_path)

    result = coordinator.invoke(
        ProviderInvocationRequest(
            provider_kind="google_gemini",
            model="gemini-placeholder",
            profile="enterprise",
            runtime_mode="dry_run",
            prompt="test",
        )
    )

    assert result.status == "blocked"
    assert "PROVIDER_UNSUPPORTED" in result.blocking_reasons
    assert result.artifact_path is not None


def test_provider_invocation_canary_live_requires_double_opt_in(tmp_path: Path) -> None:
    coordinator = ProviderInvocationCoordinator(output_dir=tmp_path)

    result = coordinator.invoke(
        ProviderInvocationRequest(
            provider_kind="openai_responses",
            model="gpt-placeholder",
            profile="enterprise",
            runtime_mode="canary_live",
            prompt="test",
        )
    )

    assert result.status == "blocked"
    assert "PROVIDER_LIVE_CANARY_REQUIRES_EXPLICIT_OPT_IN" in result.blocking_reasons


def test_provider_invoke_cli_dry_run_outputs_safe_json(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "imperaos",
            "provider",
            "invoke",
            "--provider",
            "openai_responses",
            "--model",
            "gpt-placeholder",
            "--profile",
            "enterprise",
            "--mode",
            "dry-run",
            "--once",
            "Inspect service alerts and draft read-only triage summary",
            "--output-dir",
            str(tmp_path),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    encoded = json.dumps(payload, sort_keys=True)
    assert payload["schemaVersion"] == "provider.invocation.v1"
    assert payload["status"] == "pass"
    assert payload["rawPersistence"] is False
    assert payload["evidenceMode"] == "hash_only"
    assert "Inspect service alerts" not in encoded
