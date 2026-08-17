from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from imperaos.control_plane.provider_runtime_workflows import (
    ProviderWorkflowProofRequest,
    run_provider_workflow_proof,
)


def test_read_only_ops_workflow_proof_blocks_mutations_and_attaches_evidence(
    tmp_path: Path,
) -> None:
    result = run_provider_workflow_proof(
        ProviderWorkflowProofRequest(
            workflow_kind="read_only_ops_triage",
            provider_kind="openai_responses",
            profile="enterprise",
            runtime_mode="dry_run",
            output_root=tmp_path,
        )
    )

    assert result.status == "pass"
    assert result.executed_mutations == 0
    assert result.approval_tickets_created >= 1
    assert result.provider_invocations
    assert result.evidence_artifacts
    payload = json.loads((tmp_path / "read_only_ops_triage_workflow_proof.json").read_text())
    encoded = json.dumps(payload, sort_keys=True)
    assert payload["schemaVersion"] == "provider.workflow-proof.v1"
    assert payload["executedMutations"] == 0
    assert "restart service" in encoded
    assert "direct_execution" not in encoded


def test_workflow_proof_script_outputs_schema_valid_json(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_provider_runtime_workflow_proof.py",
            "--profile",
            "enterprise",
            "--provider",
            "openai_responses",
            "--mode",
            "dry-run",
            "--output-root",
            str(tmp_path),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schemaVersion"] == "provider.workflow-proof.v1"
    assert payload["status"] == "pass"
    assert payload["executedMutations"] == 0
    assert payload["approvalTicketsCreated"] >= 1
