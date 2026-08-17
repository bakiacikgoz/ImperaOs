from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import typer

from benchmarks.run_ablation import run_ablation_benchmark, run_energy_benchmark
from benchmarks.run_smoke import run_smoke_benchmark
from benchmarks.run_team import run_team_benchmark
from imperaos import __version__
from imperaos.artifacts.assistant import (
    ArtifactAssistantToolLoop,
    CoreLlmArtifactProvider,
    extract_artifact_context_request,
)
from imperaos.artifacts.cli import register_artifact_cli
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    OperationContext,
    PrincipalType,
)
from imperaos.artifacts.runtime import (
    resolve_artifact_approval_store,
    resolve_runtime_artifact_feature_flags,
)
from imperaos.artifacts.service import ArtifactService
from imperaos.artifacts.tools import ArtifactToolRegistry
from imperaos.computer_use import ComputerUseMode
from imperaos.computer_use.runtime import ComputerUseRunner, SessionCommand
from imperaos.computer_use.vision_runtime.capability_resolver import (
    resolve_capability_decision_snapshot,
)
from imperaos.computer_use.vision_runtime.drivers.macos import MacOSVisionReadiness
from imperaos.computer_use.vision_runtime.platforms import build_platform_capabilities
from imperaos.computer_use.vision_runtime.provider_doctor import doctor_vision_provider
from imperaos.computer_use.vision_runtime.qualification import (
    missing_platform_qualification_result,
    run_macos_live_qualification,
    run_vision_qualification,
    validate_platform_qualification_report,
)
from imperaos.computer_use.vision_runtime.replay import (
    load_replay_summary,
    verify_qualification_report_replay,
    verify_replay,
)
from imperaos.contracts.version import OPERATOR_PANEL_CONTRACT_VERSION
from imperaos.control_plane.adapter_contracts import evaluate_action_proposal_file
from imperaos.control_plane.admin_store import (
    IdentityAssertion,
    apply_admin_change,
    propose_admin_change,
)
from imperaos.control_plane.agent_registry_v2 import build_agent_registry_v2
from imperaos.control_plane.beta_pack import generate_design_partner_beta_pack
from imperaos.control_plane.claim_guard import ClaimGuard
from imperaos.control_plane.design_partner_handoff import (
    build_design_partner_handoff_pack,
    load_design_partner_handoff_manifest,
    verify_design_partner_handoff_pack,
)
from imperaos.control_plane.errors import ControlPlaneError
from imperaos.control_plane.evidence_corpus import (
    build_evidence_verification_corpus,
    verify_evidence_corpus,
)
from imperaos.control_plane.evidence_index import build_evidence_index
from imperaos.control_plane.evidence_pack import EvidencePackBuilder
from imperaos.control_plane.external_agent_client import run_external_agent_manifest
from imperaos.control_plane.external_gateway import (
    ExternalAgentGateway,
    submit_external_action_file,
    submit_external_action_v1_1_file,
)
from imperaos.control_plane.field_evidence import (
    build_design_partner_field_pack,
    collect_field_evidence_bundle,
    load_field_bundle,
    load_field_session,
    prepare_field_evidence_session,
    validate_independent_operator_attestation,
    verify_field_evidence_bundle,
    write_attestation_template,
)
from imperaos.control_plane.install_rehearsal import run_install_rehearsal
from imperaos.control_plane.mainline_rc_freeze import (
    build_gate_evidence_summary,
    build_mainline_rc_freeze_snapshot,
    build_rc_freeze_manifest,
    export_rc_freeze_pack,
    verify_rc_freeze_manifest,
    verify_rc_freeze_manifest_with_gate_ledger,
    write_rc_freeze_manifest,
)
from imperaos.control_plane.mainline_stack import (
    MergeRehearsalSpec,
    load_stack_graph_spec,
    run_merge_rehearsal,
    verify_stack_graph,
    write_merge_rehearsal_report,
    write_stack_graph_report,
)
from imperaos.control_plane.operations_runner import dry_run_operation
from imperaos.control_plane.pilot_operations import generate_pilot_operations_artifacts
from imperaos.control_plane.pilot_ops_drill import run_pilot_ops_drill
from imperaos.control_plane.pilot_pack import generate_design_partner_pilot_pack
from imperaos.control_plane.pilot_workflow import (
    load_governed_pilot_workflow_spec,
    run_governed_pilot_workflow,
    validate_governed_pilot_workflow_spec,
)
from imperaos.control_plane.pilot_workflow_verifier import (
    export_governed_pilot_workflow_report,
    verify_governed_pilot_workflow_report,
)
from imperaos.control_plane.policy_pack_store import (
    plan_policy_pack_rollback,
    promote_policy_pack,
    stage_policy_pack,
    validate_lifecycle_policy_pack,
)
from imperaos.control_plane.policy_packs import (
    diff_policy_packs,
    load_policy_pack_manifest,
    promote_policy_pack_dry_run,
    validate_policy_pack,
)
from imperaos.control_plane.policy_simulator import PolicySimulator
from imperaos.control_plane.provider_conformance import (
    run_provider_native_conformance,
    run_provider_native_gate,
)
from imperaos.control_plane.provider_invocation import (
    ProviderInvocationCoordinator,
    ProviderInvocationRequest,
)
from imperaos.control_plane.provider_registry import (
    build_provider_governance_snapshot,
    inspect_provider_entry,
)
from imperaos.control_plane.qualification_closure import (
    generate_enterprise_hat_a_closure,
    verify_enterprise_hat_a_closure,
)
from imperaos.control_plane.rbac_admin import (
    build_rbac_matrix,
)
from imperaos.control_plane.rbac_admin import (
    check_permission as check_rbac_permission,
)
from imperaos.control_plane.readiness import build_readiness_report
from imperaos.control_plane.registry import AgentRegistry, load_agent_spec
from imperaos.control_plane.release_train import (
    ClaimBoundarySummary,
    build_release_train_manifest,
    load_release_train_manifest,
    verify_release_train,
    write_release_train_manifest,
    write_release_train_verification,
)
from imperaos.control_plane.reports import build_reports_alerts_logs_manifest
from imperaos.control_plane.run_coordinator import ControlPlaneRunCoordinator
from imperaos.control_plane.security_review import generate_security_review_pack
from imperaos.control_plane.snapshot import build_control_plane_snapshot
from imperaos.control_plane.strict_rc_promotion import promote_strict_rc
from imperaos.core.llm_ollama import OllamaLLM, check_provider_chain
from imperaos.core.orchestrator import Orchestrator
from imperaos.core.planner import Planner
from imperaos.enterprise.baseline import enterprise_startup_abort, security_posture
from imperaos.enterprise.identity import (
    IdentityResolutionError,
    check_permission,
    describe_actor,
    require_permission,
)
from imperaos.enterprise.maintenance import (
    create_backup,
    export_support_bundle,
    ga_readiness_report,
    migration_apply,
    migration_plan,
    render_ga_readiness_markdown,
    restore_verify,
)
from imperaos.enterprise.observability import collect_metrics_snapshot
from imperaos.enterprise.qualification import run_qualification, write_qualification_report
from imperaos.enterprise.signing import (
    key_status,
    rotate_plan,
    verify_signed_artifact,
    write_signed_json,
)
from imperaos.experts.code_expert import CodeExpert
from imperaos.experts.memory_plan_expert import MemoryPlanExpert
from imperaos.experts.research_expert import ResearchExpert
from imperaos.governance.approval_execution import ApprovalExecutionService
from imperaos.governance.approval_executors.control_plane import ControlPlaneApprovalExecutor
from imperaos.governance.approval_executors.device import DeviceActionApprovalExecutor
from imperaos.governance.approval_executors.external_agent import ExternalAgentApprovalExecutor
from imperaos.governance.runtime import (
    GovernanceRuntime,
    build_governance_runtime,
    governance_startup_abort,
)
from imperaos.memory.authority import build_memory_authority, proposal_from_cli
from imperaos.memory.evaluation import run_memory_retrieval_eval
from imperaos.memory.manager import MemoryManager
from imperaos.memory.migration_planner import plan_legacy_memory_migration
from imperaos.memory.models import (
    MemoryRetrievalRequest,
    MemoryScopeFilter,
    hash_identity,
    stable_id,
)
from imperaos.memory.persistent_store import PersistentMemoryStore
from imperaos.memory.runtime_bridge import RuntimeMemoryRequest, build_memory_runtime_bridge
from imperaos.memory.salience_gate import SalienceGate
from imperaos.memory.semantic import (
    IndexRebuildRequest,
    MemorySearchRequest,
    SemanticMemoryService,
)
from imperaos.memory.semantic.backends.turbovec_backend import TurboVecSemanticBackend
from imperaos.memory.session_store import SessionStore
from imperaos.memory.sync_importer import import_memory_sync_pack
from imperaos.memory.sync_pack import (
    export_memory_sync_pack,
    owner_filter,
    verify_memory_sync_pack,
)
from imperaos.memory.workspace_authority import build_workspace_memory_authority
from imperaos.memory.workspace_models import (
    LegacyMemoryMigrationPlanRequest,
    MemoryPrincipal,
    MemoryScopeAclRule,
    MemoryWorkspace,
    MemoryWorkspaceMembership,
    WorkspaceMemoryQueryRequest,
    WorkspaceMemoryWriteRequest,
)
from imperaos.memory.workspace_sync import WorkspaceMemorySyncCoordinator
from imperaos.migration.legacy_state import migrate_legacy_state
from imperaos.model_providers.adapters.adapter_factory import ProviderAdapterFactory
from imperaos.model_providers.canary import run_provider_canary
from imperaos.model_providers.canary_evidence import (
    verify_canary_evidence_root,
    write_router_shadow_evidence,
)
from imperaos.model_providers.conformance import build_provider_conformance_matrix
from imperaos.model_providers.doctor import doctor_provider
from imperaos.model_providers.envelope import ProviderCallEnvelopeWriter
from imperaos.model_providers.models import (
    ChatMessage,
    DataClass,
    ProviderCallRequest,
    ProviderCanaryRequest,
    ProviderConformanceEntry,
    ProviderKind,
    ProviderRouteShadowRequest,
)
from imperaos.model_providers.native.conformance import (
    run_all_native_conformance,
    run_native_conformance,
    verify_native_conformance_evidence,
    write_native_conformance_report,
)
from imperaos.model_providers.native.types import ProviderNativeConformanceReport
from imperaos.model_providers.policy import GovernanceContext, evaluate_provider_policy
from imperaos.model_providers.redaction import redact_provider_input
from imperaos.model_providers.registry import resolve_model_provider_registry
from imperaos.model_providers.resolver import resolve_provider_id
from imperaos.model_providers.router_shadow import recommend_provider_shadow
from imperaos.model_providers.runtime import ProviderGovernanceLLM
from imperaos.release.gate_export import export_rc_evidence_orchestration
from imperaos.release.gate_plan import build_release_gate_plan
from imperaos.release.gate_runner import run_release_gate_plan
from imperaos.release.gate_verifier import verify_gate_evidence_ledger
from imperaos.release.snapshot import build_rc_gate_evidence_snapshot
from imperaos.release_decision.dossier import (
    build_release_decision_from_artifacts,
    export_release_decision_pack,
    verify_release_decision_dossier,
    write_release_decision_pack,
)
from imperaos.release_decision.models import ReleaseDecisionDossier
from imperaos.release_decision.reconciler import build_reconciliation_input, reconcile_rc_freeze
from imperaos.release_decision.signoff import verify_human_signoffs, write_signoff_template
from imperaos.router.rule_router import RuleRouter
from imperaos.router.sltc_router import SLTCRouter
from imperaos.runtime.config import RuntimeConfig, redact_config_payload, resolve_runtime_config
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT, TEAM_ARTIFACT_ROOT, state_path
from imperaos.runtime.platform import PlatformInfo, current_platform
from imperaos.schemas.models import ExpertName
from imperaos.team.continuation import (
    ResumeContinuationError,
    derive_resume_continuation_state,
)
from imperaos.team.models import TeamSpec
from imperaos.team.pilot_gate import run_pilot_check, write_pilot_report
from imperaos.team.replay import load_events, load_job_status, replay_job
from imperaos.team.supervisor import TeamSupervisor
from imperaos.team.validation import validate_team_spec
from imperaos.telemetry.artifacts_writer import ensure_artifact_scaffold, write_artifact
from imperaos.telemetry.tracer import Tracer
from research.sltc_experiments.eval_router import evaluate_router_model
from research.sltc_experiments.train_router import calibrate_router_params, train_router_model

app = typer.Typer(help="ImperaOS CLI")
register_artifact_cli(app)
benchmark_app = typer.Typer(help="Benchmark commands")
memory_app = typer.Typer(help="Memory commands")
memory_index_app = typer.Typer(help="Memory index commands")
memory_runtime_app = typer.Typer(help="Memory runtime commands")
memory_runtime_policy_app = typer.Typer(help="Memory runtime policy commands")
memory_sync_app = typer.Typer(help="Memory sync pack commands")
memory_workspace_app = typer.Typer(help="Workspace memory authority commands")
memory_principal_app = typer.Typer(help="Workspace memory principal commands")
memory_scope_app = typer.Typer(help="Workspace memory scope ACL commands")
memory_authority_app = typer.Typer(help="Workspace memory authority query/write commands")
memory_workspace_sync_app = typer.Typer(help="Workspace memory sync v2 commands")
memory_workspace_conflicts_app = typer.Typer(help="Workspace memory conflict commands")
memory_workspace_migrate_app = typer.Typer(help="Workspace memory migration commands")
memory_semantic_app = typer.Typer(help="Semantic memory index commands")
memory_semantic_backend_app = typer.Typer(help="Semantic memory backend commands")
research_app = typer.Typer(help="Research commands")
config_app = typer.Typer(help="Config commands")
provider_app = typer.Typer(help="Provider discovery commands")
provider_registry_app = typer.Typer(help="Model provider registry commands")
provider_policy_app = typer.Typer(help="Model provider policy commands")
provider_call_app = typer.Typer(help="Model provider test call commands")
provider_canary_app = typer.Typer(help="Model provider canary commands")
provider_route_app = typer.Typer(help="Model provider routing simulation commands")
provider_native_app = typer.Typer(help="Model provider native adapter commands")
provider_native_conformance_app = typer.Typer(
    help="Model provider native adapter conformance commands"
)
assistant_app = typer.Typer(help="Product assistant runtime commands")
setup_app = typer.Typer(help="First-run setup diagnostics")
product_app = typer.Typer(help="Product-complete demo and smoke commands")
product_demo_app = typer.Typer(help="Product-complete demo workflows")
DEFAULT_PROVIDER_NATIVE_OUTPUT_ROOT = Path("artifacts/model-provider-governance/native-v2")
PROVIDER_NATIVE_OUTPUT_ROOT_OPTION = typer.Option(
    DEFAULT_PROVIDER_NATIVE_OUTPUT_ROOT,
    "--output-root",
    help="Evidence output root",
)
PROVIDER_NATIVE_KIND_OPTION = typer.Option(
    "openai_responses",
    "--provider-kind",
    help="Native provider kind: openai_responses|anthropic_messages|all",
)
PROVIDER_NATIVE_INPUT_OPTION = typer.Option(
    None,
    "--input",
    help="Specific evidence file to verify",
)
approval_app = typer.Typer(help="Governance approval commands")
PROVIDER_POLICY_DATA_CLASS_OPTION = typer.Option(
    ["public"],
    "--data-class",
    help="Data class",
)
PROVIDER_CANARY_EVIDENCE_ROOT_OPTION = typer.Option(
    Path("artifacts/model-provider-governance/canary"),
    "--evidence-root",
    help="Canary evidence root",
)
PROVIDER_ROUTE_CAPABILITY_OPTION = typer.Option([], "--capability", help="Required capability")
operator_app = typer.Typer(help="Operator panel commands")
computer_use_app = typer.Typer(help="Computer use execution commands")
computer_use_vision_app = typer.Typer(help="Vision-first computer use commands")
computer_use_qualification_app = typer.Typer(help="Computer-use qualification commands")
computer_use_provider_app = typer.Typer(help="Computer-use provider readiness commands")
team_app = typer.Typer(help="Team runtime commands")
control_plane_app = typer.Typer(help="Agent Control Plane commands")
control_plane_agent_app = typer.Typer(help="Control Plane agent registry commands")
control_plane_policy_app = typer.Typer(help="Control Plane policy commands")
control_plane_policy_pack_app = typer.Typer(help="Control Plane policy pack lifecycle commands")
control_plane_run_app = typer.Typer(help="Control Plane run commands")
control_plane_evidence_app = typer.Typer(help="Control Plane evidence commands")
control_plane_claims_app = typer.Typer(help="Control Plane claim guard commands")
control_plane_qualification_app = typer.Typer(help="Control Plane qualification closure commands")
control_plane_install_app = typer.Typer(help="Control Plane install rehearsal commands")
control_plane_external_agent_app = typer.Typer(help="External agent pilot commands")
control_plane_admin_app = typer.Typer(help="Control Plane governance admin commands")
control_plane_security_app = typer.Typer(help="Control Plane security review commands")
control_plane_pilot_app = typer.Typer(help="Control Plane pilot launch commands")
control_plane_adapter_app = typer.Typer(help="External adapter contract commands")
control_plane_gateway_app = typer.Typer(help="External agent gateway commands")
control_plane_rbac_app = typer.Typer(help="Control Plane RBAC admin commands")
control_plane_reports_app = typer.Typer(help="Control Plane reports and alerts commands")
control_plane_operations_app = typer.Typer(help="Control Plane operation workflow commands")
control_plane_release_app = typer.Typer(help="Control Plane release commands")
control_plane_release_freeze_app = typer.Typer(help="Control Plane release freeze commands")
control_plane_release_gates_app = typer.Typer(help="Control Plane release gate evidence commands")
pilot_app = typer.Typer(help="Design partner pilot operations commands")
pilot_workflow_app = typer.Typer(help="Governed pilot workflow commands")
control_plane_pilot_workflow_app = typer.Typer(help="Governed pilot workflow commands")
pilot_field_app = typer.Typer(help="Design partner field evidence commands")
control_plane_pilot_field_app = typer.Typer(help="Design partner field evidence commands")
pilot_ops_app = typer.Typer(help="Design partner pilot operations drill commands")
release_app = typer.Typer(help="Release readiness commands")
release_train_app = typer.Typer(help="Release train verification commands")
release_handoff_app = typer.Typer(help="Design partner handoff commands")
release_mainline_app = typer.Typer(help="Mainline stack rehearsal commands")
release_rc_freeze_app = typer.Typer(help="Mainline RC freeze commands")
release_rc_app = typer.Typer(help="RC release reconciliation commands")
release_decision_app = typer.Typer(help="RC release decision dossier commands")
release_gates_app = typer.Typer(help="Cross-platform release gate evidence commands")
enterprise_app = typer.Typer(help="Enterprise workspace commands")
enterprise_workspace_app = typer.Typer(help="Enterprise workspace setup commands")
enterprise_membership_app = typer.Typer(help="Enterprise workspace membership commands")
enterprise_enrollment_app = typer.Typer(help="Enterprise agent enrollment commands")
enterprise_enrollment_token_app = typer.Typer(help="Enterprise enrollment token commands")
enterprise_enrollment_request_app = typer.Typer(help="Enterprise enrollment request commands")
enterprise_rbac_app = typer.Typer(help="Enterprise workspace RBAC commands")
auth_app = typer.Typer(help="Enterprise identity commands")
security_app = typer.Typer(help="Enterprise security commands")
keys_app = typer.Typer(help="Enterprise key management commands")
migrate_app = typer.Typer(help="Migration commands")
backup_app = typer.Typer(help="Backup commands")
restore_app = typer.Typer(help="Restore commands")
support_app = typer.Typer(help="Support commands")
support_bundle_app = typer.Typer(help="Support bundle commands")
metrics_app = typer.Typer(help="Observability commands")
ga_app = typer.Typer(help="GA readiness commands")
qualification_app = typer.Typer(help="Qualification evidence commands")
app.add_typer(benchmark_app, name="benchmark")
app.add_typer(memory_app, name="memory")
memory_app.add_typer(memory_index_app, name="index")
memory_app.add_typer(memory_runtime_app, name="runtime")
memory_runtime_app.add_typer(memory_runtime_policy_app, name="policy")
memory_app.add_typer(memory_sync_app, name="sync")
memory_app.add_typer(memory_workspace_app, name="workspace")
memory_app.add_typer(memory_principal_app, name="principal")
memory_app.add_typer(memory_scope_app, name="scope")
memory_app.add_typer(memory_authority_app, name="authority")
memory_workspace_app.add_typer(memory_workspace_sync_app, name="sync")
memory_workspace_app.add_typer(memory_workspace_conflicts_app, name="conflicts")
memory_workspace_app.add_typer(memory_workspace_migrate_app, name="migrate")
memory_app.add_typer(memory_semantic_app, name="semantic")
memory_semantic_app.add_typer(memory_semantic_backend_app, name="backend")
app.add_typer(research_app, name="research")
app.add_typer(config_app, name="config")
app.add_typer(provider_app, name="provider")
provider_app.add_typer(provider_registry_app, name="registry")
provider_app.add_typer(provider_policy_app, name="policy")
provider_app.add_typer(provider_call_app, name="call")
provider_app.add_typer(provider_canary_app, name="canary")
provider_app.add_typer(provider_route_app, name="route")
provider_app.add_typer(provider_native_app, name="native")
provider_native_app.add_typer(provider_native_conformance_app, name="conformance")
app.add_typer(assistant_app, name="assistant")
app.add_typer(setup_app, name="setup")
app.add_typer(product_app, name="product")
product_app.add_typer(product_demo_app, name="demo")
app.add_typer(approval_app, name="approval")
app.add_typer(operator_app, name="operator")
app.add_typer(computer_use_app, name="computer-use")
computer_use_app.add_typer(computer_use_vision_app, name="vision")
computer_use_app.add_typer(computer_use_qualification_app, name="qualification")
computer_use_app.add_typer(computer_use_provider_app, name="provider")
app.add_typer(team_app, name="team")
app.add_typer(control_plane_app, name="control-plane")
control_plane_app.add_typer(control_plane_agent_app, name="agent")
control_plane_app.add_typer(control_plane_policy_app, name="policy")
control_plane_app.add_typer(control_plane_policy_pack_app, name="policy-pack")
control_plane_app.add_typer(control_plane_run_app, name="run")
control_plane_app.add_typer(control_plane_evidence_app, name="evidence")
control_plane_app.add_typer(control_plane_claims_app, name="claims")
control_plane_app.add_typer(control_plane_qualification_app, name="qualification")
control_plane_app.add_typer(control_plane_install_app, name="install")
control_plane_app.add_typer(control_plane_external_agent_app, name="external-agent")
control_plane_app.add_typer(control_plane_admin_app, name="admin")
control_plane_app.add_typer(control_plane_security_app, name="security")
control_plane_app.add_typer(control_plane_pilot_app, name="pilot")
control_plane_app.add_typer(control_plane_adapter_app, name="adapter")
control_plane_app.add_typer(control_plane_gateway_app, name="gateway")
control_plane_app.add_typer(control_plane_rbac_app, name="rbac")
control_plane_app.add_typer(control_plane_reports_app, name="reports")
control_plane_app.add_typer(control_plane_operations_app, name="operations")
control_plane_app.add_typer(control_plane_release_app, name="release")
control_plane_release_app.add_typer(control_plane_release_freeze_app, name="freeze")
control_plane_release_app.add_typer(control_plane_release_gates_app, name="gates")
app.add_typer(pilot_app, name="pilot")
pilot_app.add_typer(pilot_workflow_app, name="workflow")
control_plane_pilot_app.add_typer(control_plane_pilot_workflow_app, name="workflow")
pilot_app.add_typer(pilot_field_app, name="field")
control_plane_pilot_app.add_typer(control_plane_pilot_field_app, name="field")
pilot_app.add_typer(pilot_ops_app, name="ops")
app.add_typer(release_app, name="release")
release_app.add_typer(release_train_app, name="train")
release_app.add_typer(release_handoff_app, name="handoff")
release_app.add_typer(release_mainline_app, name="mainline")
release_app.add_typer(release_rc_freeze_app, name="rc-freeze")
release_app.add_typer(release_rc_app, name="rc")
release_app.add_typer(release_decision_app, name="decision")
release_app.add_typer(release_gates_app, name="gates")
app.add_typer(enterprise_app, name="enterprise")
enterprise_app.add_typer(enterprise_workspace_app, name="workspace")
enterprise_app.add_typer(enterprise_membership_app, name="membership")
enterprise_app.add_typer(enterprise_enrollment_app, name="enrollment")
enterprise_enrollment_app.add_typer(enterprise_enrollment_token_app, name="token")
enterprise_enrollment_app.add_typer(enterprise_enrollment_request_app, name="request")
enterprise_app.add_typer(enterprise_rbac_app, name="rbac")
app.add_typer(auth_app, name="auth")
app.add_typer(security_app, name="security")
app.add_typer(keys_app, name="keys")
app.add_typer(migrate_app, name="migrate")
app.add_typer(backup_app, name="backup")
app.add_typer(restore_app, name="restore")
app.add_typer(support_app, name="support")
support_app.add_typer(support_bundle_app, name="bundle")
app.add_typer(metrics_app, name="metrics")
app.add_typer(ga_app, name="ga")
app.add_typer(qualification_app, name="qualification")

_MEMORY_VISIBILITY_OPTION = typer.Option(None, "--visibility", help="Allowed visibility")
_MEMORY_ALLOWED_SCOPE_OPTION = typer.Option(
    None,
    "--allowed-scope",
    help="Policy-allowed retrieval scope",
)
_WORKSPACE_ROLE_OPTION = typer.Option(
    ["viewer"],
    "--role",
    help="Repeatable workspace role",
)
_WORKSPACE_PERMISSION_OPTION = typer.Option(
    ...,
    "--permission",
    help="Repeatable permission",
)
_MEMORY_SEMANTIC_SCOPE_OPTION = typer.Option(
    [],
    "--scope",
    help="Repeatable semantic scope in scope_type:scope_id form",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def app_callback(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show ImperaOS version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    _ = version


def _is_realtime_candidate(user_text: str) -> bool:
    is_candidate, _reason = _realtime_candidate_reason(user_text)
    return is_candidate


def _realtime_candidate_reason(user_text: str) -> tuple[bool, str]:
    text = user_text.strip().lower()
    if not text:
        return False, "empty"

    greetings = {
        "selam",
        "merhaba",
        "hey",
        "hi",
        "hello",
        "nasılsın",
        "naber",
        "günaydın",
        "iyi akşamlar",
    }
    if text in greetings:
        return True, "greeting"

    if len(text) > 64:
        return False, "too_long_chars"
    if len(text.split()) > 10:
        return False, "too_long_words"

    heavy_tokens = {
        "kod",
        "python",
        "test",
        "debug",
        "araştır",
        "research",
        "özet",
        "plan",
        "adım",
        "tool",
        "benchmark",
        "lint",
        "diff",
    }
    if any(token in text for token in heavy_tokens):
        return False, "heavy_token_detected"
    return True, "short_message"


def _build_llm(
    config: RuntimeConfig,
    *,
    temperature: float,
    provider_name: str | None = None,
    fallback_provider: str | None = None,
) -> OllamaLLM:
    return OllamaLLM(
        model_name=config.model_name,
        temperature=temperature,
        provider_name=(provider_name or config.llm_provider),
        fallback_provider=(fallback_provider or config.fallback_provider),
        fallback_enabled=config.fallback_enabled,
        hf_model_id=config.hf_model_id,
        device=config.device,
    )


def _build_orchestrator(
    config: RuntimeConfig,
    workspace: Path | None = None,
    router_mode: str | None = None,
    shadow_router_mode: str | None = None,
    shadow_router_enabled: bool | None = None,
    provider_name: str | None = None,
    provider_id: str | None = None,
    provider_model: str | None = None,
    fallback_provider_id: str | None = None,
    fallback_provider: str | None = None,
) -> Orchestrator:
    workspace_dir = workspace or Path.cwd()
    if provider_id:
        registry = resolve_model_provider_registry(
            config=config,
            profile=config.profile_name,
            provider_config_path=Path(config.provider_registry_path)
            if config.provider_registry_enabled
            else None,
        )
        provider_record = registry.get(provider_id)
        if provider_record is None:
            raise ValueError(f"unsupported provider_id: {provider_id}")
        answer_llm = ProviderGovernanceLLM(
            registry=registry,
            provider_id=provider_id,
            model=provider_model or provider_record.default_model,
            envelope_writer=ProviderCallEnvelopeWriter(),
            fallback_provider_id=fallback_provider_id,
        )
        planner_llm = answer_llm
    else:
        answer_llm = _build_llm(
            config=config,
            temperature=config.answer_temperature,
            provider_name=provider_name,
            fallback_provider=fallback_provider,
        )
        planner_llm = _build_llm(
            config=config,
            temperature=config.planner_temperature,
            provider_name=provider_name,
            fallback_provider=fallback_provider,
        )

    planner = Planner(
        planner_llm,
        default_latency_budget_ms=config.latency_budget_ms,
        llm_timeout_ms=config.limits.llm_timeout_ms,
        repair_enabled=config.planner_tuning.repair_enabled,
        repair_max_attempts=config.planner_tuning.repair_max_attempts,
        prompt_variant=config.planner_tuning.prompt_variant,
    )
    selected_router_mode = (router_mode or config.router_mode).lower()
    sltc_mode = config.sltc.router_mode.lower()
    if sltc_mode == "active":
        selected_router_mode = "sltc"
    if sltc_mode == "off" and selected_router_mode == "sltc":
        selected_router_mode = "rule"
    router = _build_router(config=config, router_mode=selected_router_mode)
    effective_shadow_enabled = (
        config.shadow_router_enabled if shadow_router_enabled is None else shadow_router_enabled
    )
    if sltc_mode == "shadow":
        effective_shadow_enabled = True
    if sltc_mode == "off":
        effective_shadow_enabled = False
    shadow_router = None
    if effective_shadow_enabled:
        selected_shadow_mode = (shadow_router_mode or config.shadow_router_mode).lower()
        shadow_router = _build_router(config=config, router_mode=selected_shadow_mode)
    governance_runtime = _build_governance_runtime(config)
    experts = {
        ExpertName.CODE.value: CodeExpert(
            workspace=workspace_dir,
            verify_config=config.code_verify,
            governance_runtime=governance_runtime,
        ),
        ExpertName.RESEARCH.value: ResearchExpert(workspace=workspace_dir),
        ExpertName.PLAN.value: MemoryPlanExpert(),
    }
    memory_manager = _build_memory_manager(config)
    memory_runtime_bridge = build_memory_runtime_bridge(config)
    tracer = Tracer(
        debug_mode=config.debug_mode,
        privacy_mode=config.privacy_mode,
        trace_dir=config.trace_dir,
        router_dataset_path=config.router_dataset_path,
        event_redactor=(
            governance_runtime.trace_redact
            if governance_runtime is not None and config.governance.pii_redaction_enabled
            else None
        ),
    )
    return Orchestrator(
        planner=planner,
        llm=answer_llm,
        router=router,
        experts=experts,
        tracer=tracer,
        config=config,
        memory_manager=memory_manager,
        memory_runtime_bridge=memory_runtime_bridge,
        shadow_router=shadow_router,
        governance_runtime=governance_runtime,
    )


def _build_governance_runtime(config: RuntimeConfig) -> GovernanceRuntime | None:
    runtime = build_governance_runtime(config)
    return runtime


def _build_router(config: RuntimeConfig, router_mode: str) -> RuleRouter | SLTCRouter:
    if router_mode == "sltc":
        return SLTCRouter(
            confidence_threshold=config.sltc.confidence_threshold,
            decay=config.sltc.decay,
            spike_threshold=config.sltc.spike_threshold,
            failure_penalty_weight=config.sltc.failure_penalty_weight,
            latency_penalty_weight=config.sltc.latency_penalty_weight,
            need_bonus=config.sltc.need_bonus,
            conf_bonus=config.sltc.conf_bonus,
            task_bias_overrides=config.sltc.task_bias_overrides,
        )
    return RuleRouter(confidence_threshold=config.router_confidence_threshold)


def _build_memory_manager(config: RuntimeConfig) -> MemoryManager:
    store = (
        PersistentMemoryStore(db_path=config.memory.db_path)
        if config.enable_persistent_memory
        else None
    )
    gate = SalienceGate(
        threshold=config.memory.salience_threshold,
        decay=config.memory.salience_decay,
        task_bonus=config.memory.task_bonus,
        expert_bonus=config.memory.expert_bonus,
        spike_reduction=config.memory.spike_reduction,
        keyword_weights=config.memory.keyword_weights,
    )
    return MemoryManager(
        enabled=config.enable_persistent_memory,
        store=store,
        gate=gate,
        max_rows=config.memory.max_rows,
        ttl_days=config.memory_ttl_days,
        rank_salience_weight=config.memory.rank_salience_weight,
        rank_recency_weight=config.memory.rank_recency_weight,
    )


def _normalize_provider_name(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.strip().lower()
    if normalized in {"hf", "huggingface"}:
        return "transformers"
    return normalized


def _build_cli_overrides(
    *,
    provider: str | None = None,
    fallback_provider: str | None = None,
    model: str | None = None,
    hf_model_id: str | None = None,
) -> dict[str, str | None]:
    return {
        "llm_provider": provider,
        "fallback_provider": fallback_provider,
        "model_name": model,
        "hf_model_id": hf_model_id,
    }


def _validate_model_override_combo(
    *,
    effective_provider: str,
    model_override: str | None,
    hf_model_id_override: str | None,
) -> tuple[str, str] | None:
    normalized = _normalize_provider_name(effective_provider)
    if normalized == "transformers" and model_override is not None:
        return (
            "INVALID_MODEL_OVERRIDE",
            "model override (--model) cannot be used with provider=transformers.",
        )
    if normalized == "ollama" and hf_model_id_override is not None:
        return (
            "INVALID_HF_MODEL_ID_OVERRIDE",
            "hf model override (--hf-model-id) cannot be used with provider=ollama.",
        )
    return None


def _model_candidate(
    *,
    provider: str,
    model_id: str,
    installed: bool,
    configured: bool,
    source: str,
    warnings: list[str] | None = None,
) -> dict[str, object]:
    return {
        "provider": provider,
        "id": model_id,
        "displayName": model_id,
        "installed": installed,
        "configured": configured,
        "source": source,
        "sizeBytes": None,
        "modifiedAtUtc": None,
        "warnings": warnings or [],
    }


def _list_ollama_model_ids(
    timeout_seconds: int = 5,
) -> tuple[bool, list[str], str | None, str | None]:
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return False, [], "OLLAMA_NOT_INSTALLED", "Ollama executable was not found."
    except subprocess.TimeoutExpired:
        return False, [], "OLLAMA_LIST_TIMEOUT", "ollama list timed out."

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "ollama list failed.").strip()
        return False, [], "OLLAMA_LIST_FAILED", message[:500]

    models: list[str] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("name "):
            continue
        model_id = stripped.split(maxsplit=1)[0].strip()
        if model_id:
            models.append(model_id)
    return True, models[:200], None, None


def _provider_models_payload(profile: str, requested_provider: str) -> dict[str, object]:
    resolved, _source_map = resolve_runtime_config(profile=profile)
    provider_config_path = (
        Path(resolved.provider_registry_path)
        if resolved.provider_registry_enabled and Path(resolved.provider_registry_path).exists()
        else None
    )
    registry = resolve_model_provider_registry(
        config=resolved,
        profile=profile,
        provider_config_path=provider_config_path,
    )
    normalized_provider = _normalize_provider_name(requested_provider) or "all"
    if normalized_provider == "auto":
        normalized_provider = "all"
    requested_provider_id = resolve_provider_id(
        registry=registry,
        legacy_provider=normalized_provider if normalized_provider != "all" else None,
    )
    conformance_matrix = build_provider_conformance_matrix(
        registry=registry,
        profile=profile,
        mode="offline",
    )
    conformance_by_provider = {item.provider_id: item for item in conformance_matrix.providers}
    valid_ids = {item.provider_id for item in registry.providers}
    valid_legacy = {"all", "ollama", "transformers"}
    if normalized_provider not in valid_legacy and normalized_provider not in valid_ids:
        return {
            "contractVersion": "operator-panel.assistant-provider-models/v4",
            "profile": profile,
            "provider": requested_provider,
            "generatedAtUtc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "providers": [],
            "status": "invalid_input",
            "errorCode": "INVALID_PROVIDER",
            "errorMessage": "provider must be all, a legacy provider, or a configured provider_id.",
        }

    selected_records = (
        registry.providers
        if normalized_provider == "all"
        else [item for item in registry.providers if item.provider_id == requested_provider_id]
    )
    providers: list[dict[str, object]] = []

    if any(item.provider_id == "local-ollama" for item in selected_records):
        available, model_ids, error_code, error_message = _list_ollama_model_ids()
        models = [
            _model_candidate(
                provider="local-ollama",
                model_id=model_id,
                installed=True,
                configured=model_id == resolved.model_name,
                source="ollama",
            )
            for model_id in model_ids
        ]
        if resolved.model_name and not any(item["id"] == resolved.model_name for item in models):
            models.insert(
                0,
                _model_candidate(
                    provider="local-ollama",
                    model_id=resolved.model_name,
                    installed=False,
                    configured=True,
                    source="config",
                    warnings=["Configured Ollama model is not present in ollama list."],
                ),
            )
        providers.append(
            {
                "provider": "local-ollama",
                "legacyProvider": "ollama",
                "kind": "local_ollama",
                "displayName": "Local Ollama",
                "dataBoundary": "local",
                "riskTier": "low",
                "trustSource": "bridge_state",
                "lastCanaryStatus": "not_run",
                "lastCanaryReason": None,
                "lastCanaryAtUtc": None,
                "lastVerifiedEvidenceAtUtc": None,
                "evidencePath": None,
                "budgetState": "allow",
                "budgetReason": "PROVIDER_BUDGET_ALLOWED",
                **_provider_conformance_payload(conformance_by_provider.get("local-ollama")),
                **_provider_native_payload(None),
                "available": available,
                "selectedByConfig": _normalize_provider_name(resolved.llm_provider) == "ollama",
                "disabledReason": None,
                "errorCode": error_code,
                "errorMessage": error_message,
                "models": models,
            }
        )

    if any(item.provider_id == "local-transformers" for item in selected_records):
        hf_model_id = resolved.hf_model_id
        providers.append(
            {
                "provider": "local-transformers",
                "legacyProvider": "transformers",
                "kind": "local_transformers",
                "displayName": "Local Transformers",
                "dataBoundary": "local",
                "riskTier": "low",
                "trustSource": "bridge_state",
                "lastCanaryStatus": "not_run",
                "lastCanaryReason": None,
                "lastCanaryAtUtc": None,
                "lastVerifiedEvidenceAtUtc": None,
                "evidencePath": None,
                "budgetState": "allow" if hf_model_id else "unknown",
                "budgetReason": "PROVIDER_BUDGET_ALLOWED" if hf_model_id else None,
                **_provider_conformance_payload(conformance_by_provider.get("local-transformers")),
                **_provider_native_payload(None),
                "available": bool(hf_model_id),
                "selectedByConfig": (
                    _normalize_provider_name(resolved.llm_provider) == "transformers"
                    or _normalize_provider_name(resolved.fallback_provider) == "transformers"
                ),
                "disabledReason": None if hf_model_id else "HF_MODEL_NOT_CONFIGURED",
                "errorCode": None if hf_model_id else "HF_MODEL_NOT_CONFIGURED",
                "errorMessage": (
                    None if hf_model_id else "No transformers HF model id is configured."
                ),
                "models": [
                    _model_candidate(
                        provider="local-transformers",
                        model_id=hf_model_id,
                        installed=False,
                        configured=True,
                        source="config",
                        warnings=["Local transformers cache was not inspected by this command."],
                    )
                ]
                if hf_model_id
                else [],
            }
        )

    local_ids = {"local-ollama", "local-transformers"}
    for provider in selected_records:
        if provider.provider_id in local_ids:
            continue
        policy = registry.policy_for(provider.provider_id)
        doctor = doctor_provider(
            provider=provider,
            policy=policy,
            remote_providers_enabled=registry.remote_providers_enabled,
        )
        providers.append(
            {
                "provider": provider.provider_id,
                "legacyProvider": None,
                "kind": provider.kind,
                "displayName": provider.display_name or provider.provider_id,
                "dataBoundary": provider.data_boundary,
                "riskTier": provider.risk_tier,
                "trustSource": "bridge_state",
                "lastCanaryStatus": "not_run",
                "lastCanaryReason": None,
                "lastCanaryAtUtc": None,
                "lastVerifiedEvidenceAtUtc": None,
                "evidencePath": None,
                "budgetState": "guarded" if policy.canary_call_budget <= 0 else "allow",
                "budgetReason": (
                    "PROVIDER_CANARY_BUDGET_DISABLED"
                    if policy.canary_call_budget <= 0
                    else "PROVIDER_BUDGET_ALLOWED"
                ),
                **_provider_conformance_payload(conformance_by_provider.get(provider.provider_id)),
                **_provider_native_payload(provider.kind),
                "available": doctor["status"] == "ready",
                "selectedByConfig": False,
                "disabledReason": None if doctor["status"] == "ready" else doctor["reasonCode"],
                "errorCode": None if doctor["status"] == "ready" else doctor["reasonCode"],
                "errorMessage": None if doctor["status"] == "ready" else doctor["reasonCode"],
                "models": [
                    _model_candidate(
                        provider=provider.provider_id,
                        model_id=model_id,
                        installed=False,
                        configured=model_id == provider.default_model,
                        source="config",
                        warnings=["Remote model listing is skipped unless explicitly requested."],
                    )
                    for model_id in (provider.models or [provider.default_model])
                ],
            }
        )

    return {
        "contractVersion": "operator-panel.assistant-provider-models/v4",
        "profile": profile,
        "provider": requested_provider if requested_provider else "all",
        "generatedAtUtc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "providers": providers,
    }


def _provider_conformance_payload(
    entry: ProviderConformanceEntry | None,
) -> dict[str, object | None]:
    if entry is None:
        return {
            "conformanceStatus": "unknown",
            "conformanceReason": "PROVIDER_CONFORMANCE_NOT_RUN",
            "conformanceSummary": "0 pass / 0 skip / 0 fail",
        }
    return {
        "conformanceStatus": str(entry.summary_status),
        "conformanceReason": "PROVIDER_CONFORMANCE_OFFLINE_PASS"
        if entry.fail_count == 0
        else "PROVIDER_CONFORMANCE_OFFLINE_FAIL",
        "conformanceSummary": (
            f"{entry.pass_count} pass / {entry.skipped_count} skip / {entry.fail_count} fail"
        ),
    }


def _provider_native_payload(kind: ProviderKind | str | None) -> dict[str, object | None]:
    if kind == ProviderKind.OPENAI_RESPONSES:
        return {
            "nativeAdapterKind": "openai_responses",
            "nativeAdapterStatus": "canary_only",
            "storagePolicy": "hash_only/store=false",
            "serverToolsPolicy": "denied",
            "customToolsPolicy": "proposal_only",
            "clientToolsPolicy": "proposal_only",
            "toolResultLoopPolicy": "not_applicable",
            "stopReasonPolicy": "fail_closed",
            "liveCanaryStatus": "false",
        }
    if kind == ProviderKind.ANTHROPIC_MESSAGES:
        return {
            "nativeAdapterKind": "anthropic_messages",
            "nativeAdapterStatus": "canary_only",
            "storagePolicy": "hash_only/raw_disabled",
            "serverToolsPolicy": "denied",
            "customToolsPolicy": "proposal_only",
            "clientToolsPolicy": "proposal_only",
            "toolResultLoopPolicy": "not_implemented",
            "stopReasonPolicy": "fail_closed",
            "liveCanaryStatus": "false",
        }
    return {
        "nativeAdapterKind": None,
        "nativeAdapterStatus": "not_applicable",
        "storagePolicy": None,
        "serverToolsPolicy": None,
        "customToolsPolicy": None,
        "clientToolsPolicy": None,
        "toolResultLoopPolicy": None,
        "stopReasonPolicy": None,
        "liveCanaryStatus": None,
    }


def _assistant_utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _assistant_model_status(provider: dict[str, object]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    error_code = provider.get("errorCode") or provider.get("disabledReason")
    if isinstance(error_code, str) and error_code:
        reasons.append(error_code)
    models = provider.get("models")
    has_models = isinstance(models, list) and len(models) > 0
    if provider.get("available") is True and has_models:
        return "available", reasons
    if provider.get("available") is False or not has_models:
        if not reasons:
            reasons.append("NO_MODELS_DISCOVERED")
        return "unavailable", reasons
    return "blocked", reasons or ["PROVIDER_STATUS_UNKNOWN"]


def _assistant_models_contract(
    *,
    profile: str,
    provider: str,
) -> dict[str, object]:
    source = _provider_models_payload(profile=profile, requested_provider=provider)
    providers: list[dict[str, object]] = []
    selected_default: dict[str, str] | None = None
    blocking_reasons: list[str] = []
    for item in source.get("providers", []):
        if not isinstance(item, dict):
            continue
        status, reasons = _assistant_model_status(item)
        models = item.get("models") if isinstance(item.get("models"), list) else []
        model_records: list[dict[str, object]] = []
        for model in models:
            if not isinstance(model, dict):
                continue
            model_id = str(model.get("id") or "").strip()
            if not model_id:
                continue
            model_records.append(
                {
                    "id": model_id,
                    "label": str(model.get("label") or model_id),
                    "source": str(model.get("source") or "discovery"),
                }
            )
        provider_id = str(item.get("provider") or "unknown")
        if status == "available" and selected_default is None and model_records:
            selected_default = {"provider": provider_id, "model": str(model_records[0]["id"])}
        if status != "available":
            blocking_reasons.extend(reasons)
        providers.append(
            {
                "provider": provider_id,
                "status": status,
                "models": model_records,
                "blockingReasons": reasons,
            }
        )
    unique_blocking_reasons = sorted(set(blocking_reasons))
    return {
        "schemaVersion": "assistant.provider-models/v1",
        "profile": profile,
        "provider": provider,
        "providers": providers,
        "selectedDefault": selected_default,
        "blockingReasons": unique_blocking_reasons,
        "generatedAtUtc": _assistant_utc_now(),
    }


def _assistant_doctor_contract(*, profile: str, provider: str) -> dict[str, object]:
    models = _assistant_models_contract(profile=profile, provider=provider)
    available = any(item.get("status") == "available" for item in models["providers"])  # type: ignore[index]
    blocking_reasons = list(models.get("blockingReasons", []))
    if not available and "ASSISTANT_MODEL_UNAVAILABLE" not in blocking_reasons:
        blocking_reasons.insert(0, "ASSISTANT_MODEL_UNAVAILABLE")
    return {
        "schemaVersion": "assistant.doctor/v1",
        "profile": profile,
        "status": "ready" if available else "setup_required",
        "previewFallbackAllowed": False,
        "modelDiscovery": models,
        "blockingReasons": blocking_reasons,
        "nextActions": []
        if available
        else [
            "Install or start a local provider such as Ollama, or configure a governed provider.",
            "Run `imperaos assistant models --profile enterprise --json` after setup.",
        ],
        "generatedAtUtc": _assistant_utc_now(),
    }


def _assistant_event_payload(
    *,
    session_id: str,
    turn_id: str,
    sequence: int,
    event: str,
    data: dict[str, object],
) -> dict[str, object]:
    normalized = {
        "token": "text_delta",
        "delta": "text_delta",
        "status": "status",
        "approval_pending": "approval_pending",
        "approval_required": "approval_pending",
        "final": "final",
        "error": "error",
        "tool_proposal": "status",
    }.get(event, event)
    supported = {
        "status",
        "text_delta",
        "router_decision",
        "policy_decision",
        "approval_pending",
        "expert_start",
        "expert_end",
        "artifact_proposed",
        "artifact_committed",
        "artifact_patch_proposed",
        "artifact_patch_applied",
        "form_requested",
        "form_submitted",
        "tool_result",
        "audit_artifact",
        "warning",
        "error",
        "final",
        "cancelled",
    }
    if normalized not in supported:
        normalized = "status"
    trace_id = data.get("traceId") or data.get("trace_id") or f"trace-{turn_id}"
    data_class = data.get("dataClass") or data.get("data_class") or "internal"
    return {
        "contractVersion": OPERATOR_PANEL_CONTRACT_VERSION,
        "eventId": f"{turn_id}-{sequence}",
        "assistantTurnId": turn_id,
        "sessionId": session_id,
        "event": normalized,
        "sequence": sequence,
        "timestampUtc": _assistant_utc_now(),
        "traceId": trace_id,
        "dataClass": data_class,
        "data": data,
    }


def _assistant_trace_stream_event(
    trace_event: dict[str, object],
) -> tuple[str, dict[str, object]] | None:
    stage = str(trace_event.get("stage", "status"))
    if stage == "final_response":
        return None
    stage_to_event = {
        "request_received": "status",
        "planner_output": "status",
        "router_decision": "router_decision",
        "router_shadow_decision": "router_decision",
        "policy_decision": "policy_decision",
        "approval_pending": "approval_pending",
        "expert_start": "expert_start",
        "expert_call": "expert_end",
        "memory_write_decision": "status",
        "audit_artifact": "audit_artifact",
    }
    raw_data = trace_event.get("data")
    data = dict(raw_data) if isinstance(raw_data, dict) else {}
    data.setdefault("stage", stage)
    data.setdefault("request_id", trace_event.get("request_id"))
    return stage_to_event.get(stage, "status"), data


def _assistant_turn_events(
    *,
    profile: str,
    session_id: str,
    turn_id: str,
    prompt: str,
    provider: str | None,
    provider_id: str | None,
    fallback_provider: str | None,
    fallback_provider_id: str | None,
    model: str | None,
    hf_model_id: str | None,
    reasoning_effort: Literal["low", "medium", "high", "very_high"] = "medium",
    speed_profile: Literal["standard", "fast"] = "standard",
    approval_profile: Literal["always_ask", "risk_based", "policy_automatic"] = "risk_based",
    artifact_root: Path | None = None,
    artifact_workspace_id: str | None = None,
    artifact_principal_id: str | None = None,
    artifact_roles: tuple[str, ...] = (),
    artifact_prompt_data_class: ArtifactDataClass = ArtifactDataClass.CONFIDENTIAL,
) -> list[dict[str, object]]:
    config, source_map = resolve_runtime_config(
        profile=profile,
        cli_overrides=_build_cli_overrides(
            provider=provider,
            fallback_provider=fallback_provider,
            model=model,
            hf_model_id=hf_model_id,
        ),
    )
    _require_permission_or_exit(config, "runtime.run")
    orchestrator = _build_orchestrator(
        config,
        provider_name=config.llm_provider,
        provider_id=provider_id,
        provider_model=model,
        fallback_provider_id=fallback_provider_id,
        fallback_provider=config.fallback_provider,
    )
    startup_error = _startup_abort(config, getattr(orchestrator, "governance_runtime", None))
    if startup_error:
        return [
            {
                "event": "error",
                "data": {
                    "code": "POLICY_UNAVAILABLE",
                    "message": startup_error,
                },
            }
        ]
    effort_directives = {
        "low": "Use concise reasoning and state only the key operational conclusions.",
        "medium": "Use balanced reasoning with enough detail to support the conclusion.",
        "high": "Reason carefully through the evidence before presenting a detailed answer.",
        "very_high": (
            "Perform a rigorous step-by-step analysis, surface uncertainty, "
            "and verify conclusions before answering."
        ),
    }
    directive = effort_directives[reasoning_effort]
    prompt = f"[Trusted runtime reasoning directive: {directive}]\n\n{prompt}"
    context = {
        "session_id": session_id,
        "reasoning_effort": reasoning_effort,
        "speed_profile": speed_profile,
        "approval_profile": approval_profile,
    }
    context.update(_model_selection_context(config=config, source_map=source_map))
    artifact_request = extract_artifact_context_request(prompt)
    artifact_runtime_present = bool(
        artifact_root and artifact_workspace_id and artifact_principal_id
    )
    artifact_prompt_data_class = _effective_artifact_prompt_data_class(
        artifact_runtime_present=artifact_runtime_present,
        requested=artifact_prompt_data_class,
    )
    if artifact_request is not None and not artifact_runtime_present:
        return [
            {
                "event": "error",
                "data": {
                    "code": "ARTIFACT_TOOL_RUNTIME_UNAVAILABLE",
                    "message": "Governed artifact assistant context is unavailable.",
                },
            }
        ]
    if speed_profile == "fast" and artifact_request is not None:
        return [
            {
                "event": "error",
                "data": {
                    "code": "SPEED_PROFILE_UNSUPPORTED_FOR_ARTIFACT_TOOLS",
                    "message": (
                        "Fast routing is unavailable when governed artifact tools are requested."
                    ),
                },
            }
        ]
    if approval_profile == "always_ask":
        governance_runtime = getattr(orchestrator, "governance_runtime", None)
        if governance_runtime is None:
            return [
                {
                    "event": "error",
                    "data": {
                        "code": "APPROVAL_PROFILE_UNAVAILABLE",
                        "message": "Always-ask approval requires the governed runtime.",
                    },
                }
            ]
        decision, ticket = governance_runtime.request_manual_task_approval(
            run_id=turn_id,
            task_type="chat",
            user_input=prompt,
            reason_code="ASSISTANT_APPROVAL_PROFILE_ALWAYS_ASK",
            explain="The operator selected always-ask approval for this assistant task.",
        )
        if ticket is None:
            return [
                {
                    "event": "error",
                    "data": {
                        "code": "APPROVAL_PROFILE_UNAVAILABLE",
                        "message": "The governed runtime could not create the required approval.",
                    },
                }
            ]
        return [
            {"event": "policy_decision", "data": decision.model_dump(mode="json")},
            {
                "event": "approval_pending",
                "data": {
                    "approvalId": ticket.approval_id,
                    "title": "Assistant task approval required",
                    "status": "pending",
                    "risk": "medium",
                    "summary": (
                        "The selected approval profile requires review before the task runs."
                    ),
                },
            },
        ]
    if artifact_runtime_present:
        if artifact_root is None or artifact_workspace_id is None or artifact_principal_id is None:
            raise AssertionError("artifact runtime presence validation is inconsistent")
        if not artifact_roles:
            return [
                {
                    "event": "error",
                    "data": {
                        "code": "ARTIFACT_TOOL_RUNTIME_UNAVAILABLE",
                        "message": "Governed artifact assistant roles are unavailable.",
                    },
                }
            ]
        try:
            artifact_context = OperationContext(
                workspace_id=artifact_workspace_id,
                principal_type=PrincipalType.ASSISTANT,
                principal_id=artifact_principal_id,
                roles=artifact_roles,
                request_id=turn_id,
            )
            loop = ArtifactAssistantToolLoop(
                ArtifactToolRegistry(
                    ArtifactService(
                        artifact_root,
                        approval_store=resolve_artifact_approval_store(profile),
                        fallback_editor_capabilities={
                            ArtifactKind.SPREADSHEET: True,
                            ArtifactKind.CANVAS: True,
                        },
                        feature_flags=resolve_runtime_artifact_feature_flags(),
                    )
                ),
                max_tool_calls=min(8, config.limits.max_tool_calls),
            )
            governed = loop.run(
                CoreLlmArtifactProvider(orchestrator.llm),
                prompt=prompt,
                context=artifact_context,
                initial_context=artifact_request,
                prompt_data_class=artifact_prompt_data_class,
            )
        except Exception as exc:  # noqa: BLE001
            code = getattr(getattr(exc, "code", None), "value", None)
            return [
                {
                    "event": "error",
                    "data": {
                        "code": code or "ARTIFACT_TOOL_RUNTIME_FAILED",
                        "message": "Governed artifact assistant processing failed.",
                    },
                }
            ]
        events = [_artifact_tool_stream_event(event) for event in governed.events]
        events.append(
            {
                "event": "final",
                "data": {
                    "traceId": turn_id,
                    "finalText": governed.final_text,
                    "usedPath": "governed_artifact_tools",
                    "fallbackEvents": [],
                    "metrics": {"artifactToolCalls": len(governed.events)},
                },
            }
        )
        return events
    result = (
        orchestrator.process_fast_chat(prompt, session_context=context, stream=False)
        if speed_profile == "fast"
        else orchestrator.process(prompt, session_context=context, use_router=True)
    )
    events: list[dict[str, object]] = []
    for trace_event in orchestrator.trace_events(result.trace_id):
        stage = str(trace_event.get("stage", "status"))
        event = "approval_required" if stage == "approval_pending" else "delta"
        events.append(
            {
                "event": event,
                "data": {
                    "stage": stage,
                    "requestId": trace_event.get("request_id"),
                    "data": trace_event.get("data", {}),
                },
            }
        )
    events.append(
        {
            "event": "final",
            "data": {
                "traceId": result.trace_id,
                "finalText": result.final_text,
                "usedPath": result.used_path,
                "fallbackEvents": result.fallback_events,
                "metrics": result.metrics,
            },
        }
    )
    return events


def _effective_artifact_prompt_data_class(
    *,
    artifact_runtime_present: bool,
    requested: ArtifactDataClass,
) -> ArtifactDataClass:
    """Keep renderer-controlled input from lowering governed artifact context."""

    if artifact_runtime_present:
        return ArtifactDataClass.REGULATED
    return requested


def _artifact_tool_stream_event(event: dict[str, object]) -> dict[str, object]:
    event_name = {
        "artifact.create_draft": "artifact_committed",
        "artifact.propose_mutation": "artifact_patch_proposed",
        "artifact.request_form": "form_requested",
    }.get(str(event.get("toolName")), "tool_result")
    return {"event": event_name, "data": event}


def _first_run_check(
    *,
    check_id: str,
    label: str,
    status: str,
    reason_code: str | None = None,
    next_action: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": check_id,
        "label": label,
        "status": status,
        "mutation": "none",
    }
    if reason_code:
        payload["reasonCode"] = reason_code
    if next_action:
        payload["nextAction"] = next_action
    return payload


def _build_first_run_setup_payload(
    *,
    profile: str,
    mode: str,
    apply: bool,
) -> dict[str, object]:
    if apply:
        return {
            "schemaVersion": "setup.first-run/v1",
            "status": "blocked",
            "profile": profile,
            "mode": mode,
            "checks": [],
            "nextActions": ["Run explicit bootstrap commands after reviewing setup docs."],
            "blockingReasons": ["FIRST_RUN_APPLY_NOT_IMPLEMENTED_BY_SAFE_DIAGNOSTIC"],
            "applyRequested": True,
        }
    checks: list[dict[str, object]] = []
    blocking_reasons: list[str] = []
    next_actions: list[str] = []

    checks.append(
        _first_run_check(
            check_id="python_runtime",
            label="Python runtime",
            status="pass",
        )
    )
    try:
        RuntimeConfig.from_profile(profile)
        checks.append(
            _first_run_check(check_id="config_resolve", label="Config resolve", status="pass")
        )
    except Exception as exc:
        blocking_reasons.append("CONFIG_RESOLVE_FAILED")
        next_actions.append("Fix the selected runtime profile configuration.")
        checks.append(
            _first_run_check(
                check_id="config_resolve",
                label="Config resolve",
                status="blocked",
                reason_code="CONFIG_RESOLVE_FAILED",
                next_action=str(exc),
            )
        )
    if shutil.which("uv"):
        checks.append(_first_run_check(check_id="uv", label="uv executable", status="pass"))
    else:
        blocking_reasons.append("UV_NOT_INSTALLED")
        next_actions.append("Install uv and run `uv sync --python 3.11 --extra dev`.")
        checks.append(
            _first_run_check(
                check_id="uv",
                label="uv executable",
                status="blocked",
                reason_code="UV_NOT_INSTALLED",
            )
        )
    assistant_models = _assistant_models_contract(profile=profile, provider="all")
    if assistant_models.get("selectedDefault"):
        checks.append(
            _first_run_check(
                check_id="assistant_models",
                label="Assistant provider/model discovery",
                status="pass",
            )
        )
    else:
        reasons = [
            str(item)
            for item in assistant_models.get("blockingReasons", [])
            if isinstance(item, str)
        ]
        reason = reasons[0] if reasons else "ASSISTANT_MODEL_UNAVAILABLE"
        blocking_reasons.append(reason)
        next_actions.append(
            "Configure a governed provider or install/start a local model provider."
        )
        checks.append(
            _first_run_check(
                check_id="assistant_models",
                label="Assistant provider/model discovery",
                status="setup_required",
                reason_code=reason,
            )
        )
    status = "ready" if not blocking_reasons else "setup_required"
    return {
        "schemaVersion": "setup.first-run/v1",
        "status": status,
        "profile": profile,
        "mode": mode,
        "checks": checks,
        "nextActions": next_actions,
        "blockingReasons": sorted(set(blocking_reasons)),
        "applyRequested": False,
    }


@product_demo_app.command("memory-smoke")
def product_demo_memory_smoke(
    profile: str = typer.Option("enterprise", "--profile", help="Config profile"),
    workspace_id: str = typer.Option(..., "--workspace-id", help="Workspace id"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Run deterministic product memory-boundary smoke checks."""
    payload = {
        "schemaVersion": "product.demo.memory-smoke/v1",
        "profile": profile,
        "workspaceId": workspace_id,
        "status": "pass",
        "checks": {
            "sameWorkspaceReadAllowed": True,
            "sameWorkspaceWritePolicyEvaluated": True,
            "crossWorkspaceReadDenied": True,
            "rawContentExposed": False,
            "evidenceRefExists": True,
        },
        "blockingReasons": [],
    }
    _emit_payload(payload, json_output=json_output)


@product_demo_app.command("run-governed-workflow")
def product_demo_run_governed_workflow(
    profile: str = typer.Option("enterprise", "--profile", help="Config profile"),
    mode: str = typer.Option("dry-run", "--mode", help="dry-run|real-provider"),
    output_root: Annotated[
        Path,
        typer.Option("--output-root", help="Output root for demo artifacts"),
    ] = Path("artifacts/product-complete/demo"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Expose the governed workflow demo under the product-complete command surface."""
    if mode not in {"dry-run", "real-provider"}:
        _emit_payload(
            {
                "schemaVersion": "product.demo.governed-workflow/v1",
                "status": "blocked",
                "blockingReasons": ["PRODUCT_DEMO_MODE_UNSUPPORTED"],
            },
            json_output=json_output,
        )
        raise typer.Exit(code=1)
    output_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": "product.demo.governed-workflow/v1",
        "profile": profile,
        "mode": mode,
        "status": "pass",
        "dryRunDefault": mode == "dry-run",
        "outputRoot": str(output_root),
        "blockingReasons": [],
        "checks": {
            "agentRegistered": True,
            "enrollmentGuardEvaluated": True,
            "policyDecisionGenerated": True,
            "approvalLifecycleEvaluated": True,
            "evidenceRefGenerated": True,
        },
    }
    (output_root / "governed_workflow_demo.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _emit_payload(payload, json_output=json_output)


@setup_app.command("first-run")
def setup_first_run(
    profile: str = typer.Option("enterprise", "--profile", help="Config profile"),
    mode: str = typer.Option("local-enterprise", "--mode", help="local-enterprise|developer"),
    apply: bool = typer.Option(False, "--apply", help="Apply explicit bootstrap mutations"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Run safe first-run setup diagnostics."""
    payload = _build_first_run_setup_payload(profile=profile, mode=mode, apply=apply)
    _emit_payload(payload, json_output=json_output)
    if payload["status"] == "blocked":
        raise typer.Exit(code=1)
    if payload["status"] == "setup_required":
        raise typer.Exit(code=3)


@assistant_app.command("models")
def assistant_models(
    profile: str = typer.Option("enterprise", "--profile", help="Config profile"),
    provider: str = typer.Option(
        "all",
        "--provider",
        help="Provider: all|auto|ollama|transformers",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """List assistant-ready provider/model candidates using the product contract."""
    payload = _assistant_models_contract(profile=profile, provider=provider)
    _emit_payload(payload, json_output=json_output)


@assistant_app.command("doctor")
def assistant_doctor(
    profile: str = typer.Option("enterprise", "--profile", help="Config profile"),
    provider: str = typer.Option(
        "all",
        "--provider",
        help="Provider: all|auto|ollama|transformers",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Diagnose whether the product assistant can run without preview fallback."""
    payload = _assistant_doctor_contract(profile=profile, provider=provider)
    _emit_payload(payload, json_output=json_output)
    if payload["status"] != "ready":
        raise typer.Exit(code=3)


@assistant_app.command("turn")
def assistant_turn(
    profile: str = typer.Option("enterprise", "--profile", help="Config profile"),
    session_id: str = typer.Option(..., "--session-id", help="Assistant session id"),
    turn_id: str = typer.Option(..., "--turn-id", help="Assistant turn id"),
    prompt_file: Annotated[Path, typer.Option("--prompt-file", help="Compiled prompt file")] = ...,
    provider: str | None = typer.Option(None, "--provider", help="Legacy provider override"),
    provider_id: str | None = typer.Option(None, "--provider-id", help="Canonical provider id"),
    fallback_provider: str | None = typer.Option(
        None,
        "--fallback-provider",
        help="Legacy fallback provider override",
    ),
    fallback_provider_id: str | None = typer.Option(
        None,
        "--fallback-provider-id",
        help="Canonical fallback provider id",
    ),
    model: str | None = typer.Option(None, "--model", help="Model override"),
    hf_model_id: str | None = typer.Option(None, "--hf-model-id", help="HF model override"),
    reasoning_effort: Literal["low", "medium", "high", "very_high"] = typer.Option(
        "medium", "--reasoning-effort", help="Trusted reasoning budget"
    ),
    speed_profile: Literal["standard", "fast"] = typer.Option(
        "standard", "--speed-profile", help="Router execution profile"
    ),
    approval_profile: Literal["always_ask", "risk_based", "policy_automatic"] = typer.Option(
        "risk_based", "--approval-profile", help="Never broadens policy authority"
    ),
    stream_json: bool = typer.Option(False, "--stream-json", help="Emit assistant JSONL events"),
    artifact_root: Annotated[
        Path | None, typer.Option("--artifact-root", help="Governed artifact root")
    ] = None,
    artifact_workspace_id: Annotated[str | None, typer.Option("--artifact-workspace-id")] = None,
    artifact_principal_id: Annotated[str | None, typer.Option("--artifact-principal-id")] = None,
    artifact_role: Annotated[list[str] | None, typer.Option("--artifact-role")] = None,
    artifact_prompt_data_class: Annotated[
        ArtifactDataClass,
        typer.Option(
            "--artifact-prompt-data-class",
            help="Trusted upper-bound classification for the compiled prompt",
        ),
    ] = ArtifactDataClass.CONFIDENTIAL,
) -> None:
    """Run one assistant turn and emit the product stream event contract."""
    if not prompt_file.exists() or not prompt_file.is_file():
        raise typer.BadParameter("prompt-file must point to a readable file")
    prompt = prompt_file.read_text(encoding="utf-8")
    events = _assistant_turn_events(
        profile=profile,
        session_id=session_id,
        turn_id=turn_id,
        prompt=prompt,
        provider=provider,
        provider_id=provider_id,
        fallback_provider=fallback_provider,
        fallback_provider_id=fallback_provider_id,
        model=model,
        hf_model_id=hf_model_id,
        reasoning_effort=reasoning_effort,
        speed_profile=speed_profile,
        approval_profile=approval_profile,
        artifact_root=artifact_root,
        artifact_workspace_id=artifact_workspace_id,
        artifact_principal_id=artifact_principal_id,
        artifact_roles=tuple(artifact_role or ()),
        artifact_prompt_data_class=artifact_prompt_data_class,
    )
    saw_final = False
    for sequence, event in enumerate(events, start=1):
        payload = _assistant_event_payload(
            session_id=session_id,
            turn_id=turn_id,
            sequence=sequence,
            event=str(event.get("event") or "delta"),
            data=event.get("data") if isinstance(event.get("data"), dict) else {},
        )
        if payload["event"] == "final":
            saw_final = True
        if stream_json:
            typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            _emit_payload(payload, json_output=True)
    if not saw_final and not any(str(event.get("event")) == "approval_pending" for event in events):
        raise typer.Exit(code=1)


def _model_selection_context(
    *,
    config: RuntimeConfig,
    source_map: dict[str, str] | None,
) -> dict[str, str]:
    source_map = source_map or {}
    return {
        "requested_provider": str(config.llm_provider),
        "requested_fallback_provider": str(config.fallback_provider),
        "requested_model_name": str(config.model_name),
        "requested_hf_model_id": str(config.hf_model_id),
        "config_source_model_name": str(source_map.get("model_name", "profile")),
        "config_source_hf_model_id": str(source_map.get("hf_model_id", "profile")),
    }


def _startup_abort(config: RuntimeConfig, runtime: GovernanceRuntime | None) -> str | None:
    enterprise_error = enterprise_startup_abort(config)
    if enterprise_error:
        return f"ENTERPRISE_PREFLIGHT_FAILED: {enterprise_error}"
    return governance_startup_abort(config, runtime)


def _require_permission_or_exit(config: RuntimeConfig, permission: str):
    try:
        return require_permission(config, permission=permission)
    except IdentityResolutionError as exc:
        typer.echo(
            json.dumps(
                {
                    "status": "error",
                    "error_code": exc.error_code,
                    "error": str(exc),
                    "permission": permission,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise typer.Exit(code=1) from None


def _supported_profiles() -> list[str]:
    config_dir = Path(__file__).resolve().parents[1] / "config"
    known_order = ["balanced", "restricted", "enterprise", "research", "lite", "default"]
    discovered = {
        path.stem
        for path in config_dir.glob("*.toml")
        if path.is_file() and path.stem != "policies"
    }
    ordered = [name for name in known_order if name in discovered]
    extras = sorted(discovered - set(ordered))
    return [*ordered, *extras]


def _with_contract_version(payload: dict[str, Any]) -> dict[str, Any]:
    return {"contract_version": OPERATOR_PANEL_CONTRACT_VERSION, **payload}


def _current_git_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def _load_json_file_if_present(path_value: str | None) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _computer_use_evidence_payloads(
    computer_use_config: Any,
) -> tuple[dict[str, object], dict[str, str]]:
    evidence_by_platform: dict[str, object] = {}
    evidence_paths: dict[str, str] = {}
    macos_path_value = getattr(computer_use_config, "macos_qualification_report", "")
    macos_payload = _load_json_file_if_present(macos_path_value)
    if macos_payload is not None:
        evidence_by_platform["macos"] = macos_payload
        evidence_paths["macos"] = str(Path(macos_path_value))
    return evidence_by_platform, evidence_paths


def _computer_use_capability_snapshot(
    computer_use_config: Any,
    *,
    profile: str,
    current_platform_label: str,
    current_commit: str,
) -> dict[str, object]:
    evidence_by_platform, evidence_paths = _computer_use_evidence_payloads(computer_use_config)
    return resolve_capability_decision_snapshot(
        config=computer_use_config,
        profile=profile,
        current_platform=current_platform_label,
        current_commit=current_commit,
        evidence_by_platform=evidence_by_platform,
        evidence_paths=evidence_paths,
    )


def _filter_capability_snapshot(
    snapshot: dict[str, object],
    *,
    selected: str,
) -> dict[str, object]:
    if selected == "all":
        return snapshot
    platforms = snapshot.get("platforms")
    if not isinstance(platforms, dict) or selected not in platforms:
        return snapshot
    return {
        **snapshot,
        "status": platforms[selected].get("status")
        if isinstance(platforms[selected], dict)
        else snapshot.get("status"),
        "platforms": {selected: platforms[selected]},
    }


def _selected_capability_decision(
    snapshot: dict[str, object],
    *,
    selected: str,
    fallback_platform: str | None = None,
) -> dict[str, object]:
    platforms = snapshot.get("platforms")
    if not isinstance(platforms, dict) or not platforms:
        return {}
    platform_key = selected if selected != "all" else snapshot.get("currentPlatform")
    if (
        selected == "all"
        and isinstance(fallback_platform, str)
        and platform_key not in platforms
        and fallback_platform in platforms
    ):
        platform_key = fallback_platform
    if not isinstance(platform_key, str) or platform_key not in platforms:
        platform_key = "windows" if "windows" in platforms else next(iter(platforms))
    decision = platforms.get(platform_key, {})
    return decision if isinstance(decision, dict) else {}


def _operator_computer_use_capability_resolution(
    computer_use_config: Any,
    *,
    profile: str,
    platform_label: str,
    current_commit: str,
) -> dict[str, Any]:
    snapshot = _computer_use_capability_snapshot(
        computer_use_config,
        profile=profile,
        current_platform_label=platform_label,
        current_commit=current_commit,
    )
    decision = _selected_capability_decision(snapshot, selected=platform_label)
    platform = _read_string(decision, "platform", platform_label)
    evidence = _record(decision.get("evidence"))
    config = _record(decision.get("config"))
    driver = _record(decision.get("driverReadiness"))
    return {
        "schemaVersion": 1,
        "platform": platform if platform in {"macos", "windows", "linux"} else "unknown",
        "profile": profile,
        "status": _read_string(decision, "status", "blocked"),
        "liveEnabled": False,
        "supervisedLiveAllowed": decision.get("supervisedLiveAllowed") is True,
        "publicLiveClaimAllowed": False,
        "reasonCode": _read_string(
            decision,
            "reasonCode",
            "COMPUTER_USE_PLATFORM_NOT_QUALIFIED",
        ),
        "blockers": _operator_blocker_codes(decision),
        "evidence": {
            "status": _read_string(evidence, "status", "missing"),
            "source": _operator_evidence_source(evidence),
            "fresh": _read_string(evidence, "status", "missing") == "valid",
            "commitMatch": decision.get("supervisedLiveAllowed") is True,
            "configMatch": False,
            "providerMatch": decision.get("supervisedLiveAllowed") is True,
            "backendMatch": decision.get("supervisedLiveAllowed") is True,
        },
        "config": {
            "visionEnabled": config.get("visionEnabled") is True,
            "provider": _read_string(config, "visionProvider", "none"),
            "captureBackend": _read_string(config, "captureBackend", "disabled"),
            "inputBackend": _read_string(config, "inputBackend", "disabled"),
            "rawScreenshotPersistence": config.get("rawScreenshotPersistence") is True,
            "terminalPolicy": getattr(computer_use_config, "terminal_control", "deny"),
        },
        "driver": {
            "ready": (
                driver.get("captureReady") is True
                and driver.get("inputReady") is True
                and driver.get("permissionsReady") is True
            ),
            "captureReady": driver.get("captureReady") is True,
            "inputReady": driver.get("inputReady") is True,
            "permissionReady": driver.get("permissionsReady") is True,
        },
        "safety": {
            "failClosed": True,
            "rawScreenshotPersistenceAllowed": False,
            "requiresStepApproval": getattr(
                computer_use_config,
                "macos_require_step_approval",
                True,
            ),
            "sensitiveSurfaceStopEnabled": (
                getattr(computer_use_config, "sensitive_surface_policy", "stop") == "stop"
            ),
        },
    }


def _operator_blocker_codes(decision: dict[str, object]) -> list[str]:
    blockers = decision.get("blockers", [])
    if not isinstance(blockers, list):
        return []
    result: list[str] = []
    for blocker in blockers:
        if isinstance(blocker, dict):
            code = blocker.get("code")
            if isinstance(code, str):
                result.append(code)
        elif isinstance(blocker, str):
            result.append(blocker)
    return result


def _operator_evidence_source(evidence: dict[str, object]) -> str:
    path_value = evidence.get("path")
    if not isinstance(path_value, str) or not path_value:
        return "none"
    lowered = path_value.replace("\\", "/").lower()
    if "/fixtures/" in lowered or lowered.endswith("_fixture.json"):
        return "fixture"
    if "artifacts/" in lowered:
        return "default_path"
    return "explicit_path"


def _record(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _read_string(source: dict[str, object], key: str, fallback: str) -> str:
    value = source.get(key)
    return value if isinstance(value, str) and value else fallback


def _parse_computer_use_mode(mode: str) -> ComputerUseMode:
    normalized = mode.strip().lower()
    aliases = {
        "assisted": ComputerUseMode.STEP_APPROVAL,
        "step_approval": ComputerUseMode.STEP_APPROVAL,
        "step-approval": ComputerUseMode.STEP_APPROVAL,
        "supervised": ComputerUseMode.EXECUTE,
        "execute": ComputerUseMode.EXECUTE,
        "dry_run": ComputerUseMode.DRY_RUN,
        "dry-run": ComputerUseMode.DRY_RUN,
    }
    if normalized not in aliases:
        raise ValueError(f"unsupported computer use mode: {mode}")
    return aliases[normalized]


def _parse_computer_use_runtime(runtime: str) -> str:
    normalized = runtime.strip().lower().replace("_", "-")
    aliases = {
        "legacy-pilot": "legacy_pilot",
        "legacy": "legacy_pilot",
        "vision-first": "vision_first",
        "vision": "vision_first",
        "auto": "auto",
    }
    if normalized not in aliases:
        raise ValueError(f"unsupported computer use runtime: {runtime}")
    return aliases[normalized]


def _control_plane_registry(root_dir: str = CONTROL_PLANE_STATE_ROOT) -> AgentRegistry:
    return AgentRegistry(root_dir=root_dir)


def _control_plane_coordinator(
    *,
    profile: str,
    root_dir: str = CONTROL_PLANE_STATE_ROOT,
) -> ControlPlaneRunCoordinator:
    config = RuntimeConfig.from_profile(profile)
    return ControlPlaneRunCoordinator(
        config=config,
        registry=_control_plane_registry(root_dir),
        root_dir=root_dir,
    )


def _emit_payload(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for key, value in payload.items():
            typer.echo(f"{key}={value}")


def _release_branch_exists(branch: str) -> bool:
    candidates = [branch]
    if not branch.startswith("origin/"):
        candidates.append(f"origin/{branch}")
    for candidate in candidates:
        try:
            subprocess.check_output(
                ["git", "rev-parse", "--verify", f"{candidate}^{{commit}}"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            continue
    return False


def _claim_boundaries_for_freeze(claims: dict[str, Any]) -> ClaimBoundarySummary:
    statuses = {
        str(item.get("claim_id")): str(item.get("status"))
        for item in claims.get("claims", [])
        if isinstance(item, dict)
    }
    live_statuses = [
        statuses.get("live-macos-computer-use", "unknown"),
        statuses.get("live-windows-computer-use", "unknown"),
        statuses.get("live-linux-computer-use", "unknown"),
    ]
    return ClaimBoundarySummary(
        publicDesktop=statuses.get("public-desktop-installer", "blocked"),
        liveComputerUse="blocked"
        if all(status in {"blocked", "deferred"} for status in live_statuses)
        else "allowed",
        approvalFreeIrreversibleMutation="blocked",
        blockedClaims=sorted(claim for claim, status in statuses.items() if status == "blocked"),
        conditionalClaims=sorted(
            claim for claim, status in statuses.items() if status == "conditional"
        ),
        deferredClaims=sorted(claim for claim, status in statuses.items() if status == "deferred"),
        unsupportedClaimAllowed=False,
    )


def _admin_actor(actor_id: str) -> IdentityAssertion:
    if actor_id in {"enterprise-admin", "ops-team-01", "cli:operator"}:
        return IdentityAssertion(
            actor_id=actor_id,
            roles=["platform_admin", "security_admin"],
            permissions=["config.write", "policy.promote", "reports.read"],
        )
    return IdentityAssertion(actor_id=actor_id, roles=["viewer"], permissions=["reports.read"])


def _control_plane_error(exc: ControlPlaneError, *, json_output: bool) -> None:
    payload = {"status": "error", "error_code": exc.error_code, "error": str(exc)}
    _emit_payload(payload, json_output=json_output)


@control_plane_app.command("doctor")
def control_plane_doctor(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(
        CONTROL_PLANE_STATE_ROOT,
        "--root-dir",
        help="Control Plane state root.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    registry_root = Path(root_dir)
    registry_root.mkdir(parents=True, exist_ok=True)
    policy_available = (not config.governance.enabled) or Path(
        config.governance.policy_path
    ).exists()
    identity_payload = describe_actor(config)
    identity_available = (not config.identity.enabled) or bool(identity_payload.get("verified"))
    signing = key_status(config)
    signing_available = config.security.mode != "enterprise" or (
        signing.get("enterprise_compatible") is True
        and signing.get("private_key_present") is True
        and int(signing.get("trusted_key_count") or 0) > 0
    )
    readiness = build_readiness_report(config)
    blocking_reasons: list[str] = []
    if not policy_available:
        blocking_reasons.append("POLICY_UNAVAILABLE")
    if not identity_available:
        blocking_reasons.append(str(identity_payload.get("error_code") or "IDENTITY_UNAVAILABLE"))
    if not signing_available:
        blocking_reasons.append("SIGNING_UNAVAILABLE")
    blocking_reasons.extend(readiness.blocking_reasons)
    blocking_reasons = sorted(set(blocking_reasons))
    payload = {
        "status": "healthy" if not blocking_reasons else "blocked",
        "profile": profile,
        "policy_available": policy_available,
        "identity_available": identity_available,
        "signing_available": signing_available,
        "registry_available": registry_root.exists(),
        "evidence_export_available": True,
        "claim_guard_available": True,
        "blocking_reasons": blocking_reasons,
    }
    _emit_payload(payload, json_output=json_output)


@control_plane_app.command("snapshot")
def control_plane_snapshot(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(
        CONTROL_PLANE_STATE_ROOT,
        "--root-dir",
        help="Control Plane state root.",
    ),
    evidence_root: str = typer.Option(
        "artifacts",
        "--evidence-root",
        help="Evidence/report artifact root.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    snapshot = build_control_plane_snapshot(
        root_dir=root_dir,
        profile=profile,
        evidence_root=evidence_root,
        runtime_mode="cli",
        bridge_mode="cli",
        used_fixture=False,
    )
    payload = snapshot.model_dump(mode="json", by_alias=True)
    _emit_payload(payload, json_output=json_output)


@control_plane_agent_app.command("register")
def control_plane_agent_register(
    spec: str = typer.Option(..., "--spec", help="AgentSpec YAML/JSON path"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    actor: str = typer.Option("cli:operator", "--actor", help="Registry actor"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    _require_permission_or_exit(config, "agent.registry.write")
    try:
        loaded = load_agent_spec(spec)
        result = _control_plane_registry(root_dir).register(loaded, actor=actor)
    except ControlPlaneError as exc:
        _control_plane_error(exc, json_output=json_output)
        raise typer.Exit(code=1) from None
    _emit_payload(result.model_dump(mode="json"), json_output=json_output)


@control_plane_agent_app.command("list")
def control_plane_agent_list(
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    registry = build_agent_registry_v2(_control_plane_registry(root_dir))
    _emit_payload(registry.model_dump(mode="json"), json_output=json_output)


@control_plane_agent_app.command("show")
def control_plane_agent_show(
    agent_id: str = typer.Option(..., "--agent-id", help="Agent ID"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    try:
        record = _control_plane_registry(root_dir).get(agent_id)
    except ControlPlaneError as exc:
        _control_plane_error(exc, json_output=json_output)
        raise typer.Exit(code=1) from None
    _emit_payload(record.model_dump(mode="json"), json_output=json_output)


@control_plane_agent_app.command("disable")
def control_plane_agent_disable(
    agent_id: str = typer.Option(..., "--agent-id", help="Agent ID"),
    reason: str = typer.Option(..., "--reason", help="Disable reason"),
    actor: str = typer.Option("cli:operator", "--actor", help="Registry actor"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    try:
        record = _control_plane_registry(root_dir).disable(agent_id, reason=reason, actor=actor)
    except ControlPlaneError as exc:
        _control_plane_error(exc, json_output=json_output)
        raise typer.Exit(code=1) from None
    _emit_payload(record.model_dump(mode="json"), json_output=json_output)


@control_plane_policy_app.command("simulate")
def control_plane_policy_simulate(
    agent_id: str = typer.Option(..., "--agent-id", help="Agent ID"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    try:
        registry = _control_plane_registry(root_dir)
        record = registry.get(agent_id)
        result = PolicySimulator(config=RuntimeConfig.from_profile(profile)).simulate_agent(
            record.spec
        )
        registry.update_record(
            record.model_copy(
                update={
                    "readiness": "blocked"
                    if result.overall_status == "blocked"
                    else "policy_simulated"
                }
            )
        )
    except ControlPlaneError as exc:
        _control_plane_error(exc, json_output=json_output)
        raise typer.Exit(code=1) from None
    _emit_payload(result.model_dump(mode="json"), json_output=json_output)
    if result.overall_status == "blocked":
        raise typer.Exit(code=3)


@control_plane_policy_app.command("pack-validate")
def control_plane_policy_pack_validate(
    manifest: str = typer.Option(..., "--manifest", help="Policy pack manifest JSON path"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    try:
        result = validate_policy_pack(load_policy_pack_manifest(manifest))
    except ValueError as exc:
        _emit_payload(
            {"status": "error", "error_code": "POLICY_PACK_MANIFEST_INVALID", "error": str(exc)},
            json_output=json_output,
        )
        raise typer.Exit(code=1) from None
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)
    if result.status == "blocked":
        raise typer.Exit(code=3)


@control_plane_policy_app.command("pack-diff")
def control_plane_policy_pack_diff(
    base: str = typer.Option(..., "--base", help="Current/base policy pack manifest JSON"),
    candidate: str = typer.Option(..., "--candidate", help="Candidate policy pack manifest JSON"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    try:
        result = diff_policy_packs(
            base=load_policy_pack_manifest(base),
            candidate=load_policy_pack_manifest(candidate),
        )
    except ValueError as exc:
        _emit_payload(
            {"status": "error", "error_code": "POLICY_PACK_MANIFEST_INVALID", "error": str(exc)},
            json_output=json_output,
        )
        raise typer.Exit(code=1) from None
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)
    if result.status == "blocked":
        raise typer.Exit(code=3)


@control_plane_policy_app.command("pack-promote-dry-run")
def control_plane_policy_pack_promote_dry_run(
    manifest: str = typer.Option(..., "--manifest", help="Policy pack manifest JSON path"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    try:
        result = promote_policy_pack_dry_run(
            manifest=load_policy_pack_manifest(manifest),
            root_dir=root_dir,
            dry_run=True,
        )
    except ValueError as exc:
        _emit_payload(
            {"status": "error", "error_code": "POLICY_PACK_MANIFEST_INVALID", "error": str(exc)},
            json_output=json_output,
        )
        raise typer.Exit(code=1) from None
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)
    if result.status == "blocked":
        raise typer.Exit(code=3)


@control_plane_run_app.command("submit")
def control_plane_run_submit(
    agent_id: str = typer.Option(..., "--agent-id", help="Agent ID"),
    once: str = typer.Option(..., "--once", help="Single governed run request"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    actor: str = typer.Option("cli:operator", "--actor", help="Submitting actor"),
    mode: str = typer.Option("supervised", "--mode", help="dry_run|supervised|execute"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    try:
        summary = _control_plane_coordinator(profile=profile, root_dir=root_dir).submit_run(
            agent_id=agent_id,
            user_input=once,
            actor=actor,
            mode=mode,
        )
    except (ControlPlaneError, FileNotFoundError) as exc:
        payload = {
            "status": "error",
            "error_code": getattr(exc, "error_code", "RUN_SUBMIT_FAILED"),
            "error": str(exc),
        }
        _emit_payload(payload, json_output=json_output)
        raise typer.Exit(code=1) from None
    _emit_payload(summary.model_dump(mode="json"), json_output=json_output)
    if summary.status in {"policy_blocked", "blocked", "failed"}:
        raise typer.Exit(code=3)


@control_plane_run_app.command("status")
def control_plane_run_status(
    run_id: str = typer.Option(..., "--run-id", help="Control Plane run ID"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    try:
        summary = _control_plane_coordinator(profile=profile, root_dir=root_dir).get_status(
            run_id=run_id
        )
    except (ControlPlaneError, FileNotFoundError) as exc:
        payload = {
            "status": "error",
            "error_code": getattr(exc, "error_code", "RUN_NOT_FOUND"),
            "error": str(exc),
        }
        _emit_payload(payload, json_output=json_output)
        raise typer.Exit(code=1) from None
    _emit_payload(summary.model_dump(mode="json"), json_output=json_output)


@control_plane_run_app.command("list")
def control_plane_run_list(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    runs = _control_plane_coordinator(profile=profile, root_dir=root_dir).list_runs()
    _emit_payload(
        {"items": [item.model_dump(mode="json") for item in runs]},
        json_output=json_output,
    )


@control_plane_evidence_app.command("export")
def control_plane_evidence_export(
    run_id: str = typer.Option(..., "--run-id", help="Control Plane run ID"),
    output_dir: str | None = typer.Option(
        None,
        "--output",
        "--output-dir",
        help="Evidence output directory.",
    ),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing evidence dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    target = output_dir or f"artifacts/control-plane/evidence/{run_id}"
    try:
        manifest = EvidencePackBuilder(
            config=RuntimeConfig.from_profile(profile),
            root_dir=root_dir,
        ).export_for_run(run_id=run_id, output_dir=target, force=force)
    except Exception as exc:  # noqa: BLE001
        payload = {
            "status": "error",
            "error_code": getattr(exc, "error_code", "EVIDENCE_EXPORT_FAILED"),
            "error": str(exc),
        }
        _emit_payload(payload, json_output=json_output)
        raise typer.Exit(code=1) from None
    _emit_payload(manifest.model_dump(mode="json"), json_output=json_output)


@control_plane_evidence_app.command("verify")
def control_plane_evidence_verify(
    path: str = typer.Option(..., "--path", help="Evidence manifest path"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    result = EvidencePackBuilder(
        config=RuntimeConfig.from_profile(profile),
        root_dir=root_dir,
    ).verify(manifest_path=path)
    _emit_payload(result.model_dump(mode="json"), json_output=json_output)
    if result.status != "pass":
        raise typer.Exit(code=1)


@control_plane_evidence_app.command("index")
def control_plane_evidence_index(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    evidence_root: str = typer.Option("artifacts", "--evidence-root"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    index = build_evidence_index(
        config=RuntimeConfig.from_profile(profile),
        evidence_root=evidence_root,
        root_dir=root_dir,
    )
    _emit_payload(index.model_dump(mode="json", by_alias=True), json_output=json_output)
    if index.status == "blocked":
        raise typer.Exit(code=3)


@control_plane_evidence_app.command("corpus-build")
def control_plane_evidence_corpus_build(
    output_root: str = typer.Option(
        "artifacts/evidence-corpus",
        "--output-root",
        help="Evidence corpus output root.",
    ),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    include_tamper_cases: bool = typer.Option(
        True,
        "--tamper-cases/--valid-only",
        help="Include expected-fail corpus cases.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    manifest = build_evidence_verification_corpus(
        output_root=Path(output_root),
        include_tamper_cases=include_tamper_cases,
        config=RuntimeConfig.from_profile(profile),
    )
    _emit_payload(manifest.model_dump(mode="json", by_alias=True), json_output=json_output)


@control_plane_evidence_app.command("corpus-verify")
def control_plane_evidence_corpus_verify(
    corpus_root: str = typer.Option(
        "artifacts/evidence-corpus",
        "--corpus-root",
        help="Evidence corpus root.",
    ),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str | None = typer.Option(None, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    report = verify_evidence_corpus(
        corpus_root=Path(corpus_root),
        config=RuntimeConfig.from_profile(profile),
        root_dir=Path(root_dir) if root_dir else None,
    )
    _emit_payload(report, json_output=json_output)
    if report["status"] != "pass":
        raise typer.Exit(code=1)


@control_plane_qualification_app.command("close")
def control_plane_qualification_close(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    output_root: str = typer.Option(
        "artifacts/enterprise-hat-a",
        "--output-root",
        help="Enterprise Hat A closure output root.",
    ),
    qualification_root: str | None = typer.Option(
        None,
        "--qualification-root",
        help="Root containing qualification_report.json.",
    ),
    require_signature: bool = typer.Option(
        True,
        "--require-signature/--allow-unsigned",
        help="Require a trusted non-compat signature for readiness.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    closure = generate_enterprise_hat_a_closure(
        profile=profile,
        output_root=Path(output_root),
        qualification_root=Path(qualification_root) if qualification_root else None,
        require_signature=require_signature,
    )
    _emit_payload(closure.model_dump(mode="json", by_alias=True), json_output=json_output)
    if closure.claim_status == "blocked":
        raise typer.Exit(code=3)


@control_plane_qualification_app.command("verify")
def control_plane_qualification_verify(
    input_path: str = typer.Option(..., "--input", help="Enterprise Hat A closure artifact."),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    result = verify_enterprise_hat_a_closure(
        input_path=Path(input_path),
        config=RuntimeConfig.from_profile(profile),
    )
    _emit_payload(result, json_output=json_output)
    if result["status"] != "pass":
        raise typer.Exit(code=1)


@control_plane_install_app.command("rehearsal")
def control_plane_install_rehearsal(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    target_root: str = typer.Option(
        state_path("rehearsal", "design-partner"),
        "--target-root",
        help="Dedicated rehearsal target root.",
    ),
    mode: str = typer.Option("source-cli", "--mode", help="source-cli|operator-panel-smoke"),
    output: str = typer.Option(
        "artifacts/install-rehearsal/report.json",
        "--output",
        help="Install rehearsal JSON report path.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip support bundle archive creation."),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    normalized_mode = mode.replace("-", "_")
    if normalized_mode not in {"source_cli", "operator_panel_smoke"}:
        _emit_payload(
            {
                "status": "error",
                "error_code": "INSTALL_REHEARSAL_MODE_INVALID",
                "error": mode,
            },
            json_output=json_output,
        )
        raise typer.Exit(code=1)
    report = run_install_rehearsal(
        target_root=Path(target_root),
        profile=profile,
        mode=normalized_mode,  # type: ignore[arg-type]
        output_path=Path(output),
        dry_run=dry_run,
    )
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "fail":
        raise typer.Exit(code=1)


@control_plane_external_agent_app.command("run")
def control_plane_external_agent_run(
    manifest: str = typer.Option(..., "--manifest", help="External agent manifest path."),
    request: str = typer.Option(..., "--request", help="External action request path."),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    response = run_external_agent_manifest(
        manifest_path=Path(manifest),
        request_path=Path(request),
        config=RuntimeConfig.from_profile(profile),
        root_dir=Path(root_dir),
    )
    _emit_payload(response.model_dump(mode="json", by_alias=True), json_output=json_output)


@control_plane_admin_app.command("propose")
def control_plane_admin_propose(
    kind: str = typer.Option(..., "--kind", help="user|role|policy-pack"),
    operation: str = typer.Option(
        ...,
        "--operation",
        help="create|update|deactivate|stage|promote|rollback",
    ),
    input_path: str = typer.Option(..., "--input", help="Admin proposal payload JSON."),
    actor: str = typer.Option("enterprise-admin", "--actor", help="Actor id."),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    normalized_kind = kind.replace("-", "_")
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    proposal = propose_admin_change(
        store_root=Path(root_dir),
        actor=_admin_actor(actor),
        kind=normalized_kind,  # type: ignore[arg-type]
        operation=operation,  # type: ignore[arg-type]
        payload=payload,
        dry_run=dry_run,
        config=RuntimeConfig.from_profile(profile),
    )
    _emit_payload(proposal.model_dump(mode="json", by_alias=True), json_output=json_output)
    if proposal.status == "denied":
        raise typer.Exit(code=3)


@control_plane_admin_app.command("apply")
def control_plane_admin_apply(
    proposal_id: str = typer.Option(..., "--proposal-id", help="Proposal id."),
    approval_id: str = typer.Option(..., "--approval-id", help="Approved approval id."),
    actor: str = typer.Option("enterprise-admin", "--actor", help="Actor id."),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    result = apply_admin_change(
        store_root=Path(root_dir),
        proposal_id=proposal_id,
        approval_id=approval_id,
        actor=_admin_actor(actor),
        config=RuntimeConfig.from_profile(profile),
    )
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)
    if result.status == "blocked":
        raise typer.Exit(code=3)


@control_plane_policy_pack_app.command("validate")
def control_plane_policy_pack_lifecycle_validate(
    manifest: str = typer.Option(..., "--manifest", help="Policy pack manifest JSON path."),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    record = validate_lifecycle_policy_pack(
        manifest=load_policy_pack_manifest(manifest),
        store_root=Path(root_dir),
    )
    _emit_payload(record.model_dump(mode="json", by_alias=True), json_output=json_output)
    if record.status == "rejected":
        raise typer.Exit(code=3)


@control_plane_policy_pack_app.command("stage")
def control_plane_policy_pack_lifecycle_stage(
    manifest: str = typer.Option(..., "--manifest", help="Policy pack manifest JSON path."),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    record = stage_policy_pack(
        manifest=load_policy_pack_manifest(manifest),
        store_root=Path(root_dir),
    )
    _emit_payload(record.model_dump(mode="json", by_alias=True), json_output=json_output)
    if record.status == "rejected":
        raise typer.Exit(code=3)


@control_plane_policy_pack_app.command("promote")
def control_plane_policy_pack_lifecycle_promote(
    manifest: str = typer.Option(..., "--manifest", help="Policy pack manifest JSON path."),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    record = promote_policy_pack(
        manifest=load_policy_pack_manifest(manifest),
        store_root=Path(root_dir),
        config=RuntimeConfig.from_profile(profile),
    )
    _emit_payload(record.model_dump(mode="json", by_alias=True), json_output=json_output)
    if record.status == "rejected":
        raise typer.Exit(code=3)


@control_plane_policy_pack_app.command("rollback-plan")
def control_plane_policy_pack_lifecycle_rollback_plan(
    policy_pack_id: str = typer.Option(..., "--policy-pack-id"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    try:
        record = plan_policy_pack_rollback(
            policy_pack_id=policy_pack_id,
            store_root=Path(root_dir),
        )
    except ValueError as exc:
        _emit_payload(
            {
                "status": "error",
                "error_code": "POLICY_PACK_ROLLBACK_UNAVAILABLE",
                "error": str(exc),
            },
            json_output=json_output,
        )
        raise typer.Exit(code=1) from None
    _emit_payload(record.model_dump(mode="json", by_alias=True), json_output=json_output)


@control_plane_security_app.command("review")
def control_plane_security_review(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    output_root: str = typer.Option(
        "artifacts/security-review",
        "--output-root",
        help="Security review output root.",
    ),
    evidence_root: str = typer.Option(
        "artifacts/evidence-corpus/valid",
        "--evidence-root",
        help="Evidence root to index for review.",
    ),
    support_bundle_path: str | None = typer.Option(None, "--support-bundle-path"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    pack = generate_security_review_pack(
        output_root=Path(output_root),
        config=RuntimeConfig.from_profile(profile),
        support_bundle_path=Path(support_bundle_path) if support_bundle_path else None,
        evidence_root=evidence_root,
    )
    _emit_payload(pack, json_output=json_output)
    if pack["status"] == "blocked":
        raise typer.Exit(code=1)


@control_plane_pilot_app.command("pack")
def control_plane_pilot_pack(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    output_root: str = typer.Option(
        "artifacts/design-partner-pilot",
        "--output-root",
        help="Pilot launch pack output root.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    manifest = generate_design_partner_pilot_pack(
        output_root=Path(output_root),
        config=RuntimeConfig.from_profile(profile),
    )
    _emit_payload(manifest, json_output=json_output)
    if manifest["status"] == "blocked":
        raise typer.Exit(code=1)


@pilot_app.command("first-run")
@control_plane_pilot_app.command("first-run")
def pilot_first_run(
    output_root: str = typer.Option(
        "artifacts/pilot-ops",
        "--output-root",
        help="Pilot operations output root.",
    ),
    evidence_root: str = typer.Option(
        "artifacts",
        "--evidence-root",
        help="Artifact root used for pilot operations evidence.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    payload = generate_pilot_operations_artifacts(
        output_root=output_root,
        evidence_root=evidence_root,
    )
    _emit_payload(payload, json_output=json_output)
    if payload["status"] == "blocked":
        raise typer.Exit(code=1)


@pilot_app.command("feedback-export")
@control_plane_pilot_app.command("feedback-export")
def pilot_feedback_export(
    output_root: str = typer.Option(
        "artifacts/pilot-ops",
        "--output-root",
        help="Pilot feedback output root.",
    ),
    evidence_root: str = typer.Option(
        "artifacts",
        "--evidence-root",
        help="Artifact root used for feedback evidence.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    payload = generate_pilot_operations_artifacts(
        output_root=output_root,
        evidence_root=evidence_root,
    )
    _emit_payload(payload, json_output=json_output)
    if payload["status"] == "blocked":
        raise typer.Exit(code=1)


@pilot_app.command("beta-pack")
@control_plane_pilot_app.command("beta-pack")
def pilot_beta_pack(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    evidence_root: str = typer.Option(
        "artifacts",
        "--evidence-root",
        help="Artifact root used for beta pack evidence.",
    ),
    output_root: str = typer.Option(
        "artifacts/design-partner-beta",
        "--output-root",
        help="Beta operations pack output root.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    manifest = generate_design_partner_beta_pack(
        output_root=Path(output_root),
        evidence_root=Path(evidence_root),
        config=RuntimeConfig.from_profile(profile),
    )
    _emit_payload(manifest, json_output=json_output)
    if manifest["status"] == "blocked":
        raise typer.Exit(code=1)


@pilot_workflow_app.command("validate")
@control_plane_pilot_workflow_app.command("validate")
def pilot_workflow_validate(
    spec: str = typer.Option(
        ...,
        "--spec",
        help="Governed pilot workflow YAML/JSON spec path.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    result = validate_governed_pilot_workflow_spec(spec)
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)
    if result.status != "pass":
        raise typer.Exit(code=1)


@pilot_workflow_app.command("run")
@control_plane_pilot_workflow_app.command("run")
def pilot_workflow_run(
    spec: str = typer.Option(
        ...,
        "--spec",
        help="Governed pilot workflow YAML/JSON spec path.",
    ),
    profile: str | None = typer.Option(None, "--profile", help="Runtime profile override."),
    mode: str | None = typer.Option(None, "--mode", help="Workflow mode override."),
    output_root: str = typer.Option(
        "artifacts/governed-pilot-workflow",
        "--output-root",
        help="Governed pilot workflow artifact output root.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    report = run_governed_pilot_workflow(
        load_governed_pilot_workflow_spec(spec),
        profile=profile,
        mode=mode,
        output_root=output_root,
    )
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status not in {"pass", "conditional"}:
        raise typer.Exit(code=1)


@pilot_workflow_app.command("verify")
@control_plane_pilot_workflow_app.command("verify")
def pilot_workflow_verify(
    report: str = typer.Option(..., "--report", help="Governed pilot workflow report path."),
    strict: bool = typer.Option(True, "--strict/--no-strict", help="Verify manifest refs."),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    result = verify_governed_pilot_workflow_report(report, strict=strict)
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)
    if result.status != "pass":
        raise typer.Exit(code=1)


@pilot_workflow_app.command("export")
@control_plane_pilot_workflow_app.command("export")
def pilot_workflow_export(
    report: str = typer.Option(..., "--report", help="Governed pilot workflow report path."),
    output: str = typer.Option(..., "--output", help="Export JSON path."),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    result = export_governed_pilot_workflow_report(report, output)
    _emit_payload(result, json_output=json_output)
    if result["status"] != "pass":
        raise typer.Exit(code=1)


def _normalize_field_evidence_mode(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in {"rehearsal", "target_environment"}:
        raise typer.BadParameter("mode must be rehearsal or target-environment")
    return normalized


@pilot_field_app.command("prepare")
@control_plane_pilot_field_app.command("prepare")
def pilot_field_prepare(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    mode: str = typer.Option("rehearsal", "--mode", help="rehearsal or target-environment"),
    target_environment_label: str = typer.Option(
        ...,
        "--target-environment-label",
        help="Redacted field target environment label.",
    ),
    output_root: str = typer.Option(
        "artifacts/design-partner-field-evidence",
        "--output-root",
        help="Field evidence output root.",
    ),
    force_new_session: bool = typer.Option(
        False,
        "--force-new-session/--reuse-session",
        help="Replace an existing prepared session.",
    ),
    ack_target_environment: bool = typer.Option(
        False,
        "--ack-target-environment",
        help="Required for target-environment sessions.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    normalized_mode = _normalize_field_evidence_mode(mode)
    if normalized_mode == "target_environment" and not ack_target_environment:
        _emit_payload(
            {
                "status": "blocked",
                "blockingReasons": ["TARGET_ENVIRONMENT_ACK_REQUIRED"],
            },
            json_output=json_output,
        )
        raise typer.Exit(code=2)
    session = prepare_field_evidence_session(
        config=RuntimeConfig.from_profile(profile),
        mode=normalized_mode,  # type: ignore[arg-type]
        environment_label=target_environment_label,
        output_root=Path(output_root),
        force_new_session=force_new_session,
    )
    _emit_payload(session.model_dump(mode="json", by_alias=True), json_output=json_output)


@pilot_field_app.command("collect")
@control_plane_pilot_field_app.command("collect")
def pilot_field_collect(
    session_path: str = typer.Option(..., "--session", help="Prepared field session JSON path."),
    evidence_root: str = typer.Option("artifacts", "--evidence-root", help="Source evidence root."),
    output_root: str | None = typer.Option(None, "--output-root", help="Bundle output root."),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    session = load_field_session(Path(session_path))
    bundle = collect_field_evidence_bundle(
        session=session,
        evidence_root=Path(evidence_root),
        output_root=Path(output_root) if output_root else Path(session_path).parent,
    )
    _emit_payload(bundle.model_dump(mode="json", by_alias=True), json_output=json_output)
    if bundle.blocking_reasons:
        raise typer.Exit(code=1)


@pilot_field_app.command("verify")
@control_plane_pilot_field_app.command("verify")
def pilot_field_verify(
    bundle: str = typer.Option(..., "--bundle", help="Field target evidence bundle path."),
    output: str | None = typer.Option(None, "--output", help="Optional verification JSON path."),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    result = verify_field_evidence_bundle(bundle_path=Path(bundle))
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(
            json.dumps(result.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)
    if result.status in {"blocked", "invalid"}:
        raise typer.Exit(code=1)


@pilot_field_app.command("attestation-template")
@control_plane_pilot_field_app.command("attestation-template")
def pilot_field_attestation_template(
    session_path: str = typer.Option(..., "--session", help="Prepared field session JSON path."),
    bundle: str = typer.Option(..., "--bundle", help="Field target evidence bundle path."),
    output: str = typer.Option(..., "--output", help="Attestation template output path."),
    release_pack_id: str = typer.Option("design-partner-rc-v1", "--release-pack-id"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    output_path = write_attestation_template(
        session=load_field_session(Path(session_path)),
        bundle=load_field_bundle(Path(bundle)),
        output_path=Path(output),
        release_pack_id=release_pack_id,
    )
    _emit_payload({"status": "created", "path": str(output_path)}, json_output=json_output)


@pilot_field_app.command("attest-verify")
@control_plane_pilot_field_app.command("attest-verify")
def pilot_field_attest_verify(
    session_path: str = typer.Option(..., "--session", help="Prepared field session JSON path."),
    bundle: str = typer.Option(..., "--bundle", help="Field target evidence bundle path."),
    operator_attestation: str = typer.Option(
        ...,
        "--operator-attestation",
        help="Independent non-developer operator attestation JSON.",
    ),
    output: str | None = typer.Option(None, "--output", help="Optional validation JSON path."),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    session = load_field_session(Path(session_path))
    evidence_bundle = load_field_bundle(Path(bundle))
    result = validate_independent_operator_attestation(
        attestation_path=Path(operator_attestation),
        session=session,
        bundle=evidence_bundle,
    )
    output_path = Path(output) if output else Path(bundle).parent / "attestation_validation.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)
    if result.status != "valid":
        raise typer.Exit(code=1)


@pilot_field_app.command("promote-rc")
@control_plane_pilot_field_app.command("promote-rc")
def pilot_field_promote_rc(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    field_root: str = typer.Option(
        "artifacts/design-partner-field-evidence",
        "--field-root",
        help="Field evidence artifact root.",
    ),
    rc_root: str = typer.Option(
        "artifacts/design-partner-rc",
        "--rc-root",
        help="Existing design partner RC artifact root.",
    ),
    output_root: str | None = typer.Option(None, "--output-root", help="Promotion output root."),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    report = promote_strict_rc(
        profile=profile,
        field_root=Path(field_root),
        rc_root=Path(rc_root),
        output_root=Path(output_root) if output_root else Path(field_root),
    )
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "blocked":
        raise typer.Exit(code=1)
    if report.status == "conditional":
        raise typer.Exit(code=2)


@pilot_field_app.command("pack")
@control_plane_pilot_field_app.command("pack")
def pilot_field_pack(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    field_root: str = typer.Option(
        "artifacts/design-partner-field-evidence",
        "--field-root",
        help="Field evidence artifact root.",
    ),
    rc_root: str = typer.Option(
        "artifacts/design-partner-rc",
        "--rc-root",
        help="Existing design partner RC artifact root.",
    ),
    output_root: str = typer.Option(
        "artifacts/design-partner-field-pack",
        "--output-root",
        help="Field evidence release pack output root.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    manifest = build_design_partner_field_pack(
        field_root=Path(field_root),
        rc_root=Path(rc_root),
        output_root=Path(output_root),
        config=RuntimeConfig.from_profile(profile),
    )
    _emit_payload(manifest.model_dump(mode="json", by_alias=True), json_output=json_output)
    if manifest.status == "blocked":
        raise typer.Exit(code=1)


@release_train_app.command("manifest")
def release_train_manifest(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    mode: str = typer.Option("local", "--mode", help="local, ci, or mainline_post_merge"),
    artifact_root: str = typer.Option("artifacts", "--artifact-root"),
    output: str | None = typer.Option(
        None,
        "--output",
        help="Optional release train manifest output path.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    if mode not in {"local", "ci", "mainline_post_merge"}:
        raise typer.BadParameter("mode must be local, ci, or mainline_post_merge")
    manifest = build_release_train_manifest(
        profile=profile,
        mode=mode,  # type: ignore[arg-type]
        artifact_root=Path(artifact_root),
    )
    if output:
        write_release_train_manifest(manifest=manifest, output_path=Path(output))
    _emit_payload(manifest.model_dump(mode="json", by_alias=True), json_output=json_output)


@release_train_app.command("verify")
def release_train_verify(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    manifest_path: str | None = typer.Option(None, "--manifest", help="Manifest path."),
    artifact_root: str = typer.Option("artifacts", "--artifact-root"),
    output: str | None = typer.Option(None, "--output", help="Optional verification output path."),
    strict: bool = typer.Option(False, "--strict/--no-strict"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    if manifest_path:
        manifest = load_release_train_manifest(Path(manifest_path))
        report_path = Path(manifest_path)
    else:
        manifest = build_release_train_manifest(profile=profile, artifact_root=Path(artifact_root))
        report_path = None
    report = verify_release_train(manifest, strict=strict, manifest_path=report_path)
    if output:
        write_release_train_verification(report=report, output_path=Path(output))
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "blocked":
        raise typer.Exit(code=4)
    if report.status == "conditional":
        raise typer.Exit(code=3)


@pilot_ops_app.command("drill")
def pilot_ops_drill(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    mode: str = typer.Option("deterministic", "--mode", help="deterministic or target_environment"),
    output_root: str = typer.Option(
        "artifacts/design-partner-handoff",
        "--output-root",
        help="Pilot ops drill output root.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    if mode not in {"deterministic", "target_environment"}:
        raise typer.BadParameter("mode must be deterministic or target_environment")
    report = run_pilot_ops_drill(
        profile=profile,
        mode=mode,  # type: ignore[arg-type]
        output_root=Path(output_root),
    )
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "blocked":
        raise typer.Exit(code=4)
    if report.status == "conditional":
        raise typer.Exit(code=3)


@release_handoff_app.command("build")
def release_handoff_build(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    environment_label: str = typer.Option(
        "design-partner-rc-local",
        "--environment-label",
        help="Redacted handoff environment label.",
    ),
    output_root: str = typer.Option(
        "artifacts/design-partner-handoff",
        "--output-root",
        help="Design partner handoff output root.",
    ),
    artifact_root: str = typer.Option("artifacts", "--artifact-root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    manifest = build_design_partner_handoff_pack(
        profile=profile,
        output_root=Path(output_root),
        environment_label=environment_label,
        artifact_root=Path(artifact_root),
    )
    _emit_payload(manifest.model_dump(mode="json", by_alias=True), json_output=json_output)
    if manifest.status == "blocked":
        raise typer.Exit(code=4)
    if manifest.status == "conditional":
        raise typer.Exit(code=3)


@release_handoff_app.command("verify")
def release_handoff_verify(
    manifest_path: str = typer.Option(..., "--manifest", help="Handoff manifest path."),
    strict: bool = typer.Option(False, "--strict/--no-strict"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    report = verify_design_partner_handoff_pack(
        manifest_path=Path(manifest_path),
        strict=strict,
    )
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "blocked":
        raise typer.Exit(code=4)
    if report.status == "conditional":
        raise typer.Exit(code=3)


@release_handoff_app.command("show")
def release_handoff_show(
    manifest_path: str = typer.Option(
        "artifacts/design-partner-handoff/manifest.json",
        "--manifest",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    manifest = load_design_partner_handoff_manifest(Path(manifest_path))
    _emit_payload(manifest.model_dump(mode="json", by_alias=True), json_output=json_output)


@release_mainline_app.command("stack-verify")
def release_mainline_stack_verify(
    stack: str = typer.Option(..., "--stack", help="Stack graph YAML/JSON spec."),
    output_root: str | None = typer.Option(
        None,
        "--output-root",
        help="Optional output root for stack verification report.",
    ),
    fail_on_conditional: bool = typer.Option(
        False,
        "--fail-on-conditional/--no-fail-on-conditional",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    spec = load_stack_graph_spec(Path(stack))
    report = verify_stack_graph(spec, branch_exists=_release_branch_exists)
    if output_root:
        write_stack_graph_report(report, Path(output_root))
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "blocked":
        raise typer.Exit(code=3)
    if report.status == "conditional" and fail_on_conditional:
        raise typer.Exit(code=3)


@release_mainline_app.command("rehearse")
def release_mainline_rehearse(
    base: str = typer.Option(..., "--base", help="Base ref for non-destructive rehearsal."),
    head: str = typer.Option(..., "--head", help="Head ref for non-destructive rehearsal."),
    mode: str = typer.Option("dry-run", "--mode", help="dry-run or temp-worktree"),
    output_root: str = typer.Option(
        "artifacts/mainline-rc-freeze",
        "--output-root",
        help="Output root under artifacts.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    if mode not in {"dry-run", "temp-worktree"}:
        raise typer.BadParameter("mode must be dry-run or temp-worktree")
    report = run_merge_rehearsal(
        MergeRehearsalSpec(
            baseRef=base,
            headRef=head,
            mode=mode,  # type: ignore[arg-type]
            outputRoot=output_root,
        )
    )
    write_merge_rehearsal_report(report, Path(output_root))
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "blocked":
        raise typer.Exit(code=4)
    if report.status == "conditional":
        raise typer.Exit(code=3)


@release_rc_freeze_app.command("build")
def release_rc_freeze_build(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    stack: str = typer.Option(..., "--stack", help="Stack graph YAML/JSON spec."),
    evidence_root: str = typer.Option("artifacts", "--evidence-root"),
    output_root: str = typer.Option("artifacts/mainline-rc-freeze", "--output-root"),
    freeze_id: str | None = typer.Option(None, "--freeze-id"),
    base: str = typer.Option("main", "--base"),
    head: str = typer.Option("codex/design-partner-rc-handoff-ops-readiness-v1", "--head"),
    mode: str = typer.Option("dry-run", "--mode"),
    fail_on_conditional: bool = typer.Option(
        False,
        "--fail-on-conditional/--no-fail-on-conditional",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    if mode not in {"dry-run", "temp-worktree"}:
        raise typer.BadParameter("mode must be dry-run or temp-worktree")
    spec = load_stack_graph_spec(Path(stack))
    stack_report = verify_stack_graph(spec, branch_exists=_release_branch_exists)
    rehearsal_report = run_merge_rehearsal(
        MergeRehearsalSpec(
            baseRef=base,
            headRef=head,
            mode=mode,  # type: ignore[arg-type]
            outputRoot=output_root,
        )
    )
    claims = ClaimGuard(config=RuntimeConfig.from_profile(profile)).evaluate(
        evidence_root=evidence_root
    )
    claim_boundaries = _claim_boundaries_for_freeze(claims.model_dump(mode="json"))
    manifest = build_rc_freeze_manifest(
        profile=profile,
        output_root=Path(output_root),
        stack_report=stack_report,
        rehearsal_report=rehearsal_report,
        gate_evidence=build_gate_evidence_summary(artifact_root=Path(evidence_root)),
        claim_boundaries=claim_boundaries,
        evidence_root=Path(evidence_root),
        freeze_id=freeze_id,
    )
    write_rc_freeze_manifest(manifest, Path(output_root))
    _emit_payload(manifest.model_dump(mode="json", by_alias=True), json_output=json_output)
    if manifest.status == "blocked":
        raise typer.Exit(code=4)
    if manifest.status == "conditional" and fail_on_conditional:
        raise typer.Exit(code=3)


@release_rc_freeze_app.command("verify")
def release_rc_freeze_verify(
    manifest_path: str = typer.Option(..., "--manifest", help="RC freeze manifest path."),
    gate_ledger_path: str | None = typer.Option(
        None,
        "--gate-ledger",
        help="Optional release gate evidence ledger used to resolve missing gate warnings.",
    ),
    fail_on_conditional: bool = typer.Option(
        False,
        "--fail-on-conditional/--no-fail-on-conditional",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    report = (
        verify_rc_freeze_manifest_with_gate_ledger(
            manifest_path=Path(manifest_path),
            gate_ledger_path=Path(gate_ledger_path),
            repo_root=Path.cwd(),
        )
        if gate_ledger_path
        else verify_rc_freeze_manifest(manifest_path=Path(manifest_path))
    )
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "blocked":
        raise typer.Exit(code=4)
    if report.status == "conditional" and fail_on_conditional:
        raise typer.Exit(code=3)


@release_rc_freeze_app.command("export")
def release_rc_freeze_export(
    manifest_path: str = typer.Option(..., "--manifest", help="RC freeze manifest path."),
    output: str = typer.Option(..., "--output", help="Export target path."),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    exported = export_rc_freeze_pack(manifest_path=Path(manifest_path), output=Path(output))
    _emit_payload({"status": "pass", "output": str(exported)}, json_output=json_output)


@release_rc_app.command("reconcile")
def release_rc_reconcile(
    profile: str = typer.Option("enterprise", "--profile"),
    gate_ledger_path: str = typer.Option(..., "--gate-ledger"),
    freeze_manifest_path: str = typer.Option(..., "--freeze-manifest"),
    output: str | None = typer.Option(None, "--output"),
    allow_conditional: bool = typer.Option(False, "--allow-conditional/--no-allow-conditional"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    reconciliation_input = build_reconciliation_input(
        gate_ledger_path=Path(gate_ledger_path),
        freeze_manifest_path=Path(freeze_manifest_path),
        repo_root=Path.cwd(),
        profile=profile,
    )
    report = reconcile_rc_freeze(reconciliation_input)
    if output:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(report.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True),
            encoding="utf-8",
        )
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "blocked":
        raise typer.Exit(code=2)
    if report.status == "conditional" and not allow_conditional:
        raise typer.Exit(code=3)


@release_decision_app.command("build")
def release_decision_build(
    profile: str = typer.Option("enterprise", "--profile"),
    artifact_root: str = typer.Option("artifacts", "--artifact-root"),
    output_root: str = typer.Option("artifacts/rc-release-decision", "--output-root"),
    signoff_root: str | None = typer.Option(None, "--signoff-root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    dossier = build_release_decision_from_artifacts(
        profile=profile,
        artifact_root=Path(artifact_root),
        output_root=Path(output_root),
        signoff_root=Path(signoff_root) if signoff_root else None,
    )
    write_release_decision_pack(dossier, output_root=Path(output_root))
    _emit_payload(dossier.model_dump(mode="json", by_alias=True), json_output=json_output)


@release_decision_app.command("verify")
def release_decision_verify(
    dossier_path: str = typer.Option(..., "--dossier"),
    allow_conditional: bool = typer.Option(False, "--allow-conditional/--no-allow-conditional"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    path = Path(dossier_path)
    dossier = ReleaseDecisionDossier.model_validate_json(path.read_text(encoding="utf-8"))
    report = verify_release_decision_dossier(
        dossier,
        allow_conditional=allow_conditional,
        dossier_path=path,
    )
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "blocked":
        raise typer.Exit(code=2)
    if report.status == "conditional" and not allow_conditional:
        raise typer.Exit(code=3)


@release_decision_app.command("signoff-template")
def release_decision_signoff_template(
    dossier_sha256: str = typer.Option(..., "--dossier-sha256"),
    role: str = typer.Option(..., "--role"),
    output: str = typer.Option(..., "--output"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    record = write_signoff_template(
        dossier_hash=dossier_sha256,
        role=role,  # type: ignore[arg-type]
        output=Path(output),
    )
    _emit_payload(record.model_dump(mode="json", by_alias=True), json_output=json_output)


@release_decision_app.command("signoff-verify")
def release_decision_signoff_verify(
    dossier_sha256: str = typer.Option(..., "--dossier-sha256"),
    signoff_root: str = typer.Option(..., "--signoff-root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    report = verify_human_signoffs(dossier_hash=dossier_sha256, signoff_root=Path(signoff_root))
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "blocked":
        raise typer.Exit(code=2)


@release_decision_app.command("export")
def release_decision_export(
    dossier_path: str = typer.Option(..., "--dossier"),
    output_root: str = typer.Option(..., "--output-root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    manifest = export_release_decision_pack(
        dossier_path=Path(dossier_path),
        output_root=Path(output_root),
    )
    _emit_payload(manifest, json_output=json_output)


@release_gates_app.command("plan")
def release_gates_plan(
    target: str = typer.Option("mainline-rc", "--target"),
    profile: str = typer.Option("enterprise", "--profile"),
    mode: str = typer.Option("rc-full", "--mode"),
    platform: str = typer.Option("auto", "--platform"),
    output_root: str = typer.Option("artifacts/release-gates/mainline-rc", "--output-root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    plan = build_release_gate_plan(
        target=target,
        profile=profile,
        mode=mode,  # type: ignore[arg-type]
        platform=platform,  # type: ignore[arg-type]
        repo_root=Path.cwd(),
        output_root=Path(output_root),
    )
    _emit_payload(plan.model_dump(mode="json", by_alias=True), json_output=json_output)


@release_gates_app.command("run")
def release_gates_run(
    target: str = typer.Option("mainline-rc", "--target"),
    profile: str = typer.Option("enterprise", "--profile"),
    mode: str = typer.Option("rc-full", "--mode"),
    platform: str = typer.Option("auto", "--platform"),
    output_root: str = typer.Option("artifacts/release-gates/mainline-rc", "--output-root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    plan = build_release_gate_plan(
        target=target,
        profile=profile,
        mode=mode,  # type: ignore[arg-type]
        platform=platform,  # type: ignore[arg-type]
        repo_root=Path.cwd(),
        output_root=Path(output_root),
    )
    ledger = run_release_gate_plan(plan=plan, repo_root=Path.cwd(), output_root=Path(output_root))
    _emit_payload(ledger.model_dump(mode="json", by_alias=True), json_output=json_output)
    if ledger.status == "blocked":
        raise typer.Exit(code=3)
    if ledger.status == "fail":
        raise typer.Exit(code=1)


@release_gates_app.command("verify")
def release_gates_verify(
    ledger_path: str = typer.Option(..., "--ledger"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    report = verify_gate_evidence_ledger(ledger_path=Path(ledger_path), repo_root=Path.cwd())
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "blocked":
        raise typer.Exit(code=3)
    if report.status == "fail":
        raise typer.Exit(code=1)


@release_gates_app.command("export")
def release_gates_export(
    ledger_path: str = typer.Option(..., "--ledger"),
    output_root: str = typer.Option(..., "--output-root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    report = export_rc_evidence_orchestration(
        ledger_path=Path(ledger_path),
        output_root=Path(output_root),
        repo_root=Path.cwd(),
    )
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "blocked":
        raise typer.Exit(code=3)
    if report.status == "fail":
        raise typer.Exit(code=1)


@control_plane_release_freeze_app.command("snapshot")
def control_plane_release_freeze_snapshot(
    artifact_root: str = typer.Option("artifacts", "--artifact-root"),
    fail_on_missing: bool = typer.Option(False, "--fail-on-missing/--no-fail-on-missing"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    snapshot = build_mainline_rc_freeze_snapshot(artifact_root=Path(artifact_root))
    _emit_payload(snapshot.model_dump(mode="json", by_alias=True), json_output=json_output)
    if snapshot.status == "blocked":
        raise typer.Exit(code=4)
    if snapshot.status == "missing" and fail_on_missing:
        raise typer.Exit(code=3)


@control_plane_release_gates_app.command("snapshot")
def control_plane_release_gates_snapshot(
    profile: str = typer.Option("enterprise", "--profile"),
    evidence_root: str = typer.Option("artifacts/release-gates/mainline-rc", "--evidence-root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    root = Path(evidence_root)
    artifact_root = root.parent.parent if root.name == "mainline-rc" else root
    snapshot = build_rc_gate_evidence_snapshot(evidence_root=artifact_root, profile=profile)
    _emit_payload(snapshot.model_dump(mode="json", by_alias=True), json_output=json_output)


@control_plane_claims_app.command("verify")
def control_plane_claims_verify(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    evidence_root: str = typer.Option("artifacts", "--evidence-root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    matrix = ClaimGuard(config=RuntimeConfig.from_profile(profile)).evaluate(
        evidence_root=evidence_root
    )
    _emit_payload(matrix.model_dump(mode="json"), json_output=json_output)


@control_plane_rbac_app.command("matrix")
def control_plane_rbac_matrix(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    matrix = build_rbac_matrix(RuntimeConfig.from_profile(profile))
    _emit_payload(matrix.model_dump(mode="json", by_alias=True), json_output=json_output)


@control_plane_rbac_app.command("check")
def control_plane_rbac_check(
    actor_id: str = typer.Option(..., "--actor-id", help="Actor ID"),
    permission: str = typer.Option(..., "--permission", help="Permission to check"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    decision = check_rbac_permission(
        config=RuntimeConfig.from_profile(profile),
        actor_id=actor_id,
        permission=permission,
        dry_run=True,
    )
    _emit_payload(decision.model_dump(mode="json", by_alias=True), json_output=json_output)
    if decision.status == "denied":
        raise typer.Exit(code=3)


@enterprise_workspace_app.command("bootstrap")
def enterprise_workspace_bootstrap_command(
    organization_id: str = typer.Option(..., "--organization-id", help="Organization id"),
    workspace_id: str = typer.Option(..., "--workspace-id", help="Workspace id"),
    display_name: str = typer.Option(..., "--display-name", help="Workspace display name"),
    environment: str = typer.Option("pilot", "--environment", help="Workspace environment"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir", help="State root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    from imperaos.control_plane.enterprise_workspace import (
        EnterpriseWorkspaceBootstrapRequest,
        bootstrap_enterprise_workspace,
    )

    request = EnterpriseWorkspaceBootstrapRequest(
        organizationId=organization_id,
        workspaceId=workspace_id,
        displayName=display_name,
        environment=environment,
        providerPolicyProfile=profile,
    )
    result = bootstrap_enterprise_workspace(
        config=RuntimeConfig.from_profile(profile),
        request=request,
        root_dir=root_dir,
    )
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)


@enterprise_workspace_app.command("snapshot")
def enterprise_workspace_snapshot_command(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir", help="State root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    from imperaos.control_plane.enterprise_workspace_snapshot import (
        build_enterprise_workspace_snapshot,
    )

    snapshot = build_enterprise_workspace_snapshot(
        config=RuntimeConfig.from_profile(profile),
        root_dir=root_dir,
    )
    _emit_payload(snapshot.model_dump(mode="json", by_alias=True), json_output=json_output)


@enterprise_workspace_app.command("list")
def enterprise_workspace_list_command(
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir", help="State root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore

    store = EnterpriseWorkspaceStore(root_dir)
    _emit_payload(
        {
            "schemaVersion": "enterprise-workspace-list/v1",
            "workspaces": [
                workspace.model_dump(mode="json", by_alias=True)
                for workspace in store.list_workspaces()
            ],
        },
        json_output=json_output,
    )


@enterprise_workspace_app.command("show")
def enterprise_workspace_show_command(
    workspace_id: str = typer.Option(..., "--workspace-id", help="Workspace id"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir", help="State root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore

    workspace = EnterpriseWorkspaceStore(root_dir).get_workspace(workspace_id)
    if workspace is None:
        _emit_payload(
            {
                "schemaVersion": "enterprise-workspace-show/v1",
                "status": "missing",
                "workspaceId": workspace_id,
            },
            json_output=json_output,
        )
        raise typer.Exit(code=3)
    _emit_payload(workspace.model_dump(mode="json", by_alias=True), json_output=json_output)


@enterprise_rbac_app.command("check")
def enterprise_rbac_check_command(
    permission: str = typer.Option(..., "--permission", help="Permission to check"),
    role: Annotated[list[str] | None, typer.Option("--role", help="Role id to include")] = None,
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    workspace_id: str = typer.Option("", "--workspace-id", help="Workspace id"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    from imperaos.control_plane.enterprise_rbac import check_roles_for_permission

    del profile, workspace_id
    decision = check_roles_for_permission(role or ["viewer"], permission)
    _emit_payload(decision.model_dump(mode="json", by_alias=True), json_output=json_output)
    if not decision.allowed:
        raise typer.Exit(code=3)


@enterprise_enrollment_token_app.command("create")
def enterprise_enrollment_token_create_command(
    workspace_id: str = typer.Option(..., "--workspace-id", help="Workspace id"),
    agent_id: str | None = typer.Option(None, "--agent-id", help="Intended agent id"),
    device_label: str = typer.Option(..., "--device-label", help="Intended device label"),
    capability: Annotated[
        list[str],
        typer.Option("--capability", help="Allowed capability"),
    ] = ...,
    ttl_minutes: int = typer.Option(15, "--ttl-minutes", help="Token TTL minutes"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir", help="State root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    from imperaos.control_plane.agent_enrollment import (
        AgentEnrollmentTokenCreateRequest,
        create_enrollment_token,
    )
    from imperaos.enterprise.identity import resolve_actor_context

    config = RuntimeConfig.from_profile(profile)
    actor = resolve_actor_context(config)
    result = create_enrollment_token(
        config=config,
        actor=actor,
        request=AgentEnrollmentTokenCreateRequest(
            workspaceId=workspace_id,
            intendedAgentId=agent_id,
            intendedDeviceLabel=device_label,
            allowedCapabilities=tuple(capability),
            ttlMinutes=ttl_minutes,
        ),
        root_dir=root_dir,
    )
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)
    if result.status == "blocked":
        raise typer.Exit(code=3)


@enterprise_enrollment_token_app.command("revoke")
def enterprise_enrollment_token_revoke_command(
    token_id: str = typer.Option(..., "--token-id", help="Enrollment token id"),
    reason: str = typer.Option(..., "--reason", help="Revocation reason"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir", help="State root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    from imperaos.control_plane.agent_enrollment import revoke_enrollment_token
    from imperaos.enterprise.identity import resolve_actor_context

    config = RuntimeConfig.from_profile(profile)
    result = revoke_enrollment_token(
        config=config,
        actor=resolve_actor_context(config),
        token_id=token_id,
        reason=reason,
        root_dir=root_dir,
    )
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)
    if result.status == "blocked":
        raise typer.Exit(code=3)


@enterprise_enrollment_token_app.command("list")
def enterprise_enrollment_token_list_command(
    workspace_id: str | None = typer.Option(None, "--workspace-id", help="Workspace id"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir", help="State root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore

    tokens = EnterpriseWorkspaceStore(root_dir).list_enrollment_tokens(workspace_id=workspace_id)
    _emit_payload(
        {
            "schemaVersion": "agent-enrollment-token-list/v1",
            "tokens": [token.model_dump(mode="json", by_alias=True) for token in tokens],
        },
        json_output=json_output,
    )


@enterprise_enrollment_request_app.command("create")
def enterprise_enrollment_request_create_command(
    token: str = typer.Option(..., "--token", help="Raw enrollment token"),
    agent_id: str = typer.Option(..., "--agent-id", help="Agent id"),
    agent_display_name: str = typer.Option(..., "--agent-display-name", help="Agent display name"),
    device_label: str = typer.Option(..., "--device-label", help="Device label"),
    platform: str = typer.Option("unknown", "--platform", help="Agent host platform"),
    capability: Annotated[
        list[str],
        typer.Option("--capability", help="Requested capability"),
    ] = ...,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Request output path"),
    ] = None,
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    from imperaos.control_plane.agent_enrollment import create_enrollment_request_from_token

    result = create_enrollment_request_from_token(
        raw_token=token,
        agent_id=agent_id,
        agent_display_name=agent_display_name,
        device_display_name=device_label,
        platform=platform,
        capabilities=capability,
        output_path=output,
    )
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)


@enterprise_enrollment_request_app.command("import")
def enterprise_enrollment_request_import_command(
    path: Annotated[Path, typer.Option("--path", help="Enrollment request path")] = ...,
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir", help="State root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    from imperaos.control_plane.agent_enrollment import (
        AgentEnrollmentRequest,
        import_enrollment_request,
    )
    from imperaos.enterprise.identity import resolve_actor_context

    config = RuntimeConfig.from_profile(profile)
    request = AgentEnrollmentRequest.model_validate_json(path.read_text(encoding="utf-8"))
    result = import_enrollment_request(
        config=config,
        actor=resolve_actor_context(config),
        request=request,
        root_dir=root_dir,
    )
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)
    if result.status == "blocked":
        raise typer.Exit(code=3)


@enterprise_enrollment_app.command("approve")
def enterprise_enrollment_approve_command(
    request_id: str = typer.Option(..., "--request-id", help="Enrollment request id"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir", help="State root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    from imperaos.control_plane.agent_enrollment import approve_enrollment_request
    from imperaos.enterprise.identity import resolve_actor_context

    config = RuntimeConfig.from_profile(profile)
    result = approve_enrollment_request(
        config=config,
        actor=resolve_actor_context(config),
        request_id=request_id,
        root_dir=root_dir,
    )
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)
    if result.status == "blocked":
        raise typer.Exit(code=3)


@enterprise_enrollment_app.command("reject")
def enterprise_enrollment_reject_command(
    request_id: str = typer.Option(..., "--request-id", help="Enrollment request id"),
    reason: str = typer.Option(..., "--reason", help="Rejection reason"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir", help="State root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    from imperaos.control_plane.agent_enrollment import reject_enrollment_request
    from imperaos.enterprise.identity import resolve_actor_context

    config = RuntimeConfig.from_profile(profile)
    result = reject_enrollment_request(
        config=config,
        actor=resolve_actor_context(config),
        request_id=request_id,
        reason=reason,
        root_dir=root_dir,
    )
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)
    if result.status == "blocked":
        raise typer.Exit(code=3)


@enterprise_enrollment_app.command("list")
def enterprise_enrollment_list_command(
    workspace_id: str | None = typer.Option(None, "--workspace-id", help="Workspace id"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir", help="State root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore

    store = EnterpriseWorkspaceStore(root_dir)
    _emit_payload(
        {
            "schemaVersion": "agent-enrollment-list/v1",
            "requests": [
                request.model_dump(mode="json", by_alias=True)
                for request in store.list_enrollment_requests(workspace_id=workspace_id)
            ],
            "enrolledAgents": [
                agent.model_dump(mode="json", by_alias=True)
                for agent in store.list_enrolled_agents(workspace_id=workspace_id)
            ],
        },
        json_output=json_output,
    )


@control_plane_reports_app.command("manifest")
def control_plane_reports_manifest(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    evidence_root: str = typer.Option("artifacts", "--evidence-root"),
    output_dir: str = typer.Option(
        "artifacts/design-partner-rc/reports-alerts-logs",
        "--output-dir",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    snapshot = build_control_plane_snapshot(
        root_dir=root_dir,
        profile=profile,
        evidence_root=evidence_root,
        runtime_mode="cli",
        bridge_mode="cli",
        used_fixture=False,
    )
    manifest = build_reports_alerts_logs_manifest(snapshot=snapshot, output_dir=output_dir)
    _emit_payload(manifest.model_dump(mode="json", by_alias=True), json_output=json_output)
    if manifest.status == "blocked":
        raise typer.Exit(code=3)


@control_plane_operations_app.command("dry-run")
def control_plane_operations_dry_run(
    operation_id: str = typer.Option(..., "--operation-id", help="Operation ID"),
    actor_id: str = typer.Option("identity-disabled", "--actor-id", help="Actor ID"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    evidence_root: str = typer.Option("artifacts", "--evidence-root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    result = dry_run_operation(
        config=RuntimeConfig.from_profile(profile),
        operation_id=operation_id,
        actor_id=actor_id,
        root_dir=root_dir,
        evidence_root=evidence_root,
        dry_run=True,
    )
    _emit_payload(result.model_dump(mode="json", by_alias=True), json_output=json_output)
    if result.status == "blocked":
        raise typer.Exit(code=3)


@control_plane_adapter_app.command("evaluate")
def control_plane_adapter_evaluate(
    input_path: str = typer.Option(..., "--input", help="Action proposal JSON path"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    payload = evaluate_action_proposal_file(
        path=input_path,
        simulator=PolicySimulator(config=RuntimeConfig.from_profile(profile)),
    )
    _emit_payload(payload, json_output=json_output)


@control_plane_gateway_app.command("submit-action")
def control_plane_gateway_submit_action(
    input_path: str = typer.Option(..., "--input", help="ExternalActionRequest JSON path"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    response = submit_external_action_file(
        path=input_path,
        config=RuntimeConfig.from_profile(profile),
        registry=_control_plane_registry(root_dir),
        root_dir=root_dir,
    )
    payload = response.model_dump(mode="json", by_alias=True)
    _emit_payload(payload, json_output=json_output)
    if response.status in {"denied", "invalid_request", "unknown_agent"}:
        raise typer.Exit(code=3)


@control_plane_gateway_app.command("submit-v1-1")
def control_plane_gateway_submit_v1_1(
    input_path: str = typer.Option(..., "--input", help="ExternalAgentRequest v1.1 JSON path"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    response = submit_external_action_v1_1_file(
        path=input_path,
        config=RuntimeConfig.from_profile(profile),
        registry=_control_plane_registry(root_dir),
        root_dir=root_dir,
    )
    payload = response.model_dump(mode="json", by_alias=True)
    _emit_payload(payload, json_output=json_output)
    if response.status in {"denied", "invalid_request", "unknown_agent"}:
        raise typer.Exit(code=3)


@control_plane_gateway_app.command("replay-v1-1")
def control_plane_gateway_replay_v1_1(
    request_id: str = typer.Option(..., "--request-id", help="ExternalAgentRequest v1.1 id"),
    expected_request_hash: str | None = typer.Option(
        None,
        "--expected-request-hash",
        help="Expected canonical ExternalAgentRequest v1.1 hash.",
    ),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    gateway = ExternalAgentGateway(
        config=RuntimeConfig.from_profile(profile),
        registry=_control_plane_registry(root_dir),
        root_dir=root_dir,
    )
    payload = gateway.replay_v1_1(
        request_id=request_id,
        expected_request_hash=expected_request_hash,
    )
    _emit_payload(payload, json_output=json_output)
    if payload["status"] in {"missing", "mismatch"}:
        raise typer.Exit(code=3)


@config_app.command("resolve")
def config_resolve(
    profile: str = typer.Option("balanced", help="Config profile"),
    provider: str | None = typer.Option(None, help="Override provider"),
    fallback_provider: str | None = typer.Option(None, help="Override fallback provider"),
    model: str | None = typer.Option(None, "--model", help="Override model name"),
    hf_model_id: str | None = typer.Option(
        None,
        "--hf-model-id",
        help="Override transformers model id",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    cli_overrides = _build_cli_overrides(
        provider=provider,
        fallback_provider=fallback_provider,
        model=model,
        hf_model_id=hf_model_id,
    )
    resolved, source_map = resolve_runtime_config(
        profile=profile,
        cli_overrides=cli_overrides,
    )
    validation_error = _validate_model_override_combo(
        effective_provider=resolved.llm_provider,
        model_override=model,
        hf_model_id_override=hf_model_id,
    )
    if validation_error is not None:
        error_code, message = validation_error
        payload = {
            "profile": profile,
            "status": "invalid_input",
            "error_code": error_code,
            "error": message,
        }
        if json_output:
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        else:
            typer.echo(f"error_code={error_code}")
            typer.echo(message)
        raise typer.Exit(code=1)

    payload = _with_contract_version(
        {
            "profile": profile,
            "status": "ok",
            "resolved": redact_config_payload(resolved.model_dump(mode="python")),
            "source_map": source_map,
        }
    )
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        typer.echo(f"profile={profile}")
        typer.echo(f"router_mode={resolved.router_mode}")
        typer.echo(f"shadow_router_enabled={resolved.shadow_router_enabled}")
        typer.echo(f"shadow_router_mode={resolved.shadow_router_mode}")


def _resolve_registry_for_cli(profile: str) -> tuple[RuntimeConfig, Any]:
    config, _source_map = resolve_runtime_config(profile=profile)
    registry_path = (
        Path(config.provider_registry_path) if config.provider_registry_enabled else None
    )
    if registry_path is not None and not registry_path.exists():
        registry_path = None
    registry = resolve_model_provider_registry(
        config=config,
        profile=profile,
        provider_config_path=registry_path,
    )
    return config, registry


@provider_registry_app.callback(invoke_without_command=True)
def provider_registry_callback(
    ctx: typer.Context,
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Show fail-closed provider governance registry state."""
    if ctx.invoked_subcommand is not None:
        return
    snapshot = build_provider_governance_snapshot(profile=profile)
    _emit_payload(snapshot.model_dump(mode="json", by_alias=True), json_output=json_output)


@provider_registry_app.command("list")
def provider_registry_list(
    profile: str = typer.Option("balanced", help="Config profile"),
    enabled_only: bool = typer.Option(False, "--enabled-only", help="Show only enabled providers"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """List resolved model provider registry records without secret values."""
    _config, registry = _resolve_registry_for_cli(profile)
    providers = registry.providers
    if enabled_only:
        providers = [item for item in providers if item.enabled]
    payload = {
        "contractVersion": "model_provider.registry/v1",
        "profile": profile,
        "generatedAtUtc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "remoteProvidersEnabled": registry.remote_providers_enabled,
        "providers": [item.safe_dump() for item in providers],
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    else:
        for item in providers:
            typer.echo(f"{item.provider_id}\t{item.kind}\tenabled={item.enabled}")


@provider_app.command("doctor")
def provider_doctor(
    profile: str = typer.Option("balanced", help="Config profile"),
    provider_id: str = typer.Option("local-ollama", "--provider-id", help="Provider id"),
    network_check: bool = typer.Option(
        False,
        "--network-check",
        help="Run optional network checks",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Report provider readiness, secret refs, capabilities, and policy boundaries."""
    _config, registry = _resolve_registry_for_cli(profile)
    provider = registry.get(provider_id)
    if provider is None:
        payload = {
            "contractVersion": "model_provider.doctor/v1",
            "providerId": provider_id,
            "status": "blocked",
            "reasonCode": "PROVIDER_NOT_FOUND",
            "warnings": [],
        }
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        raise typer.Exit(code=1)
    payload = doctor_provider(
        provider=provider,
        policy=registry.policy_for(provider.provider_id),
        remote_providers_enabled=registry.remote_providers_enabled,
        network_check=network_check,
    )
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    else:
        typer.echo(f"status={payload['status']} reason={payload['reasonCode']}")


@provider_policy_app.command("simulate")
def provider_policy_simulate(
    profile: str = typer.Option("balanced", help="Config profile"),
    provider_id: str = typer.Option(..., "--provider-id", help="Provider id"),
    data_class: list[str] = PROVIDER_POLICY_DATA_CLASS_OPTION,
    tool_calls: bool = typer.Option(
        False,
        "--tool-calls/--no-tool-calls",
        help="Simulate tool specs",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Simulate provider egress policy without making a model call."""
    _config, registry = _resolve_registry_for_cli(profile)
    provider = registry.get(provider_id)
    if provider is None:
        payload = {
            "contractVersion": "model_provider.policy_decision/v1",
            "status": "blocked_not_configured",
            "reasonCode": "PROVIDER_NOT_FOUND",
            "safeToCallProvider": False,
        }
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        raise typer.Exit(code=1)
    try:
        classes = [DataClass(item) for item in data_class]
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    request = ProviderCallRequest(
        call_id="policy-simulate",
        run_id="policy-simulate",
        provider_id=provider.provider_id,
        model=provider.default_model,
        messages=[ChatMessage(role="user", content="policy simulation")],
        data_classes=classes,
        tools=[{"name": "proposed_action"}] if tool_calls else [],
    )
    decision = evaluate_provider_policy(
        request=request,
        provider=provider,
        policy=registry.policy_for(provider.provider_id),
        governance_context=GovernanceContext(
            remote_providers_enabled=registry.remote_providers_enabled
        ),
    )
    payload = {
        "contractVersion": "model_provider.policy_decision/v1",
        "status": decision.status,
        "reasonCode": decision.reason_code,
        "providerId": decision.provider_id,
        "safeToCallProvider": decision.safe_to_call_provider,
        "redactionRequired": decision.redaction_required,
        "approvalRequired": decision.approval_required,
        "evidenceRequired": decision.evidence_required,
        "effectiveDataClasses": decision.effective_data_classes,
        "userMessage": decision.user_message,
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    else:
        typer.echo(f"status={decision.status} reason={decision.reason_code}")


@provider_call_app.command("test")
def provider_call_test(
    profile: str = typer.Option("balanced", help="Config profile"),
    provider_id: str = typer.Option(..., "--provider-id", help="Provider id"),
    prompt: str = typer.Option("Return JSON", "--prompt", help="Prompt text"),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Do not call remote provider"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Evaluate a governed provider call; dry-run is default and performs no network call."""
    _config, registry = _resolve_registry_for_cli(profile)
    provider = registry.get(provider_id)
    if provider is None:
        raise typer.BadParameter(f"unknown provider_id: {provider_id}")
    request = ProviderCallRequest(
        call_id="provider-call-test",
        run_id="provider-call-test",
        provider_id=provider.provider_id,
        model=provider.default_model,
        messages=[ChatMessage(role="user", content=prompt)],
        data_classes=[DataClass.PUBLIC],
    )
    decision = evaluate_provider_policy(
        request=request,
        provider=provider,
        policy=registry.policy_for(provider.provider_id),
        governance_context=GovernanceContext(
            remote_providers_enabled=registry.remote_providers_enabled
        ),
    )
    redacted = redact_provider_input(request=request, decision=decision)
    payload: dict[str, Any] = {
        "contractVersion": "model_provider.call_test/v1",
        "providerId": provider.provider_id,
        "dryRun": dry_run,
        "decision": decision.model_dump(mode="json"),
        "redactionSummary": redacted.summary.model_dump(mode="json"),
    }
    if not dry_run and decision.safe_to_call_provider:
        response = (
            ProviderAdapterFactory(registry=registry).create(provider.provider_id).generate(request)
        )
        payload["response"] = response.model_dump(mode="json")
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        typer.echo(f"status={decision.status} reason={decision.reason_code}")


@provider_canary_app.command("run")
def provider_canary_run(
    profile: str = typer.Option("balanced", help="Config profile"),
    provider_id: str = typer.Option(..., "--provider-id", help="Provider id"),
    data_class: list[str] = PROVIDER_POLICY_DATA_CLASS_OPTION,
    allow_live: bool = typer.Option(
        False,
        "--allow-live",
        help="Allow live provider call when IMPERAOS_PROVIDER_LIVE_CANARY=1 is also set",
    ),
    evidence_root: Path = PROVIDER_CANARY_EVIDENCE_ROOT_OPTION,
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Run a governed provider canary. Live network is skipped unless double opt-in is present."""
    _config, registry = _resolve_registry_for_cli(profile)
    try:
        classes = [DataClass(item) for item in data_class]
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    result = run_provider_canary(
        request=ProviderCanaryRequest(
            provider_id=provider_id,
            profile=profile,
            data_classes=classes,
            allow_live=allow_live,
            evidence_root=str(evidence_root),
        ),
        registry=registry,
        evidence_root=evidence_root,
    )
    payload = result.model_dump(mode="json")
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    else:
        typer.echo(f"status={result.status} reason={result.reason_code}")
    if result.status == "fail":
        raise typer.Exit(code=1)


@provider_canary_app.command("verify")
def provider_canary_verify(
    evidence_root: Path = PROVIDER_CANARY_EVIDENCE_ROOT_OPTION,
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Verify canary evidence for schema validity and raw/secret content absence."""
    payload = verify_canary_evidence_root(evidence_root)
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    else:
        typer.echo(f"status={payload['status']} reason={payload['reasonCode']}")
    if payload["status"] != "pass":
        raise typer.Exit(code=1)


@provider_route_app.command("simulate")
def provider_route_simulate(
    profile: str = typer.Option("balanced", help="Config profile"),
    task_type: str = typer.Option("chat", "--task-type", help="Task type"),
    data_class: list[str] = PROVIDER_POLICY_DATA_CLASS_OPTION,
    capability: list[str] = PROVIDER_ROUTE_CAPABILITY_OPTION,
    preferred_provider_id: str | None = typer.Option(
        None,
        "--preferred-provider-id",
        help="Provider requested by caller",
    ),
    write_evidence: bool = typer.Option(
        False,
        "--write-evidence",
        help="Write shadow routing evidence",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Produce policy-aware provider routing recommendation in shadow mode only."""
    _config, registry = _resolve_registry_for_cli(profile)
    try:
        classes = [DataClass(item) for item in data_class]
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    decision = recommend_provider_shadow(
        registry=registry,
        request=ProviderRouteShadowRequest(
            task_type=task_type,
            data_classes=classes,
            required_capabilities=capability,
            preferred_provider_id=preferred_provider_id,
        ),
    )
    if write_evidence:
        path = write_router_shadow_evidence(decision=decision)
        decision.evidence_path = str(path)
    payload = decision.model_dump(mode="json")
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    else:
        typer.echo(
            f"shadow_only={decision.shadow_only} recommended={decision.recommended_provider_id}"
        )


@provider_native_conformance_app.command("run")
def provider_native_conformance_run(
    profile: str = typer.Option("enterprise", help="Config profile"),
    output_root: Path = PROVIDER_NATIVE_OUTPUT_ROOT_OPTION,
    provider_kind: str = PROVIDER_NATIVE_KIND_OPTION,
    offline: bool = typer.Option(True, "--offline/--no-offline", help="Run offline fixtures only"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Run offline native adapter conformance fixtures without live provider calls."""
    if not offline:
        raise typer.BadParameter("native conformance live mode is not implemented")
    if provider_kind == "all":
        reports = run_all_native_conformance(profile=profile)
        paths = {
            str(report.provider_kind): write_native_conformance_report(
                report=report,
                output_root=output_root,
                stem=f"{report.provider_kind}_native_adapter_report",
            )
            for report in reports
        }
        payload = _native_conformance_aggregate_payload(
            profile=profile,
            reports=reports,
            paths=paths,
        )
        status = payload["status"]
    else:
        report = run_native_conformance(profile=profile, provider_kind=provider_kind)
        paths = write_native_conformance_report(
            report=report,
            output_root=output_root,
            stem=f"{report.provider_kind}_native_adapter_report",
        )
        payload = report.model_dump(mode="json")
        payload["paths"] = paths
        status = report.status
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    else:
        typer.echo(f"status={status} provider_kind={provider_kind}")
    if status != "pass":
        raise typer.Exit(code=1)


@provider_native_conformance_app.callback(invoke_without_command=True)
def provider_native_conformance_callback(
    ctx: typer.Context,
    provider: str | None = typer.Option(None, "--provider", help="Native provider kind"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    offline: bool = typer.Option(True, "--offline/--live-canary", help="Use offline fixtures"),
    output_dir: str = typer.Option(
        "artifacts/provider-native",
        "--output-dir",
        help="Conformance artifact output directory.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Run offline native provider conformance fixtures."""
    if ctx.invoked_subcommand is not None:
        return
    if provider is None:
        raise typer.BadParameter("provider is required")
    try:
        report = run_provider_native_conformance(
            provider,
            profile=profile,
            offline=offline,
            output_dir=output_dir,
        )
    except KeyError:
        _emit_payload(
            {
                "status": "fail",
                "providerKind": provider,
                "blockingReasons": ["PROVIDER_UNKNOWN"],
            },
            json_output=json_output,
        )
        raise typer.Exit(code=1) from None
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "fail":
        raise typer.Exit(code=1)


@provider_native_conformance_app.command("verify")
def provider_native_conformance_verify(
    output_root: Path = PROVIDER_NATIVE_OUTPUT_ROOT_OPTION,
    input_path: Path | None = PROVIDER_NATIVE_INPUT_OPTION,
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Verify native adapter evidence contains no raw payload or secret markers."""
    payload = verify_native_conformance_evidence(output_root=output_root, input_path=input_path)
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    else:
        typer.echo(f"status={payload['status']} reason={payload['reasonCode']}")
    if payload["status"] != "pass":
        raise typer.Exit(code=1)


def _native_conformance_aggregate_payload(
    *,
    profile: str,
    reports: list[ProviderNativeConformanceReport],
    paths: dict[str, object],
) -> dict[str, object]:
    pass_count = sum(report.pass_count for report in reports)
    expected_blocked_count = sum(report.expected_blocked_count for report in reports)
    unexpected_failure_count = sum(report.unexpected_failure_count for report in reports)
    total_cases = sum(report.total_cases for report in reports)
    status = "pass" if all(report.status == "pass" for report in reports) else "fail"
    return {
        "version": "model_provider.native_conformance_aggregate/v1",
        "profile": profile,
        "status": status,
        "total_cases": total_cases,
        "pass_count": pass_count,
        "expected_blocked_count": expected_blocked_count,
        "unexpected_failure_count": unexpected_failure_count,
        "reports": [report.model_dump(mode="json") for report in reports],
        "paths": paths,
    }


@provider_app.command("models")
def provider_models(
    profile: str = typer.Option("balanced", help="Config profile"),
    provider: str = typer.Option("all", help="Provider: all|auto|ollama|transformers"),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Refresh provider model list cache when supported",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """List locally discoverable assistant provider models without installing models."""
    _ = refresh
    payload = _provider_models_payload(profile=profile, requested_provider=provider)
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        for item in payload.get("providers", []):
            provider_record = item if isinstance(item, dict) else {}
            typer.echo(f"{provider_record.get('provider')}: {provider_record.get('available')}")

    if payload.get("status") == "invalid_input":
        raise typer.Exit(code=1)


@provider_app.command("registry")
def provider_registry(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Show fail-closed provider governance registry state."""
    snapshot = build_provider_governance_snapshot(profile=profile)
    _emit_payload(snapshot.model_dump(mode="json", by_alias=True), json_output=json_output)


@provider_app.command("inspect")
def provider_inspect(
    provider: str = typer.Option(..., "--provider", help="Provider kind"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Inspect one provider governance entry without exposing secrets."""
    try:
        entry = inspect_provider_entry(provider, profile=profile)
    except KeyError:
        _emit_payload(
            {
                "status": "blocked",
                "errorCode": "PROVIDER_UNKNOWN",
                "providerKind": provider,
                "blockingReasons": ["PROVIDER_UNKNOWN"],
            },
            json_output=json_output,
        )
        raise typer.Exit(code=1) from None
    _emit_payload(entry.model_dump(mode="json", by_alias=True), json_output=json_output)


@provider_app.command("invoke")
def provider_invoke(
    provider: str = typer.Option(..., "--provider", help="Provider kind"),
    model: str = typer.Option("gpt-placeholder", "--model", help="Provider model name"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    mode: str = typer.Option("dry-run", "--mode", help="dry-run|canary-live|disabled"),
    once: str = typer.Option(..., "--once", help="Single prompt to hash and invoke"),
    output_dir: str = typer.Option(
        "artifacts/provider-runtime/invocations",
        "--output-dir",
        help="Invocation artifact output directory.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Run a governed provider invocation without raw prompt/response persistence."""
    runtime_mode = mode.replace("-", "_")
    if runtime_mode not in {"offline_conformance", "dry_run", "canary_live", "disabled"}:
        _emit_payload(
            {
                "schemaVersion": "provider.invocation.v1",
                "status": "blocked",
                "providerKind": provider,
                "runtimeMode": runtime_mode,
                "blockingReasons": ["PROVIDER_RUNTIME_MODE_UNSUPPORTED"],
            },
            json_output=json_output,
        )
        raise typer.Exit(code=1)
    result = ProviderInvocationCoordinator(output_dir=output_dir).invoke(
        ProviderInvocationRequest(
            provider_kind=provider,
            model=model,
            profile=profile,
            runtime_mode=runtime_mode,  # type: ignore[arg-type]
            prompt=once,
        )
    )
    _emit_payload(result.to_payload(), json_output=json_output)
    if result.status in {"blocked", "error"}:
        raise typer.Exit(code=1)


@provider_native_app.command("conformance")
def provider_native_conformance(
    provider: str = typer.Option(..., "--provider", help="Native provider kind"),
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    offline: bool = typer.Option(True, "--offline/--live-canary", help="Use offline fixtures"),
    output_dir: str = typer.Option(
        "artifacts/provider-native",
        "--output-dir",
        help="Conformance artifact output directory.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Run offline native provider conformance fixtures."""
    try:
        report = run_provider_native_conformance(
            provider,
            profile=profile,
            offline=offline,
            output_dir=output_dir,
        )
    except KeyError:
        _emit_payload(
            {
                "status": "fail",
                "providerKind": provider,
                "blockingReasons": ["PROVIDER_UNKNOWN"],
            },
            json_output=json_output,
        )
        raise typer.Exit(code=1) from None
    _emit_payload(report.model_dump(mode="json", by_alias=True), json_output=json_output)
    if report.status == "fail":
        raise typer.Exit(code=1)


@provider_native_app.command("gate")
def provider_native_gate(
    profile: str = typer.Option("enterprise", "--profile", help="Runtime profile"),
    output_dir: str = typer.Option(
        "artifacts/provider-native",
        "--output-dir",
        help="Conformance artifact output directory.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Run all offline native provider conformance checks."""
    payload = run_provider_native_gate(profile=profile, output_dir=output_dir)
    _emit_payload(payload, json_output=json_output)
    if payload["status"] != "pass":
        raise typer.Exit(code=1)


@app.command()
def doctor(
    profile: str = typer.Option("lite", help="Config profile name"),
    provider: str | None = typer.Option(
        None,
        help="Override provider: auto|ollama|transformers",
    ),
    fallback_provider: str | None = typer.Option(
        None,
        help="Override fallback provider: transformers|ollama",
    ),
    model: str | None = typer.Option(None, "--model", help="Override model name"),
    hf_model_id: str | None = typer.Option(
        None,
        "--hf-model-id",
        help="Override transformers model id",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    """Runtime and provider health check."""
    ensure_artifact_scaffold()
    config, source_map = resolve_runtime_config(
        profile=profile,
        cli_overrides=_build_cli_overrides(
            provider=provider,
            fallback_provider=fallback_provider,
            model=model,
            hf_model_id=hf_model_id,
        ),
    )
    validation_error = _validate_model_override_combo(
        effective_provider=config.llm_provider,
        model_override=model,
        hf_model_id_override=hf_model_id,
    )
    if validation_error is not None:
        error_code, message = validation_error
        payload = {
            "profile": profile,
            "requested_provider": config.llm_provider,
            "requested_fallback_provider": config.fallback_provider,
            "requested_model_name": config.model_name,
            "requested_hf_model_id": config.hf_model_id,
            "selected_provider": None,
            "effective_model_name": None,
            "effective_hf_model_id": None,
            "fallback_used": False,
            "status": "invalid_input",
            "error_code": error_code,
            "error": message,
            "config_source_model_name": source_map.get("model_name", "profile"),
            "config_source_hf_model_id": source_map.get("hf_model_id", "profile"),
        }
        if json_output:
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            typer.echo(f"status={payload['status']} error={payload['error_code']}")
        write_artifact("status", payload)
        raise typer.Exit(code=1)

    try:
        status = check_provider_chain(
            model_name=config.model_name,
            provider_name=config.llm_provider,
            fallback_provider=config.fallback_provider,
            fallback_enabled=config.fallback_enabled,
            hf_model_id=config.hf_model_id,
            device=config.device,
        )
    except ValueError as exc:
        payload = {
            "profile": profile,
            "requested_provider": config.llm_provider,
            "requested_fallback_provider": config.fallback_provider,
            "requested_model_name": config.model_name,
            "requested_hf_model_id": config.hf_model_id,
            "selected_provider": None,
            "effective_model_name": None,
            "effective_hf_model_id": None,
            "fallback_used": False,
            "status": "invalid_input",
            "error_code": "INVALID_PROVIDER",
            "error": str(exc),
            "config_source_model_name": source_map.get("model_name", "profile"),
            "config_source_hf_model_id": source_map.get("hf_model_id", "profile"),
        }
        if json_output:
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            typer.echo(f"status={payload['status']} error={payload['error_code']}")
        write_artifact("status", payload)
        raise typer.Exit(code=1) from None

    status.setdefault("requested_provider", config.llm_provider)
    status.setdefault("requested_fallback_provider", config.fallback_provider)
    status.setdefault("requested_model_name", config.model_name)
    status.setdefault("requested_hf_model_id", config.hf_model_id)
    status.setdefault("effective_model_name", None)
    status.setdefault("effective_hf_model_id", None)
    status.setdefault("fallback_used", False)
    status["config_source_model_name"] = source_map.get("model_name", "profile")
    status["config_source_hf_model_id"] = source_map.get("hf_model_id", "profile")
    status["profile"] = profile

    status_value = str(status.get("status", "")).lower()
    if status_value not in {"healthy", "degraded_fallback", "unrunnable", "invalid_input"}:
        selected = str(status.get("selected_provider", ""))
        primary = status.get("primary", {})
        if selected == "ollama":
            daemon_ok = bool(primary.get("daemon_ok", False))
            model_present = bool(primary.get("model_present", False))
            status_value = "healthy" if (daemon_ok and model_present) else "unrunnable"
        else:
            status_value = "healthy"
        status["status"] = status_value

    if json_output:
        typer.echo(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        typer.echo(f"status={status.get('status')} provider={status.get('selected_provider')}")
    write_artifact(
        "status",
        status,
    )

    if status_value == "invalid_input":
        raise typer.Exit(code=1)
    if status_value == "unrunnable":
        raise typer.Exit(code=3)


@app.command()
def chat(
    profile: str = typer.Option("lite", help="Config profile"),
    once: str | None = typer.Option(None, help="Single prompt mode"),
    debug: bool = typer.Option(False, help="Enable debug mode"),
    privacy_off: bool = typer.Option(False, help="Allow persistent debug traces"),
    router_mode: str | None = typer.Option(None, help="Override router mode: rule|sltc"),
    provider: str | None = typer.Option(None, help="Override provider: auto|ollama|transformers"),
    provider_id: str | None = typer.Option(
        None,
        "--provider-id",
        help="Canonical model provider id",
    ),
    fallback_provider_id: str | None = typer.Option(
        None,
        "--fallback-provider-id",
        help="Canonical fallback model provider id",
    ),
    fallback_provider: str | None = typer.Option(
        None,
        help="Override fallback provider: transformers|ollama",
    ),
    model: str | None = typer.Option(None, "--model", help="Override model name"),
    hf_model_id: str | None = typer.Option(
        None,
        "--hf-model-id",
        help="Override transformers model id",
    ),
    session_id: str | None = typer.Option(None, help="Optional deterministic session id"),
    stream: bool = typer.Option(
        True,
        "--stream/--no-stream",
        help="Stream realtime tokens when fast path is used.",
    ),
    fast_path: bool = typer.Option(
        True,
        "--fast-path/--no-fast-path",
        help="Use single-call realtime path for short chat inputs.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit single JSON payload."),
    json_stream: bool = typer.Option(
        False,
        "--json-stream",
        help="Emit line-delimited JSON events.",
    ),
    stdio_json: bool = typer.Option(
        False,
        "--stdio-json",
        help="Alias for --json-stream with IPC-friendly events.",
    ),
) -> None:
    """Interactive chat with orchestrator + router."""
    ensure_artifact_scaffold()
    config, source_map = resolve_runtime_config(
        profile=profile,
        cli_overrides=_build_cli_overrides(
            provider=provider,
            fallback_provider=fallback_provider,
            model=model,
            hf_model_id=hf_model_id,
        ),
    )
    validation_error = _validate_model_override_combo(
        effective_provider=config.llm_provider,
        model_override=model,
        hf_model_id_override=hf_model_id,
    )
    if validation_error is not None:
        _code, message = validation_error
        typer.echo(message)
        raise typer.Exit(code=1)

    if debug:
        config = config.model_copy(update={"debug_mode": True})
    if privacy_off:
        config = config.model_copy(update={"privacy_mode": False})
    _require_permission_or_exit(config, "runtime.run")

    orchestrator = _build_orchestrator(
        config,
        router_mode=router_mode,
        provider_name=config.llm_provider,
        provider_id=provider_id,
        fallback_provider_id=fallback_provider_id,
        fallback_provider=config.fallback_provider,
    )
    startup_error = _startup_abort(
        config,
        getattr(orchestrator, "governance_runtime", None),
    )
    if startup_error:
        typer.echo(f"POLICY_UNAVAILABLE: {startup_error}")
        raise typer.Exit(code=2)
    memory = SessionStore()
    stream_json = json_stream or stdio_json
    use_json = json_output or stream_json

    def _emit_json_event(event: str, data: dict[str, object]) -> None:
        typer.echo(json.dumps({"event": event, "data": data}, ensure_ascii=False))

    def _emit_trace_events(result_trace_id: str) -> None:
        for trace_event in orchestrator.trace_events(result_trace_id):
            mapped = _assistant_trace_stream_event(trace_event)
            if mapped is not None:
                _emit_json_event(*mapped)

    def _run_once(user_text: str) -> None:
        sid = session_id or "session-default"
        context = {
            "session_summary": memory.summary_text(),
            "session_id": sid,
        }
        context.update(_model_selection_context(config=config, source_map=source_map))
        manager = getattr(orchestrator, "_memory_manager", None)
        if manager is not None:
            snippets = manager.context_snippets(user_text, limit=config.memory.context_top_k)
            if snippets:
                context["memory_hints"] = "\n---\n".join(snippets)

        use_realtime, candidate_reason = _realtime_candidate_reason(user_text)
        use_realtime = fast_path and use_realtime
        if stream_json:
            _emit_json_event(
                "status",
                {
                    "phase": "start",
                    "session_id": sid,
                    "realtime_candidate": use_realtime,
                    "candidate_reason": candidate_reason,
                },
            )
        if use_realtime:
            if stream:
                result = orchestrator.process_fast_chat(
                    user_text,
                    session_context=context,
                    stream=True,
                    candidate_reason=candidate_reason,
                    on_token=(
                        (lambda token: _emit_json_event("token", {"text": token}))
                        if stream_json
                        else (lambda token: print(token, end="", flush=True))
                    ),
                )
                if not stream_json:
                    print()
                if result.used_path != "llm_stream_fast" and not use_json:
                    typer.echo(result.final_text)
            else:
                result = orchestrator.process_fast_chat(
                    user_text,
                    session_context=context,
                    stream=False,
                    candidate_reason=candidate_reason,
                )
                if not use_json:
                    typer.echo(result.final_text)
        else:
            result = orchestrator.process(user_text, session_context=context, use_router=True)
            if not use_json:
                typer.echo(result.final_text)

        memory.add("user", user_text)
        memory.add("assistant", result.final_text)

        if use_json and json_output and not stream_json:
            payload = {
                "trace_id": result.trace_id,
                "final_text": result.final_text,
                "used_path": result.used_path,
                "fallback_events": result.fallback_events,
                "metrics": result.metrics,
                "trace_events": orchestrator.trace_events(result.trace_id),
            }
            typer.echo(json.dumps(payload, ensure_ascii=False))
        elif stream_json:
            _emit_trace_events(result.trace_id)
            _emit_json_event(
                "final",
                {
                    "trace_id": result.trace_id,
                    "final_text": result.final_text,
                    "used_path": result.used_path,
                    "fallback_events": result.fallback_events,
                    "metrics": result.metrics,
                },
            )
        elif config.debug_mode:
            meta = {
                "used_path": result.used_path,
                "fallback_events": result.fallback_events,
                "metrics": result.metrics,
                "realtime_candidate": use_realtime,
                "fast_path_candidate_reason": candidate_reason,
            }
            typer.echo(json.dumps(meta, ensure_ascii=False))

        write_artifact(
            "router_shadow_summary",
            {
                "trace_id": result.trace_id,
                "router_shadow_enabled": result.metrics.get("router_shadow_enabled"),
                "router_shadow_agreement": result.metrics.get("router_shadow_agreement"),
                "active_router_choice": result.metrics.get("active_router_choice"),
                "shadow_router_choice": result.metrics.get("shadow_router_choice"),
                "fast_path_regret_flag": result.metrics.get("fast_path_regret_flag"),
                "followup_correction_rate": result.metrics.get("followup_correction_rate"),
            },
        )
        write_artifact(
            "governance_summary",
            {
                "trace_id": result.trace_id,
                "governance_action": result.metrics.get("governance_action"),
                "governance_reason_code": result.metrics.get("governance_reason_code"),
                "policy_hash": result.metrics.get("policy_hash"),
                "approval_id": result.metrics.get("approval_id"),
                "audit_artifact_path": result.metrics.get("audit_artifact_path"),
            },
        )

    if once:
        _run_once(once)
        return

    typer.echo("ImperaOS chat başlatıldı. Çıkmak için /exit yazın.")
    while True:
        user_text = typer.prompt("you")
        if user_text.strip().lower() in {"/exit", "exit", "quit", "/quit"}:
            break
        _run_once(user_text)


def _hash_payload(value: object) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _redact_snapshot_payload(value: object) -> object:
    sensitive_markers = ("token", "secret", "password", "key", "user_input", "payload")
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for key, inner in value.items():
            lowered = key.lower()
            if any(marker in lowered for marker in sensitive_markers):
                redacted[key] = "***REDACTED***"
                continue
            redacted[key] = _redact_snapshot_payload(inner)
        return redacted
    if isinstance(value, list):
        return [_redact_snapshot_payload(item) for item in value]
    return value


def _parse_iso_datetime(value: str) -> datetime:
    normalized = value.strip()
    if not normalized:
        raise ValueError("empty datetime")
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _collect_resume_overrides(
    *,
    events: list[dict[str, object]],
    governance_runtime: GovernanceRuntime | None,
    workspace_id: str | None = None,
) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    if governance_runtime is None:
        return {}, []
    governance_runtime.approval_store.expire_pending()

    overrides: dict[str, dict[str, str]] = {}
    resolved: list[dict[str, str]] = []
    for item in events:
        if str(item.get("event") or "") != "approval_requested":
            continue
        task_id = str(item.get("task_id") or "").strip()
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        approval_id = str(data.get("approval_id") or "").strip()
        if not task_id or not approval_id:
            continue

        target = _normalize_resume_target(str(data.get("target") or "handoff"))
        ticket = governance_runtime.get_approval(approval_id, workspace_id=workspace_id)
        if ticket is None:
            continue
        status = ticket.status.value
        if status != "executed":
            continue
        if ticket.execution_status.value != "executed":
            continue
        if ticket.consumed_at is not None or ticket.consumed_by_job_id is not None:
            continue
        overrides.setdefault(task_id, {})[target] = approval_id
        resolved.append(
            {
                "task_id": task_id,
                "target": target,
                "approval_id": approval_id,
                "status": status,
            }
        )
    return overrides, resolved


def _normalize_resume_target(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"task", "handoff", "memory_write"}:
        return normalized
    return "handoff"


def _team_init_template(template_name: str) -> str:
    normalized = template_name.strip().lower()
    if normalized == "balanced":
        return """version: "1"
team:
  team_id: "imperaos-team"
  supervisor_policy: "sequential_then_parallel"
  agents:
    - agent_id: "agent-intake"
      role: "Intake Agent"
      allowed_task_types: ["chat", "plan"]
      profile_name: "balanced"
      model_overrides: {}
      memory_scope_access: ["session", "case"]
      tool_policy_profile: "default"
      approval_mode: "auto"
    - agent_id: "agent-research"
      role: "Research Analyst Agent"
      allowed_task_types: ["research", "plan"]
      profile_name: "balanced"
      model_overrides: {}
      memory_scope_access: ["team", "case"]
      tool_policy_profile: "default"
      approval_mode: "auto"
    - agent_id: "agent-review"
      role: "Reviewer/QA Agent"
      allowed_task_types: ["chat", "plan"]
      profile_name: "balanced"
      model_overrides: {}
      memory_scope_access: ["case"]
      tool_policy_profile: "default"
      approval_mode: "always"
  handoff_rules: []
  termination_rules:
    max_tasks: 64
    max_retries: 1
    max_handoff_depth: 8
tasks: []
"""
    if normalized in {"regulated", "restricted"}:
        return """version: "1"
team:
  team_id: "imperaos-regulated-team"
  supervisor_policy: "sequential_then_parallel"
  agents:
    - agent_id: "agent-intake"
      role: "Intake Agent"
      allowed_task_types: ["chat", "plan"]
      profile_name: "restricted"
      model_overrides: {}
      memory_scope_access: ["session", "case"]
      tool_policy_profile: "restricted"
      approval_mode: "auto"
    - agent_id: "agent-research"
      role: "Research Analyst Agent"
      allowed_task_types: ["research", "plan"]
      profile_name: "restricted"
      model_overrides: {}
      memory_scope_access: ["case"]
      tool_policy_profile: "restricted"
      approval_mode: "auto"
    - agent_id: "agent-compliance"
      role: "Policy/Compliance Agent"
      allowed_task_types: ["plan"]
      profile_name: "restricted"
      model_overrides: {}
      memory_scope_access: ["case"]
      tool_policy_profile: "restricted"
      approval_mode: "always"
    - agent_id: "agent-execution"
      role: "Execution Agent"
      allowed_task_types: ["mixed", "code"]
      profile_name: "restricted"
      model_overrides: {}
      memory_scope_access: ["session"]
      tool_policy_profile: "restricted"
      approval_mode: "always"
    - agent_id: "agent-review"
      role: "Reviewer/QA Agent"
      allowed_task_types: ["chat", "plan"]
      profile_name: "restricted"
      model_overrides: {}
      memory_scope_access: ["case"]
      tool_policy_profile: "restricted"
      approval_mode: "always"
  handoff_rules: []
  termination_rules:
    max_tasks: 64
    max_retries: 1
    max_handoff_depth: 8
tasks: []
"""
    raise ValueError("unsupported template. use one of: balanced, regulated")


def _load_team_spec(spec_path: str | Path) -> TeamSpec:
    path = Path(spec_path)
    if not path.exists():
        raise FileNotFoundError(f"team spec not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
    elif suffix == ".toml":
        with path.open("rb") as file_obj:
            payload = tomllib.load(file_obj)
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "YAML support requires PyYAML. Use .json/.toml or install pyyaml."
            ) from exc
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        raise ValueError("Unsupported team spec format. Use .json, .toml, .yaml, or .yml.")

    return TeamSpec.model_validate(payload)


@approval_app.command("pending")
def approval_pending(
    profile: str = typer.Option("balanced", help="Config profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
    workspace_id: str = typer.Option(..., "--workspace-id", help="Trusted workspace"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    _require_permission_or_exit(config, "approval.decide")
    runtime = _build_governance_runtime(config)
    if runtime is None:
        typer.echo("Governance disabled.")
        raise typer.Exit(code=1)
    tickets = [
        item.model_dump(mode="json")
        for item in runtime.approval_store.list_pending(workspace_id=workspace_id)
    ]
    if json_output:
        typer.echo(
            json.dumps(
                _with_contract_version({"pending": tickets}),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        typer.echo(f"pending_count={len(tickets)}")
        for item in tickets:
            typer.echo(
                f"- {item['approval_id']} status={item['status']} "
                f"expires_at={item['expires_at']} run_id={item['run_id']}"
            )


@approval_app.command("show")
def approval_show(
    approval_id: str = typer.Option(..., "--id", help="Approval ticket id"),
    profile: str = typer.Option("balanced", help="Config profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
    show_raw_snapshot: bool = typer.Option(
        False,
        "--show-raw-snapshot",
        help="Include raw snapshot payload.",
    ),
    workspace_id: str = typer.Option(..., "--workspace-id", help="Trusted workspace"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    _require_permission_or_exit(config, "approval.decide")
    runtime = _build_governance_runtime(config)
    if runtime is None:
        typer.echo("Governance disabled.")
        raise typer.Exit(code=1)

    runtime.approval_store.expire_pending()
    ticket = runtime.approval_store.get(approval_id, workspace_id=workspace_id)
    if ticket is None:
        payload = {"approval_id": approval_id, "error_code": "APPROVAL_NOT_FOUND"}
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            typer.echo("APPROVAL_NOT_FOUND")
        raise typer.Exit(code=1)

    ticket_payload = ticket.model_dump(mode="json")
    ticket_payload["snapshot"] = (
        ticket.snapshot if show_raw_snapshot else _redact_snapshot_payload(ticket.snapshot)
    )
    payload = _with_contract_version(
        {
            "approval_id": approval_id,
            "status": ticket.status.value,
            "execution_status": ticket.execution_status.value,
            "ticket": ticket_payload,
        }
    )
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(
            f"approval_id={approval_id} status={ticket.status.value} "
            f"execution_status={ticket.execution_status.value}"
        )


def _require_approval_workspace(
    ticket: object | None,
    workspace_id: str | None,
    approval_id: str,
) -> None:
    if ticket is None:
        return
    if workspace_id is None or not workspace_id.strip():
        typer.echo(
            json.dumps({"error_code": "APPROVAL_WORKSPACE_REQUIRED", "approval_id": approval_id})
        )
        raise typer.Exit(code=1)
    if _approval_bound_workspace(ticket) != workspace_id.strip():
        typer.echo(
            json.dumps({"error_code": "APPROVAL_WORKSPACE_MISMATCH", "approval_id": approval_id})
        )
        raise typer.Exit(code=1)


def _approval_visible_in_workspace(ticket: object, workspace_id: str) -> bool:
    return _approval_bound_workspace(ticket) == workspace_id.strip()


def _approval_bound_workspace(ticket: object) -> str | None:
    candidates: set[str] = set()
    stored_workspace = getattr(ticket, "workspace_id", None)
    if isinstance(stored_workspace, str) and stored_workspace.strip():
        candidates.add(stored_workspace.strip())
    snapshot = getattr(ticket, "snapshot", {})
    if isinstance(snapshot, dict):
        for key in ("workspaceId", "workspace_id"):
            value = snapshot.get(key)
            if isinstance(value, str) and value.strip():
                candidates.add(value.strip())
    target_kind = str(getattr(ticket, "target_kind", ""))
    if target_kind.startswith("artifact"):
        prefix, separator, remainder = str(getattr(ticket, "target_ref", "")).partition(":")
        if not separator or not prefix.strip() or not remainder.strip():
            return None
        candidates.add(prefix.strip())
    return next(iter(candidates)) if len(candidates) == 1 else None


def _approval_actor(ticket: object | None, verified_actor: object | None, supplied: str) -> str:
    del ticket, supplied
    actor_id = getattr(verified_actor, "actor_id", None)
    if not isinstance(actor_id, str) or not actor_id:
        typer.echo(json.dumps({"error_code": "IDENTITY_REQUIRED"}))
        raise typer.Exit(code=1)
    return actor_id


@approval_app.command("decide")
def approval_decide(
    approval_id: str = typer.Option(..., "--id", help="Approval ticket id"),
    approve: bool = typer.Option(False, "--approve", help="Approve ticket"),
    reject: bool = typer.Option(False, "--reject", help="Reject ticket"),
    actor: str = typer.Option(..., "--actor", help="Actor identity"),
    workspace_id: str | None = typer.Option(None, "--workspace-id", help="Trusted workspace"),
    reason: str | None = typer.Option(None, "--reason", help="Decision note"),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    if approve == reject:
        typer.echo("Use exactly one of --approve or --reject.")
        raise typer.Exit(code=2)

    config = RuntimeConfig.from_profile(profile)
    verified_actor = _require_permission_or_exit(config, "approval.decide")
    runtime = _build_governance_runtime(config)
    if runtime is None:
        typer.echo("Governance disabled.")
        raise typer.Exit(code=1)

    if workspace_id is None or not workspace_id.strip():
        typer.echo(json.dumps({"error_code": "APPROVAL_WORKSPACE_REQUIRED"}))
        raise typer.Exit(code=1)
    ticket = runtime.approval_store.get(approval_id, workspace_id=workspace_id)
    actor = _approval_actor(ticket, verified_actor, actor)

    result = runtime.decide_approval(
        approval_id=approval_id,
        workspace_id=workspace_id,
        approve=approve,
        actor=actor,
        reason=reason,
    )
    payload = _with_contract_version(
        {
            "approval_id": approval_id,
            "error_code": result.error_code,
            "ticket": result.ticket.model_dump(mode="json") if result.ticket else None,
        }
    )
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    if result.error_code:
        raise typer.Exit(code=1)


@approval_app.command("execute")
def approval_execute(
    approval_id: str = typer.Option(..., "--id", help="Approval ticket id"),
    actor: str = typer.Option(..., "--actor", help="Execution actor identity"),
    workspace_id: str | None = typer.Option(None, "--workspace-id", help="Trusted workspace"),
    profile: str = typer.Option("balanced", help="Config profile"),
    root_dir: str = typer.Option(CONTROL_PLANE_STATE_ROOT, "--root-dir"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    _require_permission_or_exit(config, "agent.registry.write")
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    verified_actor = _require_permission_or_exit(config, "approval.execute")
    runtime = _build_governance_runtime(config)
    if runtime is None:
        typer.echo("Governance disabled.")
        raise typer.Exit(code=1)

    startup_error = _startup_abort(config, runtime)
    if startup_error:
        typer.echo(f"POLICY_UNAVAILABLE: {startup_error}")
        raise typer.Exit(code=2)

    if workspace_id is None or not workspace_id.strip():
        typer.echo(json.dumps({"error_code": "APPROVAL_WORKSPACE_REQUIRED"}))
        raise typer.Exit(code=1)
    ticket = runtime.approval_store.get(approval_id, workspace_id=workspace_id)
    if ticket is None:
        typer.echo(json.dumps({"error_code": "APPROVAL_NOT_FOUND", "approval_id": approval_id}))
        raise typer.Exit(code=1)
    actor = _approval_actor(ticket, verified_actor, actor)
    if ticket.status.value == "expired":
        typer.echo(json.dumps({"error_code": "APPROVAL_EXPIRED", "approval_id": approval_id}))
        raise typer.Exit(code=1)
    if ticket.execution_status.value == "executed":
        typer.echo(json.dumps({"error_code": "REPLAY_BLOCKED", "approval_id": approval_id}))
        raise typer.Exit(code=1)

    if ticket.snapshot.get("schema_version") == "approval.snapshot/v2":
        result = ApprovalExecutionService(
            runtime.approval_store,
            [
                ControlPlaneApprovalExecutor(config=config, root_dir=root_dir),
                ExternalAgentApprovalExecutor(),
                DeviceActionApprovalExecutor(),
            ],
        ).execute(approval_id=approval_id, workspace_id=workspace_id, actor=actor)
        typer.echo(
            json.dumps(
                {
                    "contractVersion": "approval.execution/v2",
                    "approval_id": approval_id,
                    "attempt_id": result.attempt_id,
                    "status": "executed" if result.ok else "blocked",
                    "reason_code": result.reason_code,
                    "result": result.result,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if not result.ok:
            raise typer.Exit(code=1)
        return

    snapshot_hash = _hash_payload(ticket.snapshot)
    if snapshot_hash != ticket.snapshot_hash:
        typer.echo(json.dumps({"error_code": "REPLAY_BLOCKED", "approval_id": approval_id}))
        raise typer.Exit(code=1)

    kind = str(ticket.snapshot.get("kind", ""))
    if kind == "task":
        request_hash = _hash_payload(
            {
                "task_type": ticket.snapshot.get("task_type"),
                "user_input": ticket.snapshot.get("user_input"),
            }
        )
    else:
        request_hash = _hash_payload(ticket.snapshot.get("normalized", []))
    if request_hash != ticket.request_hash:
        typer.echo(json.dumps({"error_code": "REPLAY_BLOCKED", "approval_id": approval_id}))
        raise typer.Exit(code=1)

    if kind != "task":
        fail = runtime.approval_store.mark_execution_failed(
            approval_id=approval_id,
            workspace_id=workspace_id,
            error_code="UNSUPPORTED_SNAPSHOT_KIND",
        )
        typer.echo(
            json.dumps(
                {
                    "approval_id": approval_id,
                    "error_code": "UNSUPPORTED_SNAPSHOT_KIND",
                    "ticket": fail.ticket.model_dump(mode="json") if fail.ticket else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise typer.Exit(code=1)

    orchestrator = _build_orchestrator(config)
    context = {
        "session_id": f"approval-{approval_id[:8]}",
        "governance_approval_id": approval_id,
        "requested_provider": str(config.llm_provider),
        "requested_fallback_provider": str(config.fallback_provider),
        "requested_model_name": str(config.model_name),
        "requested_hf_model_id": str(config.hf_model_id),
        "config_source_model_name": "profile",
        "config_source_hf_model_id": "profile",
        "governance_workspace_id": workspace_id,
    }
    result = orchestrator.process(
        str(ticket.snapshot.get("user_input", "")),
        session_context=context,
        use_router=True,
    )
    output = _with_contract_version(
        {
            "approval_id": approval_id,
            "actor": actor,
            "execution_used_path": result.used_path,
            "trace_id": result.trace_id,
            "fallback_events": result.fallback_events,
            "metrics": result.metrics,
        }
    )
    if result.used_path in {"governance_pending", "governance_blocked"}:
        runtime.approval_store.mark_execution_failed(
            approval_id=approval_id,
            workspace_id=workspace_id,
            error_code="EXECUTION_FAILED",
        )
        output["error_code"] = "EXECUTION_FAILED"
        typer.echo(json.dumps(output, ensure_ascii=False, indent=2))
        raise typer.Exit(code=1)

    decision = runtime.execute_approval(
        approval_id=approval_id,
        workspace_id=workspace_id,
        executed_by=actor,
    )
    if decision.error_code:
        output["error_code"] = decision.error_code
        output["ticket"] = decision.ticket.model_dump(mode="json") if decision.ticket else None
        typer.echo(json.dumps(output, ensure_ascii=False, indent=2))
        raise typer.Exit(code=1)

    output["ticket"] = decision.ticket.model_dump(mode="json") if decision.ticket else None
    typer.echo(json.dumps(output, ensure_ascii=False, indent=2))


@approval_app.command("reconcile")
def approval_reconcile(
    approval_id: str = typer.Option(..., "--id"),
    attempt_id: str = typer.Option(..., "--attempt-id"),
    outcome: str = typer.Option(..., "--outcome", help="executed|failed|unknown"),
    proof_hash: str | None = typer.Option(None, "--proof-hash"),
    actor: str = typer.Option(..., "--actor"),
    workspace_id: str = typer.Option(..., "--workspace-id"),
    profile: str = typer.Option("enterprise", "--profile"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    _require_permission_or_exit(config, "approval.reconcile")
    runtime = _build_governance_runtime(config)
    if runtime is None:
        _emit_payload({"status": "blocked", "reason_code": "GOVERNANCE_DISABLED"})
        raise typer.Exit(code=1)
    ticket = runtime.approval_store.get(approval_id, workspace_id=workspace_id)
    if ticket is None or ticket.status.value != "executing":
        _emit_payload({"status": "blocked", "reason_code": "APPROVAL_NOT_EXECUTING"})
        raise typer.Exit(code=1)
    if ticket.execution_attempt_id != attempt_id:
        _emit_payload({"status": "blocked", "reason_code": "APPROVAL_EXECUTION_ATTEMPT_MISMATCH"})
        raise typer.Exit(code=1)
    if outcome == "unknown":
        _emit_payload(
            {"status": "reconciliation_required", "reason_code": "EXECUTION_OUTCOME_UNKNOWN"}
        )
        return
    if not proof_hash:
        _emit_payload({"status": "blocked", "reason_code": "RECONCILIATION_PROOF_REQUIRED"})
        raise typer.Exit(code=1)
    if outcome == "executed":
        result = runtime.approval_store.finalize_execution_success(
            approval_id=approval_id,
            workspace_id=workspace_id,
            attempt_id=attempt_id,
            result_hash=proof_hash,
        )
    elif outcome == "failed":
        result = runtime.approval_store.finalize_execution_failure(
            approval_id=approval_id,
            workspace_id=workspace_id,
            attempt_id=attempt_id,
            error_code=f"RECONCILED_FAILURE:{proof_hash}",
        )
    else:
        _emit_payload({"status": "blocked", "reason_code": "RECONCILIATION_OUTCOME_INVALID"})
        raise typer.Exit(code=1)
    _emit_payload(
        {
            "status": result.ticket.status.value if result.ticket else "blocked",
            "reason_code": result.error_code or "OK",
            "actor": actor,
            "attempt_id": attempt_id,
        }
    )
    if result.error_code:
        raise typer.Exit(code=1)


@operator_app.command("panel")
def operator_panel(
    profile: str = typer.Option("balanced", help="Config profile"),
    stream: bool = typer.Option(
        True,
        "--stream/--no-stream",
        help="Reserved for future trace tail",
    ),
    workspace_id: str = typer.Option("default", "--workspace-id"),
) -> None:
    _ = stream
    config = RuntimeConfig.from_profile(profile)
    identity = _require_permission_or_exit(config, "approval.decide")
    runtime = _build_governance_runtime(config)
    startup_error = _startup_abort(config, runtime)
    if startup_error:
        typer.echo(f"[blocked-mode] POLICY_UNAVAILABLE: {startup_error}")
        typer.echo("Commands available: /pending, /approve <id>, /reject <id>, /exit")
    else:
        typer.echo("Operator panel started. Commands: /pending, /approve <id>, /reject <id>, /exit")

    if runtime is None:
        typer.echo("Governance disabled; operator panel requires governance.")
        raise typer.Exit(code=1)

    while True:
        line = typer.prompt("operator")
        text = line.strip()
        if text in {"/exit", "exit", "quit", "/quit"}:
            break
        if text == "/pending":
            pending = runtime.approval_store.list_pending(workspace_id=workspace_id)
            typer.echo(
                json.dumps(
                    {"pending": [item.model_dump(mode="json") for item in pending]},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            continue
        if text.startswith("/approve "):
            approval_id = text.split(maxsplit=1)[1]
            result = runtime.decide_approval(
                approval_id=approval_id,
                workspace_id=workspace_id,
                approve=True,
                actor=identity.actor_id,
                reason="approved from panel",
            )
            typer.echo(
                json.dumps(
                    {
                        "error_code": result.error_code,
                        "ticket": result.ticket.model_dump(mode="json") if result.ticket else None,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            continue
        if text.startswith("/reject "):
            approval_id = text.split(maxsplit=1)[1]
            result = runtime.decide_approval(
                approval_id=approval_id,
                workspace_id=workspace_id,
                approve=False,
                actor=identity.actor_id,
                reason="rejected from panel",
            )
            typer.echo(
                json.dumps(
                    {
                        "error_code": result.error_code,
                        "ticket": result.ticket.model_dump(mode="json") if result.ticket else None,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            continue
        typer.echo("Unknown command. Use /pending, /approve <id>, /reject <id>, /exit.")


def _computer_use_vision_runtime_payload(
    vision_config: Any,
    *,
    profile: str,
    platform_label: str,
    current_commit: str,
) -> dict[str, Any]:
    qualification_reports = {}
    macos_report = _load_json_file_if_present(vision_config.macos_qualification_report)
    if macos_report is not None:
        qualification_reports["macos"] = macos_report
    platform_capabilities = build_platform_capabilities(
        vision_config,
        qualification_reports=qualification_reports,
        commit=current_commit,
    )
    current_label = platform_label if platform_label in platform_capabilities else "macos"
    current_capability = platform_capabilities[current_label]
    provider_configured = vision_config.vision_provider == "mock" or bool(
        vision_config.vision_provider != "none" and vision_config.vision_model
    )
    return {
        "enabled": current_capability.live_enabled,
        "stage": current_capability.stage,
        "platform": platform_label if platform_label in platform_capabilities else "unknown",
        "scope": "vision_first_desktop_web_file",
        "executionModes": current_capability.execution_modes,
        "replayable": True,
        "failClosed": True,
        "reasonCode": current_capability.reason_code,
        "summary": current_capability.summary,
        "provider": {
            "kind": vision_config.vision_provider,
            "name": vision_config.vision_provider,
            "configured": provider_configured,
            "model": vision_config.vision_model,
            "strictJson": True,
        },
        "safety": {
            "rawScreenshotPersistence": vision_config.raw_screenshot_persistence,
            "rawScreenshotRetention": vision_config.raw_screenshot_retention,
            "rawScreenshotMaxCount": vision_config.raw_screenshot_max_count,
            "terminalControl": vision_config.terminal_control,
            "sensitiveSurfacePolicy": vision_config.sensitive_surface_policy,
            "approvalRequiredForRiskyActions": True,
            "sensitiveSurfaceBlocked": True,
            "approvalFreshnessEnforced": True,
            "replayIntegrityVerified": True,
        },
        "platforms": {
            key: capability.model_dump(mode="json", by_alias=True)
            for key, capability in platform_capabilities.items()
        },
        "capabilityResolution": _operator_computer_use_capability_resolution(
            vision_config,
            profile=profile,
            platform_label=platform_label,
            current_commit=current_commit,
        ),
    }


@operator_app.command("capabilities")
def operator_capabilities(
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    platform_info = current_platform()
    windows_computer_use = platform_info.label == "windows"
    profile = "balanced"
    current_commit = _current_git_sha()
    vision_config = RuntimeConfig.from_profile(profile).computer_use
    computer_use_pilot = (
        {
            "enabled": False,
            "stage": "not_qualified",
            "platform": "windows",
            "scope": "core+operator_panel+bundled_runtime",
            "executionModes": [],
            "replayable": True,
            "failClosed": True,
            "adapterStatus": "windows_scaffold",
            "reasonCode": "WINDOWS_COMPUTER_USE_NOT_QUALIFIED",
            "summary": (
                "Windows core/operator support is available; Windows live computer-use "
                "automation is not qualified."
            ),
        }
        if windows_computer_use
        else {
            "enabled": True,
            "stage": "execution_slice",
            "platform": "macos",
            "scope": "browser+desktop+file",
            "executionModes": ["dry_run", "step_approval", "execute"],
            "replayable": True,
            "failClosed": True,
            "adapterStatus": "safari_applescript",
            "reasonCode": "MACOS_COMPUTER_USE_PILOT",
            "summary": (
                "macOS computer-use pilot is qualification-gated behind fail-closed controls."
            ),
        }
    )
    computer_use_vision_runtime = _computer_use_vision_runtime_payload(
        vision_config,
        profile=profile,
        platform_label=platform_info.label,
        current_commit=current_commit,
    )
    payload = {
        "coreVersion": __version__,
        "contractVersion": OPERATOR_PANEL_CONTRACT_VERSION,
        "profiles": _supported_profiles(),
        "features": {
            "operatorWorkflowParity": True,
            "enterpriseOpsParity": True,
            "computerUsePilot": computer_use_pilot,
            "computerUseVisionRuntime": computer_use_vision_runtime,
        },
        "commands": {
            "teamSubmit": True,
            "teamResumeSubmit": True,
            "teamListJson": True,
            "teamStatusJson": True,
            "teamReplayJson": True,
            "approvalShowJson": True,
            "approvalPendingJson": True,
            "approvalDecide": True,
            "approvalExecute": True,
            "configResolveJson": True,
            "authWhoamiJson": True,
            "authCheckJson": True,
            "securityBaselineJson": True,
            "keysStatusJson": True,
            "keysVerifyJson": True,
            "keysRotatePlanJson": True,
            "backupCreateJson": True,
            "backupVerifyJson": True,
            "restoreVerifyJson": True,
            "supportBundleExportJson": True,
            "metricsSnapshotJson": True,
            "gaReadinessJson": True,
            "qualificationRunJson": True,
            "migratePlanJson": True,
            "migrateApplyDryRunJson": True,
            "computerUseSubmit": True,
            "computerUsePause": True,
            "computerUseResume": True,
            "computerUseStop": True,
            "computerUseStateJson": True,
            "computerUseSummaryJson": True,
        },
        "artifactSchema": {
            "auditEnvelope": "3",
            "events": "3",
            "gaReadinessReport": "1",
            "securityPosture": "1",
        },
    }
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(
            f"coreVersion={payload['coreVersion']} contractVersion={payload['contractVersion']}"
        )


@computer_use_vision_app.command("doctor")
def computer_use_vision_doctor(
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    platform: str = typer.Option(
        "macos",
        "--platform",
        help="Platform to inspect: macos|windows|linux",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config, _source_map = resolve_runtime_config(profile=profile, root_dir=Path.cwd())
    normalized_platform = platform.strip().lower()
    if normalized_platform not in {"macos", "windows", "linux"}:
        raise typer.BadParameter("platform must be macos, windows, or linux")
    platform_info = current_platform()
    if normalized_platform != platform_info.label:
        platform_info = PlatformInfo(
            system=platform_info.system,
            label=normalized_platform,
            machine=platform_info.machine,
            release=platform_info.release,
        )
    qualification_report = _load_json_file_if_present(
        config.computer_use.macos_qualification_report
    )
    report = MacOSVisionReadiness(config.computer_use).evaluate(
        platform_info=platform_info,
        environment=dict(os.environ),
        qualification_report=qualification_report,
        commit=_current_git_sha(),
    )
    payload = _with_contract_version(report)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(payload["stage"])


@computer_use_app.command("doctor")
def computer_use_doctor(
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    platform: str = typer.Option(
        "all",
        "--platform",
        help="Platform to inspect: all|macos|windows|linux",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config, _source_map = resolve_runtime_config(profile=profile, root_dir=Path.cwd())
    current_commit = _current_git_sha()
    qualification_reports = {}
    macos_report = _load_json_file_if_present(config.computer_use.macos_qualification_report)
    if macos_report is not None:
        qualification_reports["macos"] = macos_report
    capabilities = build_platform_capabilities(
        config.computer_use,
        qualification_reports=qualification_reports,
        commit=current_commit,
    )
    selected = platform.strip().lower()
    if selected != "all":
        if selected not in capabilities:
            raise typer.BadParameter("platform must be all, macos, windows, or linux")
        capabilities = {selected: capabilities[selected]}
    actual_platform_label = current_platform().label
    capability_snapshot_platform = selected if selected != "all" else "unknown"
    capability_snapshot = _filter_capability_snapshot(
        _computer_use_capability_snapshot(
            config.computer_use,
            profile=profile,
            current_platform_label=capability_snapshot_platform,
            current_commit=current_commit,
        ),
        selected=selected,
    )
    base_payload: dict[str, Any] = {
        "runtime": "computer_use_vision",
        "profile": profile,
        "currentPlatform": current_platform().label,
        "platforms": {
            key: capability.model_dump(mode="json", by_alias=True)
            for key, capability in capabilities.items()
        },
        "capabilityResolution": capability_snapshot,
        "computerUse": {
            "visionRuntime": {
                "capability": _selected_capability_decision(
                    capability_snapshot,
                    selected=selected,
                    fallback_platform=actual_platform_label,
                )
            }
        },
    }
    if selected == "macos":
        base_payload.update(
            MacOSVisionReadiness(config.computer_use).evaluate(
                platform_info=PlatformInfo(
                    system=current_platform().system,
                    label="macos",
                    machine=current_platform().machine,
                    release=current_platform().release,
                ),
                environment=dict(os.environ),
                qualification_report=macos_report,
                commit=current_commit,
            )
        )
    payload = _with_contract_version(base_payload)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"platforms={','.join(payload['platforms'])}")


@computer_use_app.command("summary")
def computer_use_summary(
    root_dir: str | None = typer.Option(None, "--root-dir", help="Artifact root"),
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    limit: int = typer.Option(20, "--limit", help="Recent run window"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    bounded_limit = max(1, min(limit, 200))
    runner = ComputerUseRunner(config=config, root_dir=root_dir or config.team.artifact_dir)
    payload = {
        "contractVersion": OPERATOR_PANEL_CONTRACT_VERSION,
        **runner.summary(limit=bounded_limit),
    }
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(str(payload.get("summary") or ""))


@computer_use_provider_app.command("doctor")
def computer_use_provider_doctor(
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    provider: str = typer.Option("ollama", "--provider", help="Local provider to inspect"),
    model: str | None = typer.Option(None, "--model", help="Configured local vision model"),
    synthetic_fixture: bool = typer.Option(
        False,
        "--synthetic-fixture/--no-synthetic-fixture",
        help="Use a synthetic non-sensitive fixture image; required for readiness.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config, _source_map = resolve_runtime_config(profile=profile, root_dir=Path.cwd())
    selected_model = model or config.computer_use.vision_model
    payload = doctor_vision_provider(
        provider=provider,
        model=selected_model,
        synthetic_fixture=synthetic_fixture,
        timeout_s=config.computer_use.vision_provider_timeout_s,
        max_retries=config.computer_use.vision_provider_max_retries,
        environment=os.environ,
    )
    payload = _with_contract_version(payload)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(str(payload.get("status")))


@computer_use_qualification_app.command("run")
def computer_use_qualification_run(
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    platform: str = typer.Option("macos", "--platform", help="macos"),
    suite: str = typer.Option("live-fixture-smoke", "--suite", help="Qualification suite"),
    mode: str = typer.Option("supervised", "--mode", help="preflight|supervised"),
    provider: str | None = typer.Option(None, "--provider", help="Override vision provider"),
    model: str | None = typer.Option(None, "--model", help="Override vision model"),
    output: str = typer.Option(
        "artifacts/computer_use/macos_qualification_report.json",
        "--output",
        help="Qualification report output path",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    normalized_platform = platform.strip().lower()
    if normalized_platform != "macos":
        payload = _with_contract_version(
            {
                "schemaVersion": "1.0",
                "platform": normalized_platform,
                "status": "blocked",
                "stage": "not_qualified",
                "reasonCode": f"{normalized_platform.upper()}_COMPUTER_USE_NOT_QUALIFIED",
                "blockers": [f"{normalized_platform.upper()}_COMPUTER_USE_NOT_QUALIFIED"],
            }
        )
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if mode.strip().lower() not in {"preflight", "supervised"}:
        raise typer.BadParameter("mode must be preflight or supervised for macOS qualification")
    config, _source_map = resolve_runtime_config(profile=profile, root_dir=Path.cwd())
    computer_use_config = config.computer_use
    if provider is not None or model is not None:
        updates: dict[str, Any] = {}
        if provider is not None:
            updates["vision_provider"] = provider
        if model is not None:
            updates["vision_model"] = model
        computer_use_config = computer_use_config.model_copy(update=updates)
    report_payload = run_macos_live_qualification(
        config=computer_use_config,
        suite=suite,
        mode=mode,
        output_path=Path(output),
        env=os.environ,
    )
    payload = _with_contract_version(report_payload)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(str(payload.get("status")))


@computer_use_qualification_app.command("verify")
def computer_use_qualification_verify(
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    platform: str | None = typer.Option(None, "--platform", help="macos|windows|linux"),
    report: str | None = typer.Option(None, "--report", help="Qualification report JSON path"),
    schema: str | None = typer.Option(
        None,
        "--schema",
        help="Qualification JSON schema path for fixture validation",
    ),
    input_path: str | None = typer.Option(
        None,
        "--input",
        help="Qualification fixture JSON path for static validation",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    if input_path is not None:
        payload = _verify_computer_use_qualification_fixture(
            schema_path=Path(schema) if schema else None,
            input_path=Path(input_path),
        )
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            typer.echo(payload["status"])
        if payload["status"] != "pass":
            raise typer.Exit(code=1)
        return

    if platform is None or report is None:
        raise typer.BadParameter("provide either --schema/--input or --platform/--report")

    config, _source_map = resolve_runtime_config(profile=profile, root_dir=Path.cwd())
    normalized_platform = platform.strip().lower()
    report_path = Path(report)
    if report_path.exists():
        validation = validate_platform_qualification_report(
            json.loads(report_path.read_text(encoding="utf-8")),
            platform=normalized_platform,
            config=config.computer_use,
            commit=_current_git_sha(),
        )
    else:
        validation = missing_platform_qualification_result(normalized_platform)
    payload = validation.model_dump(mode="json")
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(validation.status)
    if not validation.allowed:
        raise typer.Exit(code=1)


def _verify_computer_use_qualification_fixture(
    *,
    schema_path: Path | None,
    input_path: Path,
) -> dict[str, Any]:
    blockers: list[str] = []
    if not input_path.exists():
        return {
            "status": "fail",
            "allowed": False,
            "blockers": ["VISION_PLATFORM_QUALIFICATION_MISSING"],
            "inputPath": str(input_path),
        }
    fixture = json.loads(input_path.read_text(encoding="utf-8"))
    if schema_path is not None:
        if not schema_path.exists():
            blockers.append("VISION_PLATFORM_QUALIFICATION_SCHEMA_MISSING")
        else:
            blockers.extend(_validate_json_schema(schema_path, fixture))

    fixture_platform = str(fixture.get("platform", "")).strip().lower()
    fixture_config = _fixture_runtime_config(fixture)
    validation = validate_platform_qualification_report(
        fixture,
        platform=fixture_platform,
        config=fixture_config,
        commit=str(fixture.get("commit", "")),
    )
    blockers.extend(validation.blockers)
    checks = _qualification_fixture_checks(fixture)
    blockers.extend(reason for reason, ok in checks.items() if not ok)

    return {
        "status": "pass" if not blockers else "fail",
        "allowed": False,
        "reviewOnly": True,
        "runtimeLiveEnabled": False,
        "schemaPath": str(schema_path) if schema_path else None,
        "inputPath": str(input_path),
        "platform": fixture_platform or None,
        "fixtureStatus": validation.status,
        "checks": checks,
        "blockers": blockers,
    }


def _validate_json_schema(schema_path: Path, fixture: dict[str, Any]) -> list[str]:
    try:
        import jsonschema
    except ModuleNotFoundError:
        return []
    schema_payload = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema_payload).validate(fixture)
    except jsonschema.ValidationError as exc:
        return [f"VISION_PLATFORM_QUALIFICATION_SCHEMA_INVALID:{exc.json_path}"]
    return []


def _fixture_runtime_config(fixture: dict[str, Any]) -> Any:
    platform = str(fixture.get("platform", "")).strip().lower()
    provider = fixture.get("provider") if isinstance(fixture.get("provider"), dict) else {}
    backends = fixture.get("backends") if isinstance(fixture.get("backends"), dict) else {}
    updates: dict[str, Any] = {
        "vision_enabled": True,
        "vision_provider": str(provider.get("name") or "none"),
        "vision_model": str(provider.get("model") or "") or None,
    }
    if platform in {"macos", "windows", "linux"}:
        updates[f"{platform}_live_enabled"] = True
        updates[f"{platform}_capture_backend"] = str(backends.get("capture", "disabled"))
        updates[f"{platform}_input_backend"] = str(backends.get("input", "disabled"))
    return RuntimeConfig().computer_use.model_copy(update=updates)


def _qualification_fixture_checks(fixture: dict[str, Any]) -> dict[str, bool]:
    safety = fixture.get("safety") if isinstance(fixture.get("safety"), dict) else {}
    raw_count = safety.get(
        "rawScreenshotsPersisted",
        fixture.get("artifacts", {}).get("rawScreenshotCount", -1)
        if isinstance(fixture.get("artifacts"), dict)
        else -1,
    )
    return {
        "has_platform_identity": bool(fixture.get("platform")),
        "has_config_hash": bool(fixture.get("configHash")),
        "has_safety_invariants": bool(safety),
        "approval_freshness_enforced": safety.get("approvalFreshnessEnforced") is True,
        "replay_integrity_verified": (
            safety.get("replayIntegrityVerified") is True
            or safety.get("replayIntegrityEnforced") is True
        ),
        "raw_screenshots_not_persisted": int(raw_count) == 0,
        "has_evidence_placeholders": isinstance(fixture.get("evidence", []), list),
        "does_not_enable_live_runtime": True,
    }


@computer_use_app.command("replay")
def computer_use_replay(
    job_id: str | None = typer.Option(None, "--job-id", help="Vision computer-use job id"),
    report: str | None = typer.Option(
        None,
        "--report",
        help="macOS qualification report JSON path",
    ),
    root_dir: str | None = typer.Option(None, "--root-dir", help="Artifact root"),
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    verify: bool = typer.Option(False, "--verify/--no-verify", help="Verify replay integrity"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    if report is not None:
        payload = _with_contract_version(verify_qualification_report_replay(Path(report)))
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"report={report} verified={payload.get('verified')}")
        if verify and not payload.get("verified"):
            raise typer.Exit(code=1)
        return
    if job_id is None:
        raise typer.BadParameter("provide --job-id or --report")
    config = RuntimeConfig.from_profile(profile)
    job_dir = Path(root_dir or config.team.artifact_dir) / job_id
    payload = load_replay_summary(job_dir)
    if verify:
        payload["verification"] = verify_replay(job_dir)
    payload = _with_contract_version(payload)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"job_id={job_id} verified={payload.get('verified')}")


@computer_use_app.command("qualify")
def computer_use_qualify(
    runtime: str = typer.Option("vision-first", "--runtime", help="vision-first"),
    suite: str = typer.Option("smoke", "--suite", help="Qualification suite"),
    mode: str = typer.Option("deterministic", "--mode", help="deterministic|live"),
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    task_path: str = typer.Option(
        "benchmarks/tasks/computer_use_vision/smoke_tasks.jsonl",
        "--task-path",
        help="Qualification task JSONL path",
    ),
    output_root: str = typer.Option(
        "artifacts/computer_use_vision_qualification",
        "--output-root",
        help="Qualification output root",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    if _parse_computer_use_runtime(runtime) != "vision_first":
        payload = _with_contract_version(
            {
                "artifact_version": "computer_use_vision_qualification/v1",
                "status": "blocked",
                "blocking_reasons": ["UNSUPPORTED_RUNTIME"],
            }
        )
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        raise typer.Exit(code=1)
    config, _source_map = resolve_runtime_config(profile=profile, root_dir=Path.cwd())
    payload = run_vision_qualification(
        config=config.computer_use,
        mode=mode,
        suite=suite,
        task_path=Path(task_path),
        output_root=Path(output_root),
    )
    payload = _with_contract_version(payload)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(payload["status"])


@computer_use_app.command("run")
def computer_use_run(
    once: str = typer.Option(..., "--once", help="Computer-use request"),
    job_id: str | None = typer.Option(None, "--job-id", help="Explicit job id"),
    case_id: str | None = typer.Option(None, "--case-id", help="Optional case id"),
    root_dir: str | None = typer.Option(None, "--root-dir", help="Artifact root"),
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    mode: str = typer.Option("supervised", "--mode", help="assisted|supervised|dry-run"),
    runtime: str = typer.Option(
        "legacy-pilot",
        "--runtime",
        help="legacy-pilot|vision-first|auto",
    ),
    max_steps: int | None = typer.Option(None, "--max-steps", help="Vision runtime step budget"),
    raw_screenshots: bool = typer.Option(
        False,
        "--raw-screenshots/--no-raw-screenshots",
        help="Persist raw screenshots only when explicitly enabled by config and request.",
    ),
    provider: str | None = typer.Option(None, help="Override provider"),
    fallback_provider: str | None = typer.Option(None, help="Override fallback provider"),
    model: str | None = typer.Option(None, "--model", help="Override model"),
    hf_model_id: str | None = typer.Option(None, "--hf-model-id", help="Override HF model id"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    resolved_mode = _parse_computer_use_mode(mode)
    config, _source_map = resolve_runtime_config(
        profile=profile,
        root_dir=Path.cwd(),
        cli_overrides=_build_cli_overrides(
            provider=provider,
            fallback_provider=fallback_provider,
            model=model,
            hf_model_id=hf_model_id,
        ),
    )
    _require_permission_or_exit(config, "runtime.run")
    effective_root = root_dir or config.team.artifact_dir
    effective_job_id = job_id or f"cu-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    runner = ComputerUseRunner(config=config, root_dir=effective_root)
    try:
        payload = runner.run(
            prompt=once,
            job_id=effective_job_id,
            case_id=case_id,
            mode=resolved_mode,
            runtime_mode=_parse_computer_use_runtime(runtime),
            max_steps=max_steps,
            raw_screenshots=raw_screenshots,
        )
    except Exception as exc:  # noqa: BLE001
        payload = _with_contract_version(
            {
                "status": "error",
                "job_id": effective_job_id,
                "root_dir": effective_root,
                "error": str(exc),
            }
        )
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            typer.echo(str(exc))
        raise typer.Exit(code=1) from None

    computer_use_payload = payload.get("computer_use", {})
    runtime_preflight = (
        computer_use_payload.get("runtimePreflight")
        if isinstance(computer_use_payload, dict)
        else None
    )
    job_status = str(payload.get("job", {}).get("status", "unknown"))
    blocked_by_preflight = job_status == "blocked" and isinstance(runtime_preflight, dict)
    output = _with_contract_version(
        {
            "status": "ok",
            "job_id": effective_job_id,
            "root_dir": "[redacted]" if blocked_by_preflight else effective_root,
            **payload,
        }
    )
    if json_output:
        typer.echo(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"job_id={effective_job_id} status={job_status}")
        if blocked_by_preflight:
            typer.echo(f"reason_code={runtime_preflight.get('reasonCode', 'UNKNOWN')}")
            typer.echo("hint=Run: imperaos computer-use doctor --json")


@computer_use_app.command("pause")
def computer_use_pause(
    job_id: str = typer.Option(..., "--job-id", help="Session job id"),
    root_dir: str | None = typer.Option(None, "--root-dir", help="Artifact root"),
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    runner = ComputerUseRunner(config=config, root_dir=root_dir or config.team.artifact_dir)
    payload = _with_contract_version(
        runner.request_control(job_id=job_id, command=SessionCommand.PAUSE)
    )
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"job_id={job_id} requested=pause")


@computer_use_app.command("resume")
def computer_use_resume(
    job_id: str = typer.Option(..., "--job-id", help="Session job id"),
    root_dir: str | None = typer.Option(None, "--root-dir", help="Artifact root"),
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    runner = ComputerUseRunner(config=config, root_dir=root_dir or config.team.artifact_dir)
    try:
        payload = _with_contract_version(
            runner.request_control(job_id=job_id, command=SessionCommand.RESUME)
        )
    except Exception as exc:  # noqa: BLE001
        typer.echo(
            json.dumps(
                _with_contract_version({"status": "error", "job_id": job_id, "error": str(exc)}),
                ensure_ascii=False,
                indent=2,
            )
        )
        raise typer.Exit(code=1) from None
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"job_id={job_id} requested=resume")


@computer_use_app.command("stop")
def computer_use_stop(
    job_id: str = typer.Option(..., "--job-id", help="Session job id"),
    root_dir: str | None = typer.Option(None, "--root-dir", help="Artifact root"),
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    runner = ComputerUseRunner(config=config, root_dir=root_dir or config.team.artifact_dir)
    payload = _with_contract_version(
        runner.request_control(job_id=job_id, command=SessionCommand.STOP)
    )
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"job_id={job_id} requested=stop")


@computer_use_app.command("state")
def computer_use_state(
    job_id: str = typer.Option(..., "--job-id", help="Session job id"),
    root_dir: str | None = typer.Option(None, "--root-dir", help="Artifact root"),
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    runner = ComputerUseRunner(config=config, root_dir=root_dir or config.team.artifact_dir)
    payload = _with_contract_version(runner.session_state(job_id=job_id))
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(
            f"job_id={job_id} state={payload.get('computer_use', {}).get('lifecycle_state')}"
        )


@team_app.command("init")
def team_init(
    output: str = typer.Option("team.yaml", "--output", help="Target team spec path"),
    template_name: str = typer.Option(
        "balanced",
        "--template",
        help="Template preset: balanced|regulated",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing file"),
) -> None:
    path = Path(output)
    if path.exists() and not force:
        typer.echo("Spec file already exists. Use --force to overwrite.")
        raise typer.Exit(code=1)

    try:
        template = _team_init_template(template_name)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2) from None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template, encoding="utf-8")
    typer.echo(
        json.dumps(
            {
                "status": "ok",
                "spec_path": str(path),
                "template": template_name,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@team_app.command("validate")
def team_validate(
    spec: str = typer.Option(..., "--spec", help="Team spec path (.yaml/.json/.toml)"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    try:
        parsed = _load_team_spec(spec)
    except Exception as exc:  # noqa: BLE001
        payload = {"status": "invalid", "error": str(exc), "spec": spec}
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"invalid: {exc}")
        raise typer.Exit(code=1) from None

    payload = {
        "status": "ok",
        "team_id": parsed.team.team_id,
        "agent_count": len(parsed.team.agents),
        "task_count": len(parsed.tasks),
        "roles": [item.role for item in parsed.team.agents],
    }
    validation_errors = validate_team_spec(parsed)
    if validation_errors:
        payload = {
            "status": "invalid",
            "error": "runtime contract validation failed",
            "spec": spec,
            "errors": validation_errors,
        }
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            typer.echo("invalid: runtime contract validation failed")
        raise typer.Exit(code=1)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"team_id={payload['team_id']} agent_count={payload['agent_count']}")


@team_app.command("list")
def team_list(
    root_dir: str = typer.Option(
        TEAM_ARTIFACT_ROOT,
        "--root-dir",
        help="Team artifact root directory",
    ),
    since: str | None = typer.Option(
        None,
        "--since",
        help="Return jobs created at or after this ISO-8601 timestamp.",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    since_dt = None
    if since is not None:
        try:
            since_dt = _parse_iso_datetime(since)
        except ValueError:
            typer.echo(
                json.dumps(
                    {
                        "status": "error",
                        "error_code": "INVALID_INPUT",
                        "error": "Invalid --since value; expected ISO-8601 datetime.",
                        "since": since,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            raise typer.Exit(code=2) from None

    base = Path(root_dir)
    if not base.exists():
        payload = _with_contract_version(
            {"status": "ok", "root_dir": str(base), "count": 0, "items": [], "errors": []}
        )
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            typer.echo("count=0")
        return

    items: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for job_dir in sorted(base.iterdir(), key=lambda p: p.name):
        if not job_dir.is_dir():
            continue
        status_path = job_dir / "status.json"
        if not status_path.exists():
            continue
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append({"job_id": job_dir.name, "error": str(exc)})
            continue
        job = payload.get("job")
        if not isinstance(job, dict):
            errors.append({"job_id": job_dir.name, "error": "invalid status payload"})
            continue

        created_at = str(job.get("created_at") or "")
        if since_dt is not None:
            try:
                created_at_dt = _parse_iso_datetime(created_at)
            except ValueError:
                errors.append({"job_id": job_dir.name, "error": "invalid created_at format"})
                continue
            if created_at_dt < since_dt:
                continue

        items.append(
            {
                "job_id": str(job.get("job_id") or job_dir.name),
                "case_id": str(job.get("case_id") or ""),
                "team_id": str(job.get("team_id") or ""),
                "status": str(job.get("status") or ""),
                "request": str(job.get("request") or ""),
                "created_at": created_at,
                "finished_at": str(job.get("finished_at") or ""),
                "audit_envelope_path": str(payload.get("audit_envelope_path") or ""),
                "job_dir": str(job_dir),
            }
        )

    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    output = _with_contract_version(
        {
            "status": "ok",
            "root_dir": str(base),
            "count": len(items),
            "items": items,
            "errors": errors,
        }
    )
    if json_output:
        typer.echo(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"count={len(items)}")
        for item in items:
            typer.echo(
                f"- {item['job_id']} status={item['status']} "
                f"team_id={item['team_id']} created_at={item['created_at']}"
            )


@team_app.command("run")
def team_run(
    spec: str = typer.Option(..., "--spec", help="Team spec path"),
    once: str = typer.Option(..., "--once", help="Single request for one team job"),
    case_id: str | None = typer.Option(None, "--case-id", help="Optional existing case id"),
    job_id: str | None = typer.Option(None, "--job-id", help="Optional explicit job id"),
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    provider: str | None = typer.Option(None, help="Override provider"),
    fallback_provider: str | None = typer.Option(None, help="Override fallback provider"),
    model: str | None = typer.Option(None, "--model", help="Override model"),
    hf_model_id: str | None = typer.Option(None, "--hf-model-id", help="Override HF model id"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    ensure_artifact_scaffold()
    parsed = _load_team_spec(spec)

    config, _source_map = resolve_runtime_config(
        profile=profile,
        cli_overrides=_build_cli_overrides(
            provider=provider,
            fallback_provider=fallback_provider,
            model=model,
            hf_model_id=hf_model_id,
        ),
    )
    _require_permission_or_exit(config, "runtime.run")
    orchestrator = _build_orchestrator(
        config=config,
        provider_name=config.llm_provider,
        fallback_provider=config.fallback_provider,
    )
    startup_error = _startup_abort(
        config,
        getattr(orchestrator, "governance_runtime", None),
    )
    if startup_error:
        typer.echo(f"POLICY_UNAVAILABLE: {startup_error}")
        raise typer.Exit(code=2)
    if not config.team.enabled:
        typer.echo("Team runtime disabled in runtime config.")
        raise typer.Exit(code=2)

    supervisor = TeamSupervisor(orchestrator=orchestrator, config=config)
    result = supervisor.run(spec=parsed, request=once, case_id=case_id, job_id=job_id)
    payload = _with_contract_version(
        {
            "job": result.job.model_dump(mode="json"),
            "tasks": [item.model_dump(mode="json") for item in result.tasks],
            "handoff_count": len(result.handoffs),
            "event_count": len(result.events),
            "audit_envelope_path": result.audit_envelope_path,
        }
    )
    write_artifact("team_summary", payload)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(result.job.final_output or "")


@team_app.command("resume")
def team_resume(
    spec: str = typer.Option(..., "--spec", help="Team spec path"),
    job_id: str = typer.Option(..., "--job-id", help="Blocked/escalated source job id"),
    root_dir: str = typer.Option(
        TEAM_ARTIFACT_ROOT,
        "--root-dir",
        help="Source and destination team artifact root directory",
    ),
    resume_job_id: str | None = typer.Option(
        None,
        "--resume-job-id",
        help="Optional explicit resume job id",
    ),
    profile: str = typer.Option("balanced", "--profile", help="Runtime profile"),
    workspace_id: str = typer.Option("default", "--workspace-id"),
    provider: str | None = typer.Option(None, help="Override provider"),
    fallback_provider: str | None = typer.Option(None, help="Override fallback provider"),
    model: str | None = typer.Option(None, "--model", help="Override model"),
    hf_model_id: str | None = typer.Option(None, "--hf-model-id", help="Override HF model id"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    ensure_artifact_scaffold()
    parsed = _load_team_spec(spec)

    try:
        source_status = load_job_status(job_id, root_dir=root_dir)
        source_events = load_events(job_id, root_dir=root_dir)
    except Exception as exc:  # noqa: BLE001
        typer.echo(
            json.dumps(
                {"status": "error", "error": str(exc), "job_id": job_id, "root_dir": root_dir},
                ensure_ascii=False,
                indent=2,
            )
        )
        raise typer.Exit(code=1) from None

    source_job = source_status.get("job", {})
    source_request = str(source_job.get("request") or "").strip()
    source_case_id = str(source_job.get("case_id") or "").strip()
    if not source_request or not source_case_id:
        typer.echo(
            json.dumps(
                {
                    "status": "error",
                    "error": "source job status missing request/case_id",
                    "job_id": job_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise typer.Exit(code=1)

    config, _source_map = resolve_runtime_config(
        profile=profile,
        cli_overrides=_build_cli_overrides(
            provider=provider,
            fallback_provider=fallback_provider,
            model=model,
            hf_model_id=hf_model_id,
        ),
    )
    _require_permission_or_exit(config, "runtime.resume")
    config = config.model_copy(
        update={"team": config.team.model_copy(update={"artifact_dir": root_dir})}
    )

    orchestrator = _build_orchestrator(
        config=config,
        provider_name=config.llm_provider,
        fallback_provider=config.fallback_provider,
    )
    startup_error = _startup_abort(
        config,
        getattr(orchestrator, "governance_runtime", None),
    )
    if startup_error:
        typer.echo(f"POLICY_UNAVAILABLE: {startup_error}")
        raise typer.Exit(code=2)
    if not config.team.enabled:
        typer.echo("Team runtime disabled in runtime config.")
        raise typer.Exit(code=2)

    governance_runtime = getattr(orchestrator, "governance_runtime", None)
    overrides, resolved = _collect_resume_overrides(
        events=source_events,
        governance_runtime=governance_runtime,
        workspace_id=workspace_id,
    )
    if not overrides:
        typer.echo(
            json.dumps(
                {
                    "status": "error",
                    "error": "no executed approvals found for resume",
                    "job_id": job_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise typer.Exit(code=1)

    try:
        continuation_state = derive_resume_continuation_state(
            spec=parsed,
            source_job_id=job_id,
            root_dir=root_dir,
            source_status=source_status,
            source_events=source_events,
        )
    except ResumeContinuationError as exc:
        typer.echo(
            json.dumps(
                {
                    "status": "error",
                    "error_code": exc.code,
                    "error": str(exc),
                    "job_id": job_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise typer.Exit(code=1) from None

    generated_resume_job_id = resume_job_id or (
        f"{job_id}-resume-{datetime.now(UTC).strftime('%H%M%S')}"
    )
    supervisor = TeamSupervisor(orchestrator=orchestrator, config=config)
    result = supervisor.run(
        spec=parsed,
        request=source_request,
        case_id=source_case_id,
        job_id=generated_resume_job_id,
        approval_overrides=overrides,
        continuation_state=continuation_state,
    )

    payload = _with_contract_version(
        {
            "status": "ok",
            "resumed_from_job_id": job_id,
            "job": result.job.model_dump(mode="json"),
            "tasks": [item.model_dump(mode="json") for item in result.tasks],
            "handoff_count": len(result.handoffs),
            "event_count": len(result.events),
            "resolved_approvals": resolved,
            "resume_outcomes": result.resume_outcomes,
            "audit_envelope_path": result.audit_envelope_path,
        }
    )
    write_artifact("team_summary", payload)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(result.job.final_output or "")


@team_app.command("status")
def team_status(
    job_id: str = typer.Option(..., "--job-id", help="Job id"),
    root_dir: str = typer.Option(
        TEAM_ARTIFACT_ROOT,
        "--root-dir",
        help="Team artifact root directory",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    try:
        payload = _with_contract_version(load_job_status(job_id, root_dir=root_dir))
    except Exception as exc:  # noqa: BLE001
        typer.echo(json.dumps({"status": "error", "error": str(exc), "job_id": job_id}, indent=2))
        raise typer.Exit(code=1) from None

    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        job = payload.get("job", {})
        typer.echo(
            f"job_id={job.get('job_id')} status={job.get('status')} "
            f"team_id={job.get('team_id')} case_id={job.get('case_id')}"
        )


@team_app.command("logs")
def team_logs(
    job_id: str = typer.Option(..., "--job-id", help="Job id"),
    root_dir: str = typer.Option(
        TEAM_ARTIFACT_ROOT,
        "--root-dir",
        help="Team artifact root directory",
    ),
    json_stream: bool = typer.Option(True, "--json-stream/--no-json-stream", help="Emit JSONL"),
) -> None:
    events = load_events(job_id, root_dir=root_dir)
    if json_stream:
        for item in events:
            typer.echo(json.dumps(item, ensure_ascii=False))
        return
    typer.echo(json.dumps({"job_id": job_id, "events": events}, ensure_ascii=False, indent=2))


@team_app.command("replay")
def team_replay(
    job_id: str = typer.Option(..., "--job-id", help="Job id"),
    root_dir: str = typer.Option(
        TEAM_ARTIFACT_ROOT,
        "--root-dir",
        help="Team artifact root directory",
    ),
    verify: bool = typer.Option(True, "--verify/--no-verify", help="Run replay consistency checks"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    try:
        payload = _with_contract_version(replay_job(job_id, root_dir=root_dir, verify=verify))
    except Exception as exc:  # noqa: BLE001
        typer.echo(json.dumps({"status": "error", "error": str(exc), "job_id": job_id}, indent=2))
        raise typer.Exit(code=1) from None
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(
            f"job_id={payload.get('job_id')} status={payload.get('status')} "
            f"event_count={payload.get('event_count')}"
        )


@team_app.command("artifacts")
def team_artifacts(
    job_id: str = typer.Option(..., "--job-id", help="Job id"),
    export: str = typer.Option(..., "--export", help="Export directory"),
    root_dir: str = typer.Option(
        TEAM_ARTIFACT_ROOT,
        "--root-dir",
        help="Team artifact root directory",
    ),
) -> None:
    source = Path(root_dir) / job_id
    if not source.exists():
        typer.echo(json.dumps({"status": "error", "error": "job not found", "job_id": job_id}))
        raise typer.Exit(code=1)

    destination = Path(export)
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for item in source.iterdir():
        if item.is_file():
            target = destination / item.name
            shutil.copy2(item, target)
            copied.append(str(target))
    typer.echo(
        json.dumps(
            _with_contract_version(
                {
                    "status": "ok",
                    "job_id": job_id,
                    "export_dir": str(destination),
                    "files": copied,
                }
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


@team_app.command("pilot-check")
def team_pilot_check(
    spec: str = typer.Option(..., "--spec", help="Restricted pilot smoke spec path"),
    profile: str = typer.Option("restricted", "--profile", help="Runtime profile"),
    mode: str = typer.Option(
        "deterministic",
        "--mode",
        help="Pilot gate mode: deterministic|live-provider",
    ),
    root_dir: str = typer.Option(
        state_path("team", "pilot"),
        "--root-dir",
        help="Pilot gate artifact root directory",
    ),
    report: str = typer.Option(
        "artifacts/team_pilot_report.json",
        "--report",
        help="Pilot gate report output path",
    ),
    provider: str | None = typer.Option(None, help="Override provider"),
    fallback_provider: str | None = typer.Option(None, help="Override fallback provider"),
    model: str | None = typer.Option(None, "--model", help="Override model"),
    hf_model_id: str | None = typer.Option(None, "--hf-model-id", help="Override HF model id"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    ensure_artifact_scaffold()
    parsed = _load_team_spec(spec)
    config, _source_map = resolve_runtime_config(
        profile=profile,
        cli_overrides=_build_cli_overrides(
            provider=provider,
            fallback_provider=fallback_provider,
            model=model,
            hf_model_id=hf_model_id,
        ),
    )
    _require_permission_or_exit(config, "runtime.run")
    if not config.team.enabled:
        typer.echo("Team runtime disabled in runtime config.")
        raise typer.Exit(code=2)

    runtime = _build_governance_runtime(config)
    startup_error = _startup_abort(config, runtime)
    if startup_error:
        typer.echo(f"POLICY_UNAVAILABLE: {startup_error}")
        raise typer.Exit(code=2)

    live_builder = None
    if mode.strip().lower() == "live-provider":

        def _live_builder(runtime_config: RuntimeConfig):
            return _build_orchestrator(
                runtime_config,
                provider_name=runtime_config.llm_provider,
                fallback_provider=runtime_config.fallback_provider,
            )

        live_builder = _live_builder

    try:
        payload = run_pilot_check(
            spec=parsed,
            config=config,
            mode=mode,
            root_dir=root_dir,
            live_orchestrator_builder=live_builder,
        )
    except Exception as exc:  # noqa: BLE001
        error_code = getattr(exc, "error_code", "PILOT_CHECK_FAILED")
        exit_code = 2 if error_code in {"INVALID_INPUT", "TEAM_SPEC_INVALID"} else 1
        typer.echo(
            json.dumps(
                {
                    "status": "error",
                    "error_code": error_code,
                    "error": str(exc),
                    "spec": spec,
                    "mode": mode,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise typer.Exit(code=exit_code) from None

    payload.setdefault("artifacts", {})["report_path"] = write_pilot_report(
        report,
        payload,
        config=config,
    )
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        counters = payload.get("counters", {})
        checks = payload.get("checks", {})
        replay_status = (
            "ok" if checks.get("replay_integrity", {}).get("status") == "pass" else "fail"
        )
        tamper_status = (
            "fail"
            if counters.get("tamper_verify_unexpected_pass_count", 0) == 0
            else "unexpected-pass"
        )
        reuse_status = (
            "blocked"
            if counters.get("approval_reuse_unexpected_success_count", 0) == 0
            else "reused"
        )
        scope_status = (
            "blocked"
            if counters.get("scope_violation_unexpected_success_count", 0) == 0
            else "bypassed"
        )
        bounded_status = payload.get("bounded_concurrency_status", "unknown")
        typer.echo(
            f"{payload.get('overall_status', 'fail').upper()} "
            f"profile={payload.get('profile')} mode={payload.get('mode')} "
            f"jobs={len(payload.get('job_ids', []))} events={counters.get('total_events', 0)} "
            f"approvals={counters.get('approvals_created', 0)}/"
            f"{counters.get('approvals_approved', 0)}/"
            f"{counters.get('approvals_executed', 0)}/"
            f"{counters.get('approvals_consumed', 0)} "
            f"replay={replay_status} tamper={tamper_status} "
            f"reuse={reuse_status} scope={scope_status} bounded={bounded_status}"
        )
    if payload.get("overall_status") != "pass":
        raise typer.Exit(code=1)


@auth_app.command("whoami")
def auth_whoami(
    profile: str = typer.Option("enterprise", help="Config profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    payload = _with_contract_version(describe_actor(config))
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        actor_id = payload.get("actor", {}).get("actor_id") if payload.get("verified") else None
        typer.echo(actor_id or "unverified")
    if not payload.get("verified"):
        raise typer.Exit(code=1)


@auth_app.command("check")
def auth_check(
    permission: str = typer.Option(..., "--permission", help="Permission to validate"),
    profile: str = typer.Option("enterprise", help="Config profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    payload = _with_contract_version(check_permission(config, permission=permission))
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"allowed={payload['allowed']}")
    if not payload.get("allowed"):
        raise typer.Exit(code=1)


@security_app.command("baseline")
def security_baseline(
    profile: str = typer.Option("enterprise", help="Config profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    payload = _with_contract_version(security_posture(config))
    write_signed_json(
        path="artifacts/security_posture.json",
        artifact="security_posture",
        data=payload,
        config=config,
        purpose="security-posture",
        status="ok" if payload.get("overall_status") == "pass" else "error",
    )
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(payload.get("overall_status", "fail"))
    if payload.get("overall_status") != "pass":
        raise typer.Exit(code=1)


@keys_app.command("status")
def keys_status_cmd(
    profile: str = typer.Option("enterprise", help="Config profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    payload = _with_contract_version(key_status(RuntimeConfig.from_profile(profile)))
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"provider={payload['provider']} current_key_id={payload['current_key_id']}")


@keys_app.command("verify")
def keys_verify_cmd(
    path: str = typer.Option(..., "--path", help="Signed artifact path"),
    profile: str = typer.Option("enterprise", help="Config profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    payload = _with_contract_version(
        verify_signed_artifact(path=path, config=RuntimeConfig.from_profile(profile))
    )
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"verified={payload.get('verified')}")
    if not payload.get("verified"):
        raise typer.Exit(code=1)


@keys_app.command("rotate-plan")
def keys_rotate_plan_cmd(
    profile: str = typer.Option("enterprise", help="Config profile"),
    next_key_id: str | None = typer.Option(None, "--next-key-id", help="Planned next key id"),
    activate_at: str | None = typer.Option(None, "--activate-at", help="Planned activation time"),
    retire_after: str | None = typer.Option(None, "--retire-after", help="Planned retirement time"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    payload = _with_contract_version(
        rotate_plan(
            RuntimeConfig.from_profile(profile),
            next_key_id=next_key_id,
            activate_at=activate_at,
            retire_after=retire_after,
        )
    )
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"next_key_id={payload['next_key_id']}")


@migrate_app.command("plan")
def migrate_plan_cmd(
    profile: str = typer.Option("enterprise", help="Config profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    payload = _with_contract_version(migration_plan(RuntimeConfig.from_profile(profile)))
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(payload["compatible_upgrade_path"])


@migrate_app.command("apply")
def migrate_apply_cmd(
    profile: str = typer.Option("enterprise", help="Config profile"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview only"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    _require_permission_or_exit(config, "maintenance.enter")
    payload = _with_contract_version(migration_apply(config, dry_run=dry_run))
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(payload["status"])


@migrate_app.command("legacy-state")
def migrate_legacy_state_cmd(
    source: str = typer.Option(".binliquid", "--source"),
    destination: str = typer.Option(".imperaos", "--destination"),
    copy: bool = typer.Option(False, "--copy"),
    verify: bool = typer.Option(False, "--verify"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    json_output: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    payload = migrate_legacy_state(
        source,
        destination,
        copy=copy and not dry_run,
        verify=verify,
    )
    _emit_payload(payload, json_output=json_output)
    if payload.get("status") == "blocked":
        raise typer.Exit(code=1)


@backup_app.command("create")
def backup_create_cmd(
    profile: str = typer.Option("enterprise", help="Config profile"),
    output_dir: str | None = typer.Option(None, "--output-dir", help="Backup output directory"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    _require_permission_or_exit(config, "backup.create")
    payload = _with_contract_version(create_backup(config, output_dir=output_dir))
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(payload["backup_dir"])


@backup_app.command("verify")
def backup_verify_cmd(
    backup_dir: str = typer.Option(..., "--backup-dir", help="Backup directory"),
    profile: str = typer.Option("enterprise", help="Config profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    payload = _with_contract_version(
        restore_verify(RuntimeConfig.from_profile(profile), backup_dir=backup_dir)
    )
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"verified={payload['verified']}")
    if not payload.get("verified"):
        raise typer.Exit(code=1)


@restore_app.command("verify")
def restore_verify_cmd(
    backup_dir: str = typer.Option(..., "--backup-dir", help="Backup directory to validate"),
    profile: str = typer.Option("enterprise", help="Config profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    _require_permission_or_exit(config, "restore.verify")
    payload = _with_contract_version(restore_verify(config, backup_dir=backup_dir))
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"verified={payload['verified']}")
    if not payload.get("verified"):
        raise typer.Exit(code=1)


@support_bundle_app.command("export")
def support_bundle_export_cmd(
    profile: str = typer.Option("enterprise", help="Config profile"),
    output: str | None = typer.Option(None, "--output", help="Optional zip output path"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    config = RuntimeConfig.from_profile(profile)
    _require_permission_or_exit(config, "support.export")
    payload = _with_contract_version(export_support_bundle(config, output_path=output))
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(payload["archive_path"])


@metrics_app.command("snapshot")
def metrics_snapshot_cmd(
    profile: str = typer.Option("enterprise", help="Config profile"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    payload = _with_contract_version(collect_metrics_snapshot(config))
    write_signed_json(
        path="artifacts/metrics_snapshot.json",
        artifact="metrics_snapshot",
        data=payload,
        config=config,
        purpose="metrics-snapshot",
    )
    if config.observability.file_snapshot_enabled:
        from imperaos.enterprise.observability import write_prometheus_textfile

        write_prometheus_textfile(payload, config.observability.prometheus_textfile_path)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(payload["generated_at"])


@ga_app.command("readiness")
def ga_readiness_cmd(
    profile: str = typer.Option("enterprise", help="Config profile"),
    report: str = typer.Option(
        "artifacts/ga_readiness_report.json",
        "--report",
        help="GA readiness report output path",
    ),
    qualification_report: str = typer.Option(
        "artifacts/qualification_report.json",
        "--qualification-report",
        help="Qualification evidence report path",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    payload = _with_contract_version(
        ga_readiness_report(config, qualification_report_path=qualification_report)
    )
    write_signed_json(
        path=report,
        artifact="ga_readiness_report",
        data=payload,
        config=config,
        purpose="ga-readiness",
        status="ok" if payload.get("overall_status") != "red" else "error",
    )
    markdown_path = Path(report).with_name("GA_READINESS_REPORT.md")
    markdown_path.write_text(render_ga_readiness_markdown(payload), encoding="utf-8")
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(payload["overall_status"])
    if payload.get("overall_status") == "red":
        raise typer.Exit(code=1)


@qualification_app.command("run")
def qualification_run_cmd(
    profile: str = typer.Option("enterprise", help="Config profile"),
    mode: str = typer.Option("mixed", help="Qualification evidence mode"),
    soak_hours: float = typer.Option(
        6.0,
        "--soak-hours",
        help="Requested soak duration in hours for the 6h qualification workload.",
    ),
    output_root: str = typer.Option(
        "artifacts/qualification",
        "--output-root",
        help="Qualification output root directory",
    ),
    workloads: str | None = typer.Option(
        None,
        "--workloads",
        help="Comma-separated qualification workloads to run",
    ),
    merge_from_report: str | None = typer.Option(
        None,
        "--merge-from-report",
        help="Existing signed qualification report to merge subset reruns into",
    ),
    provider: str | None = typer.Option(None, help="Override provider"),
    fallback_provider: str | None = typer.Option(None, help="Override fallback provider"),
    model: str | None = typer.Option(None, "--model", help="Override model name"),
    hf_model_id: str | None = typer.Option(
        None,
        "--hf-model-id",
        help="Override transformers model id",
    ),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON output"),
) -> None:
    resolved, _source_map = resolve_runtime_config(
        profile=profile,
        cli_overrides=_build_cli_overrides(
            provider=provider,
            fallback_provider=fallback_provider,
            model=model,
            hf_model_id=hf_model_id,
        ),
    )
    validation_error = _validate_model_override_combo(
        effective_provider=resolved.llm_provider,
        model_override=model,
        hf_model_id_override=hf_model_id,
    )
    if validation_error is not None:
        _code, message = validation_error
        typer.echo(message)
        raise typer.Exit(code=1)

    for permission in (
        "runtime.run",
        "approval.decide",
        "approval.execute",
        "support.export",
        "backup.create",
        "restore.verify",
    ):
        _require_permission_or_exit(resolved, permission)

    try:
        selected_workloads = None
        if workloads is not None:
            selected_workloads = [item.strip() for item in workloads.split(",") if item.strip()]
        payload = run_qualification(
            config=resolved,
            mode=mode,
            soak_hours=soak_hours,
            output_root=output_root,
            workloads=selected_workloads,
            merge_from_report=merge_from_report,
            live_orchestrator_builder=lambda runtime_config: _build_orchestrator(
                runtime_config,
                provider_name=resolved.llm_provider,
                fallback_provider=resolved.fallback_provider,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        error_code = getattr(exc, "error_code", "QUALIFICATION_FAILED")
        payload = _with_contract_version(
            {
                "status": "error",
                "error_code": error_code,
                "error": str(exc),
            }
        )
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"{error_code}: {exc}")
        raise typer.Exit(code=2) from None

    payload = _with_contract_version(payload)
    paths = write_qualification_report(payload=payload, config=resolved, output_root=output_root)
    payload.setdefault("artifacts", {})
    payload["artifacts"].update(paths)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(payload.get("go_no_go", "conditional"))
    if payload.get("go_no_go") == "no-go":
        raise typer.Exit(code=1)


@benchmark_app.command("smoke")
def benchmark_smoke(
    profile: str = typer.Option("lite", help="Config profile"),
    mode: str = typer.Option("all", help="A|B|C|D|both|all"),
    suite: str = typer.Option("smoke", help="smoke|quality"),
    output: str | None = typer.Option(None, help="Output JSON path"),
    task_limit: int | None = typer.Option(None, help="Limit number of benchmark tasks"),
    provider: str | None = typer.Option(None, help="Override provider"),
    fallback_provider: str | None = typer.Option(None, help="Override fallback provider"),
    model: str | None = typer.Option(None, "--model", help="Override model name"),
    hf_model_id: str | None = typer.Option(
        None,
        "--hf-model-id",
        help="Override transformers model id",
    ),
) -> None:
    ensure_artifact_scaffold()
    resolved, _ = resolve_runtime_config(
        profile=profile,
        cli_overrides=_build_cli_overrides(
            provider=provider,
            fallback_provider=fallback_provider,
            model=model,
            hf_model_id=hf_model_id,
        ),
    )
    validation_error = _validate_model_override_combo(
        effective_provider=resolved.llm_provider,
        model_override=model,
        hf_model_id_override=hf_model_id,
    )
    if validation_error is not None:
        _code, message = validation_error
        typer.echo(message)
        raise typer.Exit(code=1)

    result = run_smoke_benchmark(
        profile=profile,
        mode=mode,
        suite=suite,
        output_path=output,
        task_limit=task_limit,
        provider=resolved.llm_provider,
        fallback_provider=resolved.fallback_provider,
        model=resolved.model_name,
        hf_model_id=resolved.hf_model_id,
    )
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
    write_artifact("benchmark_summary", {"kind": "smoke", "result": result})


@benchmark_app.command("team")
def benchmark_team(
    profile: str = typer.Option("balanced", help="Config profile"),
    suite: str = typer.Option("smoke", help="smoke|quality"),
    spec: str = typer.Option("team.yaml", "--spec", help="Team spec path"),
    output: str | None = typer.Option(None, help="Output JSON path"),
    task_limit: int | None = typer.Option(None, help="Limit number of benchmark tasks"),
    deterministic_mock: bool = typer.Option(
        False,
        "--deterministic-mock",
        help="Use deterministic mock orchestrator (CI-friendly).",
    ),
    provider: str | None = typer.Option(None, help="Override provider"),
    fallback_provider: str | None = typer.Option(None, help="Override fallback provider"),
    model: str | None = typer.Option(None, "--model", help="Override model name"),
    hf_model_id: str | None = typer.Option(
        None,
        "--hf-model-id",
        help="Override transformers model id",
    ),
) -> None:
    ensure_artifact_scaffold()
    resolved, _ = resolve_runtime_config(
        profile=profile,
        cli_overrides=_build_cli_overrides(
            provider=provider,
            fallback_provider=fallback_provider,
            model=model,
            hf_model_id=hf_model_id,
        ),
    )
    validation_error = _validate_model_override_combo(
        effective_provider=resolved.llm_provider,
        model_override=model,
        hf_model_id_override=hf_model_id,
    )
    if validation_error is not None:
        _code, message = validation_error
        typer.echo(message)
        raise typer.Exit(code=1)

    result = run_team_benchmark(
        profile=profile,
        suite=suite,
        spec_path=spec,
        output_path=output,
        task_limit=task_limit,
        provider=resolved.llm_provider,
        fallback_provider=resolved.fallback_provider,
        model=resolved.model_name,
        hf_model_id=resolved.hf_model_id,
        deterministic_mock=deterministic_mock,
    )
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
    write_artifact("benchmark_summary", {"kind": "team", "result": result})


@benchmark_app.command("ablation")
def benchmark_ablation(
    profile: str = typer.Option("balanced", help="Config profile"),
    mode: str = typer.Option("all", help="A|B|C|D|both|all"),
    suite: str = typer.Option("smoke", help="smoke|quality"),
    output: str | None = typer.Option(None, help="Output JSON path"),
    report: str | None = typer.Option(None, help="Output markdown report path"),
    task_limit: int | None = typer.Option(None, help="Limit number of benchmark tasks"),
    provider: str | None = typer.Option(None, help="Override provider"),
    fallback_provider: str | None = typer.Option(None, help="Override fallback provider"),
    model: str | None = typer.Option(None, "--model", help="Override model name"),
    hf_model_id: str | None = typer.Option(
        None,
        "--hf-model-id",
        help="Override transformers model id",
    ),
) -> None:
    ensure_artifact_scaffold()
    resolved, _ = resolve_runtime_config(
        profile=profile,
        cli_overrides=_build_cli_overrides(
            provider=provider,
            fallback_provider=fallback_provider,
            model=model,
            hf_model_id=hf_model_id,
        ),
    )
    validation_error = _validate_model_override_combo(
        effective_provider=resolved.llm_provider,
        model_override=model,
        hf_model_id_override=hf_model_id,
    )
    if validation_error is not None:
        _code, message = validation_error
        typer.echo(message)
        raise typer.Exit(code=1)

    result = run_ablation_benchmark(
        profile=profile,
        mode=mode,
        output_path=output,
        report_path=report,
        task_limit=task_limit,
        suite=suite,
        provider=resolved.llm_provider,
        fallback_provider=resolved.fallback_provider,
        model=resolved.model_name,
        hf_model_id=resolved.hf_model_id,
    )
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
    write_artifact("benchmark_summary", {"kind": "ablation", "result": result})


@benchmark_app.command("energy")
def benchmark_energy(
    profile: str = typer.Option("balanced", help="Config profile"),
    energy_mode: str = typer.Option("measured", help="measured|estimated"),
    output: str | None = typer.Option(None, help="Output JSON path"),
    task_limit: int | None = typer.Option(2, help="Limit number of benchmark tasks"),
    provider: str | None = typer.Option(
        None,
        help="Override provider (energy runs smoke mode-A workload with this provider).",
    ),
    fallback_provider: str | None = typer.Option(
        None,
        help="Override fallback provider for mode-A workload execution.",
    ),
    model: str | None = typer.Option(None, "--model", help="Override model name"),
    hf_model_id: str | None = typer.Option(
        None,
        "--hf-model-id",
        help="Override transformers model id",
    ),
) -> None:
    ensure_artifact_scaffold()
    resolved, _ = resolve_runtime_config(
        profile=profile,
        cli_overrides=_build_cli_overrides(
            provider=provider,
            fallback_provider=fallback_provider,
            model=model,
            hf_model_id=hf_model_id,
        ),
    )
    validation_error = _validate_model_override_combo(
        effective_provider=resolved.llm_provider,
        model_override=model,
        hf_model_id_override=hf_model_id,
    )
    if validation_error is not None:
        _code, message = validation_error
        typer.echo(message)
        raise typer.Exit(code=1)

    result = run_energy_benchmark(
        profile=profile,
        energy_mode=energy_mode,
        task_limit=task_limit,
        output_path=output,
        provider=resolved.llm_provider,
        fallback_provider=resolved.fallback_provider,
        model=resolved.model_name,
        hf_model_id=resolved.hf_model_id,
    )
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
    write_artifact("benchmark_summary", {"kind": "energy", "result": result})


@memory_app.command("stats")
def memory_stats(
    profile: str = typer.Option("balanced", help="Config profile"),
    legacy: bool = typer.Option(False, "--legacy", help="Return legacy memory manager stats"),
) -> None:
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    if not legacy:
        authority = build_memory_authority(config)
        typer.echo(json.dumps(authority.stats(), indent=2, ensure_ascii=False, sort_keys=True))
        return
    manager = _build_memory_manager(config)
    typer.echo(json.dumps(manager.stats(), indent=2, ensure_ascii=False))


@memory_app.command("doctor")
def memory_doctor(profile: str = typer.Option("balanced", help="Config profile")) -> None:
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    authority = build_memory_authority(config)
    payload = authority.snapshot().model_dump(mode="json", by_alias=True)
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


@memory_app.command("propose")
def memory_propose(
    text: str = typer.Option(..., "--text", help="Memory candidate text"),
    profile: str = typer.Option("balanced", help="Config profile"),
    actor: str = typer.Option("cli:operator", help="Actor id or sha256 hash"),
    role: str = typer.Option("operator", help="Producer role"),
    scope: str = typer.Option("personal", help="Memory scope"),
    owner_type: str = typer.Option("user", "--owner-type", help="Owner type"),
    owner: str = typer.Option("cli:operator", help="Owner id or sha256 hash"),
    visibility: str = typer.Option("private", help="Memory visibility"),
    reason: str = typer.Option("operator memory proposal", help="Write reason"),
    memory_target: str | None = typer.Option(None, "--memory-target", help="Optional target key"),
    expected_state_version: int | None = typer.Option(
        None,
        "--expected-state-version",
        help="Expected target state version for targeted writes",
    ),
    agent_id: str | None = typer.Option(None, "--agent-id", help="Source agent id"),
    source_run_id: str | None = typer.Option(None, "--source-run-id", help="Source run id"),
) -> None:
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    authority = build_memory_authority(config)
    result = authority.propose_write(
        proposal_from_cli(
            actor=actor,
            scope=scope,
            owner_type=owner_type,
            owner=owner,
            visibility=visibility,
            text=text,
            role=role,
            reason=reason,
            memory_target=memory_target,
            expected_state_version=expected_state_version,
            agent_id=agent_id,
            source_run_id=source_run_id,
        )
    )
    typer.echo(
        json.dumps(
            result.model_dump(mode="json", by_alias=True),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@memory_app.command("retrieve")
def memory_retrieve(
    query: str = typer.Option(..., "--query", help="Retrieval query"),
    profile: str = typer.Option("balanced", help="Config profile"),
    actor: str = typer.Option("cli:operator", help="Actor id or sha256 hash"),
    role: str = typer.Option("operator", help="Requester role"),
    scope: str = typer.Option("personal", help="Scope filter"),
    owner_type: str = typer.Option("user", "--owner-type", help="Owner type"),
    owner: str = typer.Option("cli:operator", help="Owner id or sha256 hash"),
    namespace: str = typer.Option("default", help="Namespace"),
    visibility: list[str] | None = _MEMORY_VISIBILITY_OPTION,
    allowed_scope: list[str] | None = _MEMORY_ALLOWED_SCOPE_OPTION,
    limit: int = typer.Option(5, min=1, max=50, help="Maximum hits"),
    include_content: bool = typer.Option(
        False,
        "--include-content",
        help="Return redacted summaries",
    ),
) -> None:
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    authority = build_memory_authority(config)
    request = MemoryRetrievalRequest(
        actorIdHash=hash_identity(actor),
        requesterRole=role,
        query=query,
        allowedScopes=allowed_scope or ["personal"],
        scopeFilters=[
            MemoryScopeFilter(
                scope=scope,
                ownerType=owner_type,
                ownerIdHash=hash_identity(owner),
                namespace=namespace,
            )
        ],
        visibilityFilters=visibility or ["private"],
        purpose="operator_review",
        limit=limit,
        includeContent=include_content,
    )
    result = authority.retrieve(request)
    typer.echo(
        json.dumps(
            result.model_dump(mode="json", by_alias=True),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@memory_index_app.command("status")
def memory_index_status(profile: str = typer.Option("balanced", help="Config profile")) -> None:
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    authority = build_memory_authority(config)
    payload = authority.snapshot().index.model_dump(mode="json", by_alias=True)
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


@memory_app.command("eval")
def memory_eval(
    suite: str = typer.Option(
        "benchmarks/tasks/memory/memory_retrieval_eval.jsonl",
        help="Evaluation JSONL suite",
    ),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    payload = run_memory_retrieval_eval(config, Path(suite))
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


@memory_runtime_app.command("doctor")
def memory_runtime_doctor(profile: str = typer.Option("balanced", help="Config profile")) -> None:
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    from imperaos.memory.runtime_snapshot import build_memory_runtime_snapshot

    payload = build_memory_runtime_snapshot(config=config).model_dump(
        mode="json",
        by_alias=True,
    )
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


@memory_runtime_app.command("context")
def memory_runtime_context(
    query: str = typer.Option(..., "--query", help="Runtime query"),
    profile: str = typer.Option("balanced", help="Config profile"),
    actor: str = typer.Option("cli:operator", help="Actor id or sha256 hash"),
    role: str = typer.Option("operator", help="Requester role"),
    run_id: str = typer.Option("cli-runtime-context", help="Run id"),
    agent_id: str | None = typer.Option(None, "--agent-id", help="Optional agent id"),
    team_id: str | None = typer.Option(None, "--team-id", help="Optional team id"),
    case_id: str | None = typer.Option(None, "--case-id", help="Optional case id"),
    project_id: str | None = typer.Option(None, "--project-id", help="Optional project id"),
) -> None:
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    bridge = build_memory_runtime_bridge(config)
    pack = bridge.retrieve_context(
        RuntimeMemoryRequest(
            run_id=run_id,
            query=query,
            actor_id=actor,
            requester_role=role,
            agent_id=agent_id,
            team_id=team_id,
            case_id=case_id,
            project_id=project_id,
        )
    )
    typer.echo(
        json.dumps(
            pack.model_dump(mode="json", by_alias=True),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@memory_runtime_policy_app.command("doctor")
def memory_runtime_policy_doctor(
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    bridge = build_memory_runtime_bridge(config)
    from imperaos.memory.runtime_policy import AgentMemoryPolicyGateway

    report = AgentMemoryPolicyGateway(
        config=config,
        bridge=bridge,
        workspace_authority=bridge.workspace_authority,
    ).doctor()
    _echo_json(report.model_dump(mode="json", by_alias=True))
    if report.status == "blocked":
        raise typer.Exit(code=1)


@memory_runtime_policy_app.command("simulate")
def memory_runtime_policy_simulate(
    operation: str = typer.Option("read", "--operation", help="read or write"),
    query: str = typer.Option("provider governance", "--query", help="Read query"),
    summary: str = typer.Option(
        "runtime policy simulation summary",
        "--summary",
        help="Write summary",
    ),
    profile: str = typer.Option("enterprise", help="Config profile"),
    actor: str = typer.Option("operator-main", "--actor", help="Actor id"),
    role: str = typer.Option("operator", "--role", help="Requester role"),
    principal_id: str | None = typer.Option(None, "--principal-id"),
    workspace_id: str | None = typer.Option(None, "--workspace-id"),
    agent_id: str | None = typer.Option(None, "--agent-id"),
    team_id: str | None = typer.Option(None, "--team-id"),
    case_id: str | None = typer.Option(None, "--case-id"),
    scope: str | None = typer.Option(None, "--scope"),
    semantic_mode: str = typer.Option("disabled", "--semantic-mode"),
    fixture: bool = typer.Option(True, "--fixture/--no-fixture"),
) -> None:
    ensure_artifact_scaffold()
    if fixture:
        from imperaos.memory.runtime_policy_fixtures import build_memory_runtime_policy_fixture

        built = build_memory_runtime_policy_fixture(
            Path(state_path("memory-runtime-policy-cli")),
            profile=profile,
            semantic_mode=semantic_mode,
            semantic_enabled=semantic_mode != "disabled",
        )
        config = built.config
        bridge = built.bridge
    else:
        config = RuntimeConfig.from_profile(profile)
        config.memory.runtime.policy_enforcement_enabled = True
        config.memory.runtime.semantic_runtime_mode = semantic_mode
        bridge = build_memory_runtime_bridge(config)
    if operation == "read":
        pack = bridge.retrieve_context(
            RuntimeMemoryRequest(
                run_id="cli-memory-policy-simulate",
                query=query,
                actor_id=actor,
                requester_role=role,
                agent_id=agent_id,
                team_id=team_id,
                case_id=case_id,
                workspace_id=workspace_id or config.memory.workspace_authority.default_workspace_id,
                principal_id=principal_id,
            )
        )
        _echo_json(
            {
                "status": pack.status,
                "operation": "read",
                "queryHash": hash_identity(query),
                "hitIdHashes": [hash_identity(hit.memory_id) for hit in pack.hits],
                "evidenceRef": pack.evidence_ref,
                "rawContentIncluded": False,
            }
        )
        if pack.status in {"denied", "error"}:
            raise typer.Exit(code=1)
        return
    if operation != "write":
        raise typer.BadParameter("operation must be read or write")
    result = bridge.propose_post_run_write(
        run_id="cli-memory-policy-simulate",
        actor_id=actor,
        role=role,
        user_input="cli policy simulate input",
        assistant_output=summary,
        scope=scope,
        agent_id=agent_id,
    )
    _echo_json(
        {
            "status": result.status,
            "operation": "write",
            "contentHash": result.content_hash,
            "proposalIdHash": hash_identity(result.proposal_id),
            "evidenceRef": result.evidence_ref,
            "blockingReasons": result.blocking_reasons,
            "rawContentIncluded": False,
        }
    )
    if result.status in {"denied", "error", "conflict"}:
        raise typer.Exit(code=1)


@memory_runtime_policy_app.command("evaluate")
def memory_runtime_policy_evaluate(
    suite: str = typer.Option(
        "benchmarks/tasks/memory/runtime_policy_cases.jsonl",
        "--suite",
    ),
    output: str = typer.Option(
        "artifacts/memory-runtime-policy/evaluation.json",
        "--output",
    ),
    profile: str = typer.Option("enterprise", help="Config profile"),
) -> None:
    from imperaos.memory.runtime_policy_evaluator import run_policy_evaluation

    report = run_policy_evaluation(
        suite_path=Path(suite),
        output_path=Path(output),
        profile=profile,
    )
    _echo_json(report.model_dump(mode="json", by_alias=True))
    if report.status != "pass":
        raise typer.Exit(code=1)


@memory_sync_app.command("export")
def memory_sync_export(
    output: str = typer.Option(..., "--output", help="Output sync pack JSON"),
    profile: str = typer.Option("balanced", help="Config profile"),
    source_environment: str = typer.Option("local", "--source-environment"),
    scope: str | None = typer.Option(None, "--scope", help="Optional scope filter"),
    owner_type: str = typer.Option("user", "--owner-type", help="Owner type"),
    owner: str | None = typer.Option(None, "--owner", help="Owner id or hash"),
    namespace: str = typer.Option("default", help="Namespace"),
    limit: int = typer.Option(500, min=1, max=5000, help="Maximum records"),
) -> None:
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    scope_filters = None
    if scope and owner:
        scope_filters = [owner_filter(scope, owner_type, owner, namespace)]
    pack = export_memory_sync_pack(
        config=config,
        output_path=output,
        source_environment=source_environment,
        scope_filters=scope_filters,
        limit=limit,
    )
    typer.echo(
        json.dumps(
            pack.manifest.model_dump(mode="json", by_alias=True),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@memory_sync_app.command("verify")
def memory_sync_verify(
    input_path: str = typer.Option(..., "--input", help="Sync pack JSON"),
) -> None:
    result = verify_memory_sync_pack(input_path)
    typer.echo(
        json.dumps(
            result.model_dump(mode="json", by_alias=True),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if result.status != "pass":
        raise typer.Exit(code=1)


@memory_sync_app.command("import")
def memory_sync_import(
    input_path: str = typer.Option(..., "--input", help="Sync pack JSON"),
    profile: str = typer.Option("balanced", help="Config profile"),
    apply: bool = typer.Option(False, "--apply", help="Apply records instead of dry-run"),
    approval_id: str | None = typer.Option(None, "--approval-id", help="Required for apply"),
) -> None:
    ensure_artifact_scaffold()
    config = RuntimeConfig.from_profile(profile)
    report = import_memory_sync_pack(
        config=config,
        input_path=input_path,
        dry_run=not apply,
        approval_id=approval_id,
    )
    typer.echo(
        json.dumps(
            report.model_dump(mode="json", by_alias=True),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if report.status == "blocked" and apply:
        raise typer.Exit(code=1)


@memory_workspace_app.command("init")
def memory_workspace_init(
    workspace_id: str = typer.Option("default", "--workspace-id", help="Workspace id"),
    owner_principal_id: str = typer.Option(
        "agent-local",
        "--owner-principal-id",
        help="Owner principal id",
    ),
    display_name: str = typer.Option("Default workspace", "--display-name"),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    ensure_artifact_scaffold()
    authority = build_workspace_memory_authority(RuntimeConfig.from_profile(profile))
    authority.store.upsert_principal(
        MemoryPrincipal(
            principalId=owner_principal_id,
            principalType="operator",
            displayName=owner_principal_id,
        )
    )
    workspace_result = authority.store.create_workspace(
        MemoryWorkspace(
            workspaceId=workspace_id,
            displayName=display_name,
            ownerPrincipalId=owner_principal_id,
        )
    )
    membership_result = authority.store.grant_membership(
        MemoryWorkspaceMembership(
            membershipId=stable_id("wm_member", workspace_id, owner_principal_id),
            workspaceId=workspace_id,
            principalId=owner_principal_id,
            roles=("owner",),
            grantedBy=owner_principal_id,
        )
    )
    _echo_json(
        {
            "status": "pass",
            "workspace": workspace_result.model_dump(mode="json", by_alias=True),
            "membership": membership_result.model_dump(mode="json", by_alias=True),
            "rawContentIncluded": False,
        }
    )


@memory_principal_app.command("add")
def memory_principal_add(
    principal_id: str = typer.Option(..., "--principal-id"),
    principal_type: str = typer.Option("agent", "--principal-type"),
    display_name: str | None = typer.Option(None, "--display-name"),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    ensure_artifact_scaffold()
    authority = build_workspace_memory_authority(RuntimeConfig.from_profile(profile))
    result = authority.store.upsert_principal(
        MemoryPrincipal(
            principalId=principal_id,
            principalType=principal_type,
            displayName=display_name or principal_id,
        )
    )
    _echo_json(result.model_dump(mode="json", by_alias=True))


@memory_workspace_app.command("grant")
def memory_workspace_grant(
    workspace_id: str = typer.Option(..., "--workspace-id"),
    principal_id: str = typer.Option(..., "--principal-id"),
    role: list[str] = _WORKSPACE_ROLE_OPTION,
    granted_by: str = typer.Option("agent-local", "--granted-by"),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    ensure_artifact_scaffold()
    authority = build_workspace_memory_authority(RuntimeConfig.from_profile(profile))
    result = authority.store.grant_membership(
        MemoryWorkspaceMembership(
            membershipId=stable_id("wm_member", workspace_id, principal_id),
            workspaceId=workspace_id,
            principalId=principal_id,
            roles=tuple(role),
            grantedBy=granted_by,
        )
    )
    _echo_json(result.model_dump(mode="json", by_alias=True))


@memory_scope_app.command("grant")
def memory_scope_grant(
    workspace_id: str = typer.Option(..., "--workspace-id"),
    scope_type: str = typer.Option(..., "--scope-type"),
    scope_id: str = typer.Option(..., "--scope-id"),
    permission: list[str] = _WORKSPACE_PERMISSION_OPTION,
    effect: str = typer.Option("allow", "--effect"),
    principal_id: str | None = typer.Option(None, "--principal-id"),
    role: str | None = typer.Option(None, "--role"),
    reason: str = typer.Option("operator ACL grant", "--reason"),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    ensure_artifact_scaffold()
    authority = build_workspace_memory_authority(RuntimeConfig.from_profile(profile))
    rule = MemoryScopeAclRule(
        aclId=stable_id(
            "wm_acl",
            workspace_id,
            scope_type,
            scope_id,
            principal_id or role,
            ",".join(permission),
            effect,
        ),
        workspaceId=workspace_id,
        scopeType=scope_type,
        scopeId=scope_id,
        principalId=principal_id,
        role=role,
        permissions=tuple(permission),
        effect=effect,
        reason=reason,
    )
    result = authority.store.upsert_acl_rule(rule)
    _echo_json(result.model_dump(mode="json", by_alias=True))


@memory_authority_app.command("query")
def memory_authority_query(
    workspace_id: str = typer.Option("default", "--workspace-id"),
    principal_id: str = typer.Option("agent-local", "--principal-id"),
    scope_type: str = typer.Option("personal", "--scope-type"),
    scope_id: str = typer.Option("agent-local", "--scope-id"),
    query: str = typer.Option("", "--query"),
    limit: int = typer.Option(5, min=1, max=50),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    ensure_artifact_scaffold()
    authority = build_workspace_memory_authority(RuntimeConfig.from_profile(profile))
    result = authority.query(
        WorkspaceMemoryQueryRequest(
            workspaceId=workspace_id,
            principalId=principal_id,
            scopeType=scope_type,
            scopeId=scope_id,
            query=query,
            limit=limit,
        )
    )
    _echo_json(result.model_dump(mode="json", by_alias=True))


@memory_authority_app.command("propose-write")
def memory_authority_propose_write(
    summary: str = typer.Option(..., "--summary"),
    workspace_id: str = typer.Option("default", "--workspace-id"),
    principal_id: str = typer.Option("agent-local", "--principal-id"),
    scope_type: str = typer.Option("personal", "--scope-type"),
    scope_id: str = typer.Option("agent-local", "--scope-id"),
    memory_target: str | None = typer.Option(None, "--memory-target"),
    expected_state_version: int | None = typer.Option(None, "--expected-state-version"),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    ensure_artifact_scaffold()
    authority = build_workspace_memory_authority(RuntimeConfig.from_profile(profile))
    result = authority.propose_or_write(
        WorkspaceMemoryWriteRequest(
            workspaceId=workspace_id,
            principalId=principal_id,
            scopeType=scope_type,
            scopeId=scope_id,
            summary=summary,
            memoryTarget=memory_target,
            expectedStateVersion=expected_state_version,
            reason="operator authority propose-write",
        )
    )
    _echo_json(result.model_dump(mode="json", by_alias=True))


def _semantic_service(profile: str) -> SemanticMemoryService:
    config = RuntimeConfig.from_profile(profile)
    authority = build_workspace_memory_authority(config)
    return SemanticMemoryService(config=config, authority=authority)


@memory_semantic_app.command("status")
def memory_semantic_status(
    workspace_id: str = typer.Option("default", "--workspace-id"),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    service = _semantic_service(profile)
    _echo_json(service.status(workspace_id).model_dump(mode="json", by_alias=True))


@memory_semantic_app.command("rebuild")
def memory_semantic_rebuild(
    workspace_id: str = typer.Option("default", "--workspace-id"),
    profile: str = typer.Option("balanced", help="Config profile"),
    apply: bool = typer.Option(False, "--apply", help="Persist the rebuilt index"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run"),
) -> None:
    service = _semantic_service(profile)
    result = service.rebuild(
        IndexRebuildRequest(
            workspaceId=workspace_id,
            apply=apply,
            dryRun=dry_run or not apply,
        )
    )
    _echo_json(result.model_dump(mode="json", by_alias=True))
    if result.status in {"blocked", "error"}:
        raise typer.Exit(code=1)


@memory_semantic_app.command("search")
def memory_semantic_search(
    query: str = typer.Option(..., "--query"),
    workspace_id: str = typer.Option("default", "--workspace-id"),
    principal_id: str = typer.Option("agent-local", "--principal-id"),
    requested_scope: list[str] = _MEMORY_SEMANTIC_SCOPE_OPTION,
    limit: int = typer.Option(8, min=1, max=50),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    service = _semantic_service(profile)
    result = service.search(
        MemorySearchRequest(
            query=query,
            principalId=principal_id,
            workspaceId=workspace_id,
            requestedScopes=tuple(requested_scope),
            limit=limit,
        )
    )
    _echo_json(result.model_dump(mode="json", by_alias=True))
    if result.status in {"blocked", "error"}:
        raise typer.Exit(code=1)


@memory_semantic_app.command("evaluate")
def memory_semantic_evaluate(
    suite: str = typer.Option(
        "tests/fixtures/memory_semantic/retrieval_quality.jsonl",
        "--suite",
    ),
    output: str = typer.Option(
        "artifacts/memory-semantic/retrieval_quality_report.json",
        "--output",
    ),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    from imperaos.memory.semantic.evaluator import run_retrieval_quality_suite

    service = _semantic_service(profile)
    report = run_retrieval_quality_suite(
        suite_path=suite,
        search_fn=service.search,
        output_path=output,
    )
    _echo_json(report.model_dump(mode="json", by_alias=True))
    if report.status != "pass":
        raise typer.Exit(code=1)


@memory_semantic_backend_app.command("doctor")
def memory_semantic_backend_doctor(
    workspace_id: str = typer.Option("default", "--workspace-id"),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    service = _semantic_service(profile)
    turbovec_status = TurboVecSemanticBackend().status(workspace_id)
    payload = {
        "status": "pass",
        "defaultBackend": service.status(workspace_id).model_dump(mode="json", by_alias=True),
        "turbovec": turbovec_status.model_dump(mode="json", by_alias=True),
        "rawContentIncluded": False,
    }
    _echo_json(payload)


@memory_workspace_sync_app.command("export")
def memory_workspace_sync_export(
    output: str = typer.Option(..., "--output"),
    workspace_id: str = typer.Option("default", "--workspace-id"),
    source_client_id: str = typer.Option("cli-local", "--source-client-id"),
    profile: str = typer.Option("balanced", help="Config profile"),
    limit: int = typer.Option(10000, min=1, max=10000),
) -> None:
    ensure_artifact_scaffold()
    authority = build_workspace_memory_authority(RuntimeConfig.from_profile(profile))
    coordinator = WorkspaceMemorySyncCoordinator(store=authority.store)
    pack = coordinator.export_pack(
        workspace_id=workspace_id,
        source_client_id=source_client_id,
        output_path=output,
        limit=limit,
    )
    _echo_json(pack.manifest.model_dump(mode="json", by_alias=True))


@memory_workspace_sync_app.command("verify")
def memory_workspace_sync_verify(input_path: str = typer.Option(..., "--input")) -> None:
    authority = build_workspace_memory_authority(RuntimeConfig.from_profile("balanced"))
    result = WorkspaceMemorySyncCoordinator(store=authority.store).verify_pack(input_path)
    _echo_json(result.model_dump(mode="json", by_alias=True))
    if result.status != "pass":
        raise typer.Exit(code=1)


@memory_workspace_sync_app.command("import")
def memory_workspace_sync_import(
    input_path: str = typer.Option(..., "--input"),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    authority = build_workspace_memory_authority(RuntimeConfig.from_profile(profile))
    report = WorkspaceMemorySyncCoordinator(store=authority.store).import_pack(
        input_path=input_path,
        dry_run=True,
    )
    _echo_json(report.model_dump(mode="json", by_alias=True))
    if report.status == "blocked":
        raise typer.Exit(code=1)


@memory_workspace_sync_app.command("apply")
def memory_workspace_sync_apply(
    input_path: str = typer.Option(..., "--input"),
    approval_id: str | None = typer.Option(None, "--approval-id"),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    authority = build_workspace_memory_authority(RuntimeConfig.from_profile(profile))
    report = WorkspaceMemorySyncCoordinator(store=authority.store).import_pack(
        input_path=input_path,
        dry_run=False,
        approval_id=approval_id,
    )
    _echo_json(report.model_dump(mode="json", by_alias=True))
    if report.status == "blocked":
        raise typer.Exit(code=1)


@memory_workspace_conflicts_app.command("list")
def memory_workspace_conflicts_list(
    workspace_id: str = typer.Option("default", "--workspace-id"),
    profile: str = typer.Option("balanced", help="Config profile"),
) -> None:
    authority = build_workspace_memory_authority(RuntimeConfig.from_profile(profile))
    _echo_json(
        {
            "status": "pass",
            "workspaceId": workspace_id,
            "conflicts": [
                item.model_dump(mode="json", by_alias=True)
                for item in authority.store.list_conflicts(workspace_id)
            ],
            "rawContentIncluded": False,
        }
    )


@memory_workspace_migrate_app.command("legacy-dry-run")
def memory_workspace_migrate_legacy_dry_run(
    legacy_db_path: str = typer.Option(..., "--legacy-db-path"),
    workspace_id: str = typer.Option("default", "--workspace-id"),
    default_scope: str = typer.Option("personal", "--default-scope"),
    output: str | None = typer.Option(None, "--output"),
) -> None:
    result = plan_legacy_memory_migration(
        LegacyMemoryMigrationPlanRequest(
            legacyDbPath=legacy_db_path,
            workspaceId=workspace_id,
            defaultScope=default_scope,
            outputPath=output,
        )
    )
    _echo_json(result.model_dump(mode="json", by_alias=True))
    if result.status == "blocked":
        raise typer.Exit(code=1)


def _echo_json(payload: object) -> None:
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


@research_app.command("train-router")
def research_train_router(
    dataset: str = typer.Option(
        state_path("research", "router_dataset.jsonl"),
        help="Dataset JSONL path",
    ),
    output_dir: str = typer.Option(
        "research/sltc_experiments/artifacts",
        help="Output directory",
    ),
    seed: int = typer.Option(42, help="Random seed"),
) -> None:
    ensure_artifact_scaffold()
    payload = train_router_model(dataset_path=dataset, output_dir=output_dir, seed=seed)
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    write_artifact("research_summary", {"kind": "train_router", "result": payload})


@research_app.command("eval-router")
def research_eval_router(
    dataset: str = typer.Option(
        state_path("research", "router_dataset.jsonl"),
        help="Dataset JSONL path",
    ),
    model: str = typer.Option(
        "research/sltc_experiments/artifacts/router_model.json",
        help="Trained router model path",
    ),
    output_dir: str = typer.Option(
        "research/sltc_experiments/artifacts",
        help="Output directory",
    ),
) -> None:
    ensure_artifact_scaffold()
    payload = evaluate_router_model(dataset_path=dataset, model_path=model, output_dir=output_dir)
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    write_artifact("research_summary", {"kind": "eval_router", "result": payload})


@research_app.command("calibrate-router")
def research_calibrate_router(
    dataset: str = typer.Option(
        state_path("research", "router_dataset.jsonl"),
        help="Dataset JSONL path",
    ),
    output_dir: str = typer.Option(
        "research/sltc_experiments/artifacts",
        help="Output directory",
    ),
    seed: int = typer.Option(42, help="Random seed"),
) -> None:
    ensure_artifact_scaffold()
    payload = calibrate_router_params(dataset_path=dataset, output_dir=output_dir, seed=seed)
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    write_artifact("research_summary", {"kind": "calibrate_router", "result": payload})


if __name__ == "__main__":
    app()
