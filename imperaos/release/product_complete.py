from __future__ import annotations

from pydantic import Field

from imperaos.memory.models import StrictModel
from imperaos.release_decision.models import NoShipItem, NoShipRegister


class ProductCompleteInput(StrictModel):
    assistant_preview_in_product_mode: bool = Field(
        default=False,
        alias="assistantPreviewInProductMode",
    )
    fake_model_discovery: bool = Field(default=False, alias="fakeModelDiscovery")
    inert_primary_action: bool = Field(default=False, alias="inertPrimaryAction")
    enterprise_workspace_setup_bypass: bool = Field(
        default=False,
        alias="enterpriseWorkspaceSetupBypass",
    )
    agent_enrollment_raw_token_leak: bool = Field(
        default=False,
        alias="agentEnrollmentRawTokenLeak",
    )
    external_agent_not_enrolled_accepted: bool = Field(
        default=False,
        alias="externalAgentNotEnrolledAccepted",
    )
    memory_cross_workspace_allowed: bool = Field(
        default=False,
        alias="memoryCrossWorkspaceAllowed",
    )
    unrestricted_live_computer_use_claim: bool = Field(
        default=False,
        alias="unrestrictedLiveComputerUseClaim",
    )
    public_cloud_saas_claim: bool = Field(default=False, alias="publicCloudSaasClaim")
    public_installer_signed_claim_without_evidence: bool = Field(
        default=False,
        alias="publicInstallerSignedClaimWithoutEvidence",
    )


def _blocker(
    *,
    reason_code: str,
    claim_id: str,
    resolution_path: str,
) -> NoShipItem:
    return NoShipItem(
        id=reason_code,
        severity="blocker",
        status="open",
        claimId=claim_id,
        reasonCode=reason_code,
        resolutionPath=resolution_path,
    )


def build_product_complete_no_ship_register(
    input_state: ProductCompleteInput | None = None,
) -> NoShipRegister:
    state = input_state or ProductCompleteInput()
    items: list[NoShipItem] = []
    if state.assistant_preview_in_product_mode:
        items.append(
            _blocker(
                reason_code="ASSISTANT_PREVIEW_IN_PRODUCT_MODE",
                claim_id="real_ai_assistant_runtime",
                resolution_path=(
                    "Disable preview fixtures in product mode and route turns through "
                    "the assistant bridge."
                ),
            )
        )
    if state.fake_model_discovery:
        items.append(
            _blocker(
                reason_code="ASSISTANT_MODEL_DISCOVERY_FAKE",
                claim_id="assistant_model_discovery",
                resolution_path=(
                    "Use provider registry/model discovery or show setup-required diagnostics."
                ),
            )
        )
    if state.inert_primary_action:
        items.append(
            _blocker(
                reason_code="OPERATOR_INERT_PRIMARY_ACTION",
                claim_id="operator_panel_productization",
                resolution_path=(
                    "Classify the action as working, disabled_with_reason, or preview_only."
                ),
            )
        )
    if state.enterprise_workspace_setup_bypass:
        items.append(
            _blocker(
                reason_code="ENTERPRISE_WORKSPACE_SETUP_BYPASS",
                claim_id="enterprise_workspace_first_run",
                resolution_path=(
                    "Require identity/workspace readiness before enterprise-ready claims."
                ),
            )
        )
    if state.agent_enrollment_raw_token_leak:
        items.append(
            _blocker(
                reason_code="AGENT_ENROLLMENT_RAW_TOKEN_LEAK",
                claim_id="agent_enrollment",
                resolution_path=(
                    "Keep raw tokens shown-once only and store hashes in durable artifacts."
                ),
            )
        )
    if state.external_agent_not_enrolled_accepted:
        items.append(
            _blocker(
                reason_code="EXTERNAL_AGENT_NOT_ENROLLED_ACCEPTED",
                claim_id="external_agent_gateway",
                resolution_path=(
                    "Reject unknown or unenrolled external agents before action submission."
                ),
            )
        )
    if state.memory_cross_workspace_allowed:
        items.append(
            _blocker(
                reason_code="MEMORY_CROSS_WORKSPACE_ALLOWED",
                claim_id="workspace_memory_boundary",
                resolution_path="Enforce workspace-scoped memory ACLs and add denial evidence.",
            )
        )
    if state.unrestricted_live_computer_use_claim:
        items.append(
            _blocker(
                reason_code="COMPUTER_USE_UNQUALIFIED_CLAIM",
                claim_id="qualified_execution_surfaces",
                resolution_path=(
                    "Keep live computer-use qualification-gated with platform evidence."
                ),
            )
        )
    if state.public_cloud_saas_claim:
        items.append(
            _blocker(
                reason_code="PUBLIC_CLOUD_SAAS_OUT_OF_SCOPE",
                claim_id="product_boundary",
                resolution_path=(
                    "Remove public multi-tenant SaaS claims from product-complete scope."
                ),
            )
        )
    if state.public_installer_signed_claim_without_evidence:
        items.append(
            _blocker(
                reason_code="PUBLIC_INSTALLER_UNSIGNED_CLAIM",
                claim_id="desktop_public_release",
                resolution_path=(
                    "Attach real signing/notarization evidence or keep the claim internal-only."
                ),
            )
        )
    return NoShipRegister(status="clear", items=items)
