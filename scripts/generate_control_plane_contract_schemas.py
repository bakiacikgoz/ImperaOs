from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.admin_store import AdminChangeProposal  # noqa: E402
from imperaos.control_plane.agent_enrollment import (  # noqa: E402
    AgentEnrollmentDecision,
    AgentEnrollmentRequest,
    AgentEnrollmentToken,
    EnrolledAgent,
)
from imperaos.control_plane.design_partner_handoff import (  # noqa: E402
    DesignPartnerHandoffManifest,
    DesignPartnerHandoffSnapshot,
    DesignPartnerHandoffVerificationReport,
)
from imperaos.control_plane.enterprise_rbac import WorkspacePermissionDecision  # noqa: E402
from imperaos.control_plane.enterprise_workspace import (  # noqa: E402
    EnterpriseDevice,
    EnterpriseOrganization,
    EnterprisePrincipal,
    EnterpriseWorkspace,
    EnterpriseWorkspaceMembership,
    EnterpriseWorkspaceSnapshot,
)
from imperaos.control_plane.external_agent_client import ExternalAgentPilotManifest  # noqa: E402
from imperaos.control_plane.external_contracts import (  # noqa: E402
    ExternalActionRequest,
    ExternalActionResponse,
    ExternalAgentRequestV11,
    ExternalAgentV11Result,
)
from imperaos.control_plane.field_evidence import (  # noqa: E402
    DesignPartnerFieldEvidenceSnapshot,
    DesignPartnerFieldPackManifest,
    FieldEvidenceBundle,
    FieldEvidenceSession,
    FieldEvidenceVerificationResult,
    OperatorAttestationBinding,
    OperatorAttestationValidationResult,
)
from imperaos.control_plane.install_rehearsal import InstallRehearsalReport  # noqa: E402
from imperaos.control_plane.mainline_rc_freeze import (  # noqa: E402
    GateEvidenceSummary,
    MainlineRcFreezeSnapshot,
    RcFreezeManifest,
    RcFreezeVerificationReport,
)
from imperaos.control_plane.mainline_stack import (  # noqa: E402
    MergeRehearsalReport,
    StackGraphSpec,
    StackGraphVerificationReport,
)
from imperaos.control_plane.models import (  # noqa: E402
    ActionProposal,
    AgentRecord,
    AgentRegistryV2Snapshot,
    AgentSpec,
    AlertEvaluation,
    ClaimMatrix,
    ControlPlaneRunSummary,
    ControlPlaneSnapshot,
    EvidenceIndexSnapshot,
    EvidencePackManifest,
    EvidenceVerifyResult,
    OperationWorkflowRequest,
    OperationWorkflowResult,
    OperatorAttestation,
    PilotCandidateManifest,
    PolicyPackDiffResult,
    PolicyPackManifest,
    PolicyPackPromotionDryRun,
    PolicySimulationResult,
    ProviderConformanceReport,
    ProviderGovernanceSnapshot,
    ProviderInvocationArtifact,
    ProviderRuntimeSnapshot,
    ProviderWorkflowProofArtifact,
    RbacMatrixSnapshot,
    RbacPermissionDecision,
    ReadinessReport,
    ReportManifest,
    TargetEvidenceBundle,
    TargetEvidenceClosureSummary,
    TargetEvidenceSession,
)
from imperaos.control_plane.pilot_ops_drill import PilotOpsDrillReport  # noqa: E402
from imperaos.control_plane.pilot_workflow_models import (  # noqa: E402
    GovernedPilotWorkflowReport,
    GovernedPilotWorkflowSnapshot,
    GovernedPilotWorkflowSpec,
    GovernedPilotWorkflowVerification,
)
from imperaos.control_plane.policy_pack_store import PolicyPackLifecycleRecord  # noqa: E402
from imperaos.control_plane.release_train import (  # noqa: E402
    ReleaseTrainManifest,
    ReleaseTrainVerificationReport,
)
from imperaos.control_plane.strict_rc_promotion import StrictRCPromotionReport  # noqa: E402
from imperaos.release.gate_models import RcGateEvidenceSnapshot  # noqa: E402
from imperaos.release_decision.models import RcReleaseDecisionSnapshot  # noqa: E402

SCHEMAS = {
    "agent_spec": AgentSpec,
    "agent_record": AgentRecord,
    "agent_registry_v2": AgentRegistryV2Snapshot,
    "action_proposal": ActionProposal,
    "policy_simulation": PolicySimulationResult,
    "policy_pack_manifest": PolicyPackManifest,
    "policy_pack_diff": PolicyPackDiffResult,
    "policy_pack_promotion": PolicyPackPromotionDryRun,
    "rbac_matrix": RbacMatrixSnapshot,
    "rbac_decision": RbacPermissionDecision,
    "report_manifest": ReportManifest,
    "alert_evaluation": AlertEvaluation,
    "control_plane_run_summary": ControlPlaneRunSummary,
    "evidence_index": EvidenceIndexSnapshot,
    "evidence_pack_manifest": EvidencePackManifest,
    "evidence_verify_result": EvidenceVerifyResult,
    "operation_workflow_request": OperationWorkflowRequest,
    "operation_workflow_result": OperationWorkflowResult,
    "provider_registry": ProviderGovernanceSnapshot,
    "provider_conformance": ProviderConformanceReport,
    "provider_invocation": ProviderInvocationArtifact,
    "provider_workflow_proof": ProviderWorkflowProofArtifact,
    "provider_runtime": ProviderRuntimeSnapshot,
    "target_evidence_session": TargetEvidenceSession,
    "target_evidence_bundle": TargetEvidenceBundle,
    "operator_attestation": OperatorAttestation,
    "pilot_candidate_manifest": PilotCandidateManifest,
    "target_evidence_closure": TargetEvidenceClosureSummary,
    "readiness_report": ReadinessReport,
    "claim_matrix": ClaimMatrix,
    "control_plane_snapshot": ControlPlaneSnapshot,
    "install_rehearsal_report": InstallRehearsalReport,
    "admin_change_proposal": AdminChangeProposal,
    "policy_pack_lifecycle": PolicyPackLifecycleRecord,
    "external_agent_client_manifest": ExternalAgentPilotManifest,
    "external_agent_request": ExternalActionRequest,
    "external_agent_response": ExternalActionResponse,
    "external_agent_request_v1_1": ExternalAgentRequestV11,
    "external_agent_result_v1_1": ExternalAgentV11Result,
    "governed_pilot_workflow_spec": GovernedPilotWorkflowSpec,
    "governed_pilot_workflow_report": GovernedPilotWorkflowReport,
    "governed_pilot_workflow_verification": GovernedPilotWorkflowVerification,
    "governed_pilot_workflow_snapshot": GovernedPilotWorkflowSnapshot,
    "field_evidence_session": FieldEvidenceSession,
    "field_evidence_bundle": FieldEvidenceBundle,
    "field_evidence_verification": FieldEvidenceVerificationResult,
    "operator_attestation_binding": OperatorAttestationBinding,
    "operator_attestation_binding_verification": OperatorAttestationValidationResult,
    "strict_rc_promotion": StrictRCPromotionReport,
    "design_partner_field_evidence_snapshot": DesignPartnerFieldEvidenceSnapshot,
    "design_partner_field_pack": DesignPartnerFieldPackManifest,
    "release_train_manifest": ReleaseTrainManifest,
    "release_train_verification": ReleaseTrainVerificationReport,
    "pilot_ops_drill_report": PilotOpsDrillReport,
    "design_partner_handoff_manifest": DesignPartnerHandoffManifest,
    "design_partner_handoff_verification": DesignPartnerHandoffVerificationReport,
    "design_partner_handoff_snapshot": DesignPartnerHandoffSnapshot,
    "mainline_stack": StackGraphSpec,
    "mainline_stack_spec": StackGraphSpec,
    "mainline_stack_verification": StackGraphVerificationReport,
    "mainline_merge_rehearsal": MergeRehearsalReport,
    "gate_evidence_summary": GateEvidenceSummary,
    "rc_freeze_manifest": RcFreezeManifest,
    "rc_freeze_verification": RcFreezeVerificationReport,
    "mainline_rc_freeze_snapshot": MainlineRcFreezeSnapshot,
    "rc_gate_evidence_snapshot": RcGateEvidenceSnapshot,
    "rc_release_decision_snapshot": RcReleaseDecisionSnapshot,
    "enterprise_organization": EnterpriseOrganization,
    "enterprise_workspace": EnterpriseWorkspace,
    "enterprise_principal": EnterprisePrincipal,
    "enterprise_membership": EnterpriseWorkspaceMembership,
    "enterprise_device": EnterpriseDevice,
    "agent_enrollment_token": AgentEnrollmentToken,
    "agent_enrollment_request": AgentEnrollmentRequest,
    "agent_enrollment_decision": AgentEnrollmentDecision,
    "enrolled_agent": EnrolledAgent,
    "enterprise_workspace_snapshot": EnterpriseWorkspaceSnapshot,
    "workspace_permission_decision": WorkspacePermissionDecision,
}

OPERATOR_PANEL_SCHEMAS = {
    "control_plane_snapshot": ControlPlaneSnapshot,
}


def main() -> None:
    root = REPO_ROOT / "contracts" / "control_plane"
    root.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMAS.items():
        (root / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    operator_root = REPO_ROOT / "contracts" / "operator_panel" / "schemas"
    operator_root.mkdir(parents=True, exist_ok=True)
    for name, model in OPERATOR_PANEL_SCHEMAS.items():
        (operator_root / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
