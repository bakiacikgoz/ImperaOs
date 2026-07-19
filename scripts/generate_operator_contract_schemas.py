from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.contracts.operator_panel import (  # noqa: E402
    ApprovalDetailPayloadContract,
    ApprovalPendingPayloadContract,
    AssistantStartTurnPayloadContract,
    AssistantStreamEventPayloadContract,
    AuthCheckPayloadContract,
    AuthWhoAmIPayloadContract,
    BridgeHandshakeContract,
    ConfigResolvePayloadContract,
    ControlPlaneAgentListPayloadContract,
    ControlPlaneClaimMatrixPayloadContract,
    ControlPlaneEvidenceExportPayloadContract,
    ControlPlaneEvidenceVerifyPayloadContract,
    ControlPlanePolicySimulationPayloadContract,
    ControlPlaneReadinessPayloadContract,
    ControlPlaneRunSummaryPayloadContract,
    DeviceActionApprovalSnapshotContract,
    KeyStatusPayloadContract,
    OperatorCapabilitiesPayload,
    PreviewFixtureBundleContract,
    ReadArtifactPayloadContract,
    RunReplayPayloadContract,
    RunSummaryPayloadContract,
    SecurityBaselinePayloadContract,
    SpawnedRunPayloadContract,
    SupportBundleExportPayloadContract,
    TailEventsPayloadContract,
    TeamStatusArtifactContract,
)

SCHEMAS = {
    "approval_detail": ApprovalDetailPayloadContract,
    "approval_pending": ApprovalPendingPayloadContract,
    "assistant_start_turn": AssistantStartTurnPayloadContract,
    "assistant_stream_event": AssistantStreamEventPayloadContract,
    "auth_check": AuthCheckPayloadContract,
    "auth_whoami": AuthWhoAmIPayloadContract,
    "bridge_handshake": BridgeHandshakeContract,
    "config_resolve": ConfigResolvePayloadContract,
    "control_plane_agent_list": ControlPlaneAgentListPayloadContract,
    "control_plane_claim_matrix": ControlPlaneClaimMatrixPayloadContract,
    "control_plane_evidence_export": ControlPlaneEvidenceExportPayloadContract,
    "control_plane_evidence_verify": ControlPlaneEvidenceVerifyPayloadContract,
    "control_plane_policy_simulation": ControlPlanePolicySimulationPayloadContract,
    "control_plane_readiness": ControlPlaneReadinessPayloadContract,
    "control_plane_run_summary": ControlPlaneRunSummaryPayloadContract,
    "device_action_snapshot": DeviceActionApprovalSnapshotContract,
    "key_status": KeyStatusPayloadContract,
    "operator_capabilities": OperatorCapabilitiesPayload,
    "preview_fixture_bundle": PreviewFixtureBundleContract,
    "read_artifact": ReadArtifactPayloadContract,
    "run_replay": RunReplayPayloadContract,
    "run_summary": RunSummaryPayloadContract,
    "security_baseline": SecurityBaselinePayloadContract,
    "spawned_run": SpawnedRunPayloadContract,
    "support_bundle_export": SupportBundleExportPayloadContract,
    "tail_events": TailEventsPayloadContract,
    "team_status_artifact": TeamStatusArtifactContract,
}


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "contracts" / "operator_panel" / "schemas"
    root.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMAS.items():
        target = root / f"{name}.schema.json"
        target.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
