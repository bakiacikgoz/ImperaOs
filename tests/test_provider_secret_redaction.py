from __future__ import annotations

import json

from imperaos.control_plane.provider_conformance import run_provider_native_gate


def test_provider_conformance_artifacts_do_not_persist_raw_prompt_or_secrets(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-should-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-should-not-leak")

    gate = run_provider_native_gate(profile="enterprise", output_dir=tmp_path)

    assert gate["status"] == "pass"
    artifact_text = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.glob("*.json"))
    assert "sk-live-should-not-leak" not in artifact_text
    assert "anthropic-should-not-leak" not in artifact_text
    assert "Summarize queue errors without mutation." not in artifact_text
    assert "Summarize failed jobs and propose remediation." not in artifact_text

    for path in tmp_path.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload.get("rawPersistence") is False
