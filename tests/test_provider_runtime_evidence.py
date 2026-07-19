from __future__ import annotations

import json
from pathlib import Path

from imperaos.control_plane.provider_runtime_evidence import ProviderEvidenceWriter


def test_provider_evidence_writer_persists_hash_only_artifact(tmp_path: Path) -> None:
    writer = ProviderEvidenceWriter(output_dir=tmp_path)

    result = writer.write_invocation(
        invocation_id="inv-test",
        provider_kind="openai_responses",
        model="gpt-placeholder",
        runtime_mode="dry_run",
        status="pass",
        policy_decision={"decision": "allow", "reasonCodes": ["PROVIDER_POLICY_PASS"]},
        request_hash="sha256:" + "a" * 64,
        response_hash="sha256:" + "b" * 64,
        tool_policy={
            "serverToolsPolicy": "denied",
            "customToolsPolicy": "proposal_only",
            "requestedServerTools": [],
        },
        blocking_reasons=[],
        raw_inputs_for_scan=["secret-key-123", "raw prompt should not persist"],
    )

    payload = json.loads(Path(result.artifact_path).read_text(encoding="utf-8"))
    encoded = json.dumps(payload, sort_keys=True)
    assert payload["schemaVersion"] == "provider.invocation.v1"
    assert payload["rawPersistence"] is False
    assert payload["evidenceMode"] == "hash_only"
    assert payload["requestHash"] == "sha256:" + "a" * 64
    assert "secret-key-123" not in encoded
    assert "raw prompt should not persist" not in encoded
    assert result.artifact_hash.startswith("sha256:")


def test_provider_evidence_writer_rejects_raw_leakage(tmp_path: Path) -> None:
    writer = ProviderEvidenceWriter(output_dir=tmp_path)

    result = writer.write_invocation(
        invocation_id="inv-leak",
        provider_kind="openai_responses",
        model="gpt-placeholder",
        runtime_mode="dry_run",
        status="pass",
        policy_decision={"decision": "allow", "reasonCodes": ["PROVIDER_POLICY_PASS"]},
        request_hash="sha256:" + "a" * 64,
        response_hash="sha256:" + "b" * 64,
        tool_policy={
            "serverToolsPolicy": "denied",
            "customToolsPolicy": "proposal_only",
            "requestedServerTools": [],
        },
        blocking_reasons=[],
        extra_payload={"unsafeSummary": "secret-key-123"},
        raw_inputs_for_scan=["secret-key-123"],
    )

    assert result.status == "error"
    assert "PROVIDER_EVIDENCE_LEAKAGE_DETECTED" in result.blocking_reasons
    assert result.artifact_path is None
