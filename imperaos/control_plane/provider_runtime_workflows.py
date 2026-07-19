from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from imperaos.control_plane.models import (
    ProviderWorkflowProofArtifact,
    ProviderWorkflowProposal,
)
from imperaos.control_plane.provider_governance import stable_hash_payload
from imperaos.control_plane.provider_invocation import (
    ProviderInvocationCoordinator,
    ProviderInvocationRequest,
)


@dataclass(frozen=True)
class ProviderWorkflowProofRequest:
    workflow_kind: Literal["read_only_ops_triage"]
    provider_kind: str
    profile: str
    runtime_mode: Literal["dry_run", "canary_live"]
    output_root: Path


@dataclass(frozen=True)
class ProviderWorkflowProofResult:
    status: Literal["pass", "conditional", "blocked", "error"]
    workflow_id: str
    executed_mutations: int
    approval_tickets_created: int
    evidence_artifacts: tuple[str, ...]
    provider_invocations: tuple[str, ...]
    artifact_path: str

    def to_payload(self) -> dict[str, object]:
        return {
            "schemaVersion": "provider.workflow-proof.v1",
            "status": self.status,
            "workflowId": self.workflow_id,
            "workflowKind": "read_only_ops_triage",
            "executedMutations": self.executed_mutations,
            "approvalTicketsCreated": self.approval_tickets_created,
            "providerInvocations": list(self.provider_invocations),
            "evidenceArtifacts": list(self.evidence_artifacts),
            "artifactPath": self.artifact_path,
        }


def run_provider_workflow_proof(
    request: ProviderWorkflowProofRequest,
) -> ProviderWorkflowProofResult:
    output_root = Path(request.output_root)
    invocation_dir = output_root / "invocations"
    workflow_id = "read-only-ops-triage"
    invocation = ProviderInvocationCoordinator(output_dir=invocation_dir).invoke(
        ProviderInvocationRequest(
            provider_kind=request.provider_kind,
            model=_default_model(request.provider_kind),
            profile=request.profile,
            runtime_mode=request.runtime_mode,
            prompt="Inspect service alerts and draft remediation plan",
            agent_id="provider-governed-ops",
            workflow_id=workflow_id,
        )
    )
    proposals = [
        ProviderWorkflowProposal(
            proposalId="proposal-restart-service",
            actionId="restart-service",
            riskClass="mutation",
            executionMode="proposal_only",
            effectSummary="restart service is captured as an approval-gated proposal",
        )
    ]
    status = "pass" if invocation.status == "pass" else invocation.status
    artifact = ProviderWorkflowProofArtifact(
        status=status,
        workflowId=workflow_id,
        workflowKind="read_only_ops_triage",
        agentId="provider-governed-ops",
        providerInvocations=[invocation.invocation_id],
        proposals=proposals,
        executedMutations=0,
        approvalTicketsCreated=1,
        evidenceArtifacts=[path for path in [invocation.artifact_path] if path],
        blockingReasons=list(invocation.blocking_reasons),
        generatedAtUtc=datetime.now(UTC),
    )
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / "read_only_ops_triage_workflow_proof.json"
    path.write_text(
        json.dumps(artifact.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return ProviderWorkflowProofResult(
        status=status,
        workflow_id=workflow_id,
        executed_mutations=0,
        approval_tickets_created=1,
        evidence_artifacts=tuple(path for path in [invocation.artifact_path] if path),
        provider_invocations=(invocation.invocation_id,),
        artifact_path=str(path),
    )


def _default_model(provider_kind: str) -> str:
    if provider_kind == "anthropic_messages":
        return "claude-placeholder"
    return "gpt-placeholder"


def workflow_proof_hash(path: Path) -> str:
    return stable_hash_payload(json.loads(path.read_text(encoding="utf-8")))
