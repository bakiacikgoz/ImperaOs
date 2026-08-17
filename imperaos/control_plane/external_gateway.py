from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from imperaos import __version__
from imperaos.control_plane.errors import ControlPlaneError
from imperaos.control_plane.external_contracts import (
    ExternalActionRequest,
    ExternalActionResponse,
    ExternalAgentRequestV11,
    ExternalAgentV11Result,
)
from imperaos.control_plane.models import (
    ActionProposal,
    AgentReadiness,
    AgentStatus,
    ControlPlaneDecisionAction,
    ControlPlaneRunSummary,
    RiskClass,
    RunStatus,
)
from imperaos.control_plane.policy_simulator import PolicySimulator
from imperaos.control_plane.registry import AgentRegistry
from imperaos.control_plane.storage import ControlPlaneStore, canonical_json_hash
from imperaos.governance.approval_store import ApprovalStore
from imperaos.runtime.config import RuntimeConfig
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT

EXTERNAL_GATEWAY_CONTRACT_VERSION = "control-plane.external-gateway/v1"
EXTERNAL_GATEWAY_V1_1_CONTRACT_VERSION = "control-plane.external-gateway/v1.1"
EXTERNAL_RUNTIME_KINDS = {"external_stdio", "external_http"}
SENSITIVE_REDACTION_KEYS = {"secret", "token", "password", "private_key", "api_key"}


class ExternalAgentGateway:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        registry: AgentRegistry,
        root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
    ):
        self.config = config
        self.registry = registry
        self.store = ControlPlaneStore(root_dir)
        self.policy = PolicySimulator(config=config)
        self.approvals = ApprovalStore(config.governance.approval_store_path)

    def submit_action_v1_1(self, request: ExternalAgentRequestV11) -> ExternalAgentV11Result:
        request_hash = canonical_json_hash(request.model_dump(mode="json", by_alias=True))
        existing = self._read_v1_1_idempotency(request.idempotency_key)
        if existing is not None:
            if existing.get("requestHash") != request_hash:
                return ExternalAgentV11Result(
                    requestId=request.request_id,
                    agentId=request.agent_id,
                    workflowId=request.workflow_id,
                    status="invalid_request",
                    reasonCode="EXTERNAL_AGENT_DUPLICATE_REQUEST",
                    policyDecision="unknown",
                    replayStatus="mismatch",
                    idempotencyStatus="conflict",
                    requestHash=request_hash,
                )
            response_payload = existing.get("response")
            if isinstance(response_payload, dict):
                return ExternalAgentV11Result.model_validate(
                    {
                        **response_payload,
                        "replayStatus": "replayed",
                        "idempotencyStatus": "replayed",
                    }
                )

        v1_request = _v1_request_from_v1_1(request)
        response = self.submit_action(v1_request)
        result = _v1_1_result_from_v1_response(
            request=request,
            response=response,
            request_hash=request_hash,
            replay_status="recorded",
            idempotency_status="created",
        )
        self._write_v1_1_evidence(request=request, request_hash=request_hash, result=result)
        self._write_v1_1_idempotency(
            request=request,
            request_hash=request_hash,
            response=result,
        )
        return result

    def replay_v1_1(
        self,
        *,
        request_id: str,
        expected_request_hash: str | None = None,
    ) -> dict[str, Any]:
        evidence_path = f"external-gateway/evidence/{request_id}.json"
        evidence = self.store.read_json(evidence_path)
        if not evidence:
            return {
                "version": "control-plane.external-agent-replay/v1.1",
                "requestId": request_id,
                "status": "missing",
                "evidenceRef": evidence_path,
                "reasonCode": "EXTERNAL_AGENT_EVIDENCE_MISSING",
            }
        actual_hash = evidence.get("request_hash_v1_1") or evidence.get("request_hash")
        if expected_request_hash and actual_hash != expected_request_hash:
            return {
                "version": "control-plane.external-agent-replay/v1.1",
                "requestId": request_id,
                "status": "mismatch",
                "evidenceRef": evidence_path,
                "reasonCode": "EXTERNAL_AGENT_REPLAY_MISMATCH",
                "expectedRequestHash": expected_request_hash,
                "actualRequestHash": actual_hash,
            }
        return {
            "version": "control-plane.external-agent-replay/v1.1",
            "requestId": request_id,
            "status": "verified",
            "evidenceRef": evidence_path,
            "reasonCode": "EXTERNAL_AGENT_REPLAY_VERIFIED",
            "actualRequestHash": actual_hash,
        }

    def submit_action(self, request: ExternalActionRequest) -> ExternalActionResponse:
        run_id = _gateway_run_id(request.request_id)
        evidence_ref = f"external-gateway/evidence/{request.request_id}.json"
        try:
            record = self.registry.get(request.agent_id)
        except ControlPlaneError:
            response = ExternalActionResponse(
                request_id=request.request_id,
                agent_id=request.agent_id,
                status="unknown_agent",
                reason_code="UNKNOWN_AGENT",
                dry_run=request.dry_run,
                evidence_ref=evidence_ref,
                next_actions=["agent.register"],
            )
            self._write_evidence(request=request, response=response, run_id=None)
            return response

        if str(record.status) != AgentStatus.REGISTERED.value:
            response = ExternalActionResponse(
                request_id=request.request_id,
                agent_id=request.agent_id,
                status="denied",
                reason_code="AGENT_DISABLED",
                dry_run=request.dry_run,
                evidence_ref=evidence_ref,
                next_actions=["agent.show", "agent.enable"],
            )
            self._write_evidence(request=request, response=response, run_id=None)
            return response

        if str(record.spec.runtime_kind) not in EXTERNAL_RUNTIME_KINDS:
            response = ExternalActionResponse(
                request_id=request.request_id,
                agent_id=request.agent_id,
                status="denied",
                reason_code="AGENT_RUNTIME_NOT_EXTERNAL",
                dry_run=request.dry_run,
                evidence_ref=evidence_ref,
                next_actions=["agent.register_external"],
            )
            self._write_evidence(request=request, response=response, run_id=None)
            return response

        enrollment_error = self._enrollment_error_for_record(record)
        if enrollment_error is not None:
            response = ExternalActionResponse(
                request_id=request.request_id,
                agent_id=request.agent_id,
                status="denied",
                reason_code=enrollment_error,
                dry_run=request.dry_run,
                evidence_ref=evidence_ref,
                next_actions=["enterprise enrollment approve"],
            )
            self._write_evidence(request=request, response=response, run_id=None)
            return response

        if not _redaction_summary_safe(request.payload_redaction_summary):
            response = ExternalActionResponse(
                request_id=request.request_id,
                agent_id=request.agent_id,
                status="invalid_request",
                reason_code="PAYLOAD_REDACTION_UNSAFE",
                dry_run=request.dry_run,
                evidence_ref=evidence_ref,
                next_actions=["redact.payload", "retry"],
            )
            self._write_evidence(request=request, response=response, run_id=None)
            return response

        proposal = _proposal_from_request(request=request, run_id=run_id)
        decision = self.policy.simulate_action(proposal)
        request_hash = canonical_json_hash(request.model_dump(mode="json", by_alias=True))
        status = RunStatus.CREATED
        approval_id: str | None = None
        response_status = "accepted"
        next_actions = ["evidence.inspect"]

        if decision.decision_action == ControlPlaneDecisionAction.DENY:
            status = RunStatus.POLICY_BLOCKED
            response_status = "denied"
            next_actions = ["policy.review", "request.update"]
        elif decision.decision_action == ControlPlaneDecisionAction.REQUIRE_APPROVAL:
            if request.dry_run:
                response_status = "requires_approval"
                next_actions = ["gateway.submit --dry-run false", "approval.required"]
            else:
                ticket = self.approvals.create_ticket(
                    workspace_id=self.config.memory.workspace_authority.default_workspace_id,
                    run_id=run_id,
                    target_kind="external_agent_action",
                    target_ref=f"{request.agent_id}:{request.action_kind}",
                    action_hash=canonical_json_hash(proposal.model_dump(mode="json")),
                    policy_hash=decision.policy_hash,
                    request_hash=request_hash,
                    snapshot_hash=canonical_json_hash(
                        {
                            "request": request.model_dump(mode="json", by_alias=True),
                            "decision": decision.model_dump(mode="json"),
                        }
                    ),
                    snapshot={
                        "kind": "external_agent_action",
                        "contract_version": EXTERNAL_GATEWAY_CONTRACT_VERSION,
                        "request": request.model_dump(mode="json", by_alias=True),
                        "decision": decision.model_dump(mode="json"),
                        "runtime_version": __version__,
                    },
                    ttl_seconds=self.config.governance.approval_ttl_seconds,
                    idempotency_key=f"external-gateway:{request.request_id}",
                )
                approval_id = ticket.approval_id
                status = RunStatus.APPROVAL_PENDING
                response_status = "blocked_pending_approval"
                next_actions = ["approval.show", "approval.decide", "approval.execute"]
        else:
            status = RunStatus.COMPLETED
            next_actions = ["evidence.inspect", "evidence.verify"]

        summary = ControlPlaneRunSummary(
            run_id=run_id,
            agent_id=request.agent_id,
            profile=self.config.profile_name,
            status=status,
            submitted_by=f"external:{request.actor_id}",
            identity_ref=f"external:{request.actor_id}",
            input_hash=request_hash,
            policy_hash=decision.policy_hash,
            completed_at=datetime.now(UTC) if status == RunStatus.COMPLETED else None,
            approval_ids=[approval_id] if approval_id else [],
            artifact_refs=[evidence_ref],
            evidence_pack_id=None,
            blocking_reasons=[decision.reason_code] if status == RunStatus.POLICY_BLOCKED else [],
            next_actions=next_actions,
        )
        self._write_run(
            summary=summary,
            request=request,
            proposal=proposal,
            decision=decision.model_dump(mode="json"),
        )
        self.registry.update_record(
            record.model_copy(
                update={
                    "readiness": AgentReadiness.POLICY_SIMULATED,
                    "last_run_id": run_id,
                    "updated_at": datetime.now(UTC),
                }
            )
        )

        response = ExternalActionResponse(
            request_id=request.request_id,
            agent_id=request.agent_id,
            status=response_status,
            reason_code=decision.reason_code,
            policy_decision=decision,
            run_id=run_id,
            approval_id=approval_id,
            evidence_ref=evidence_ref,
            dry_run=request.dry_run,
            next_actions=next_actions,
        )
        self._write_evidence(request=request, response=response, run_id=run_id)
        return response

    def _write_run(
        self,
        *,
        summary: ControlPlaneRunSummary,
        request: ExternalActionRequest,
        proposal: ActionProposal,
        decision: dict[str, Any],
    ) -> None:
        self.store.write_json_atomic(
            f"runs/{summary.run_id}.json",
            {
                "version": "control-plane.external-run-state/v1",
                "run": summary.model_dump(mode="json"),
                "external_request": request.model_dump(mode="json", by_alias=True),
                "action_proposal": proposal.model_dump(mode="json"),
                "policy_decision": decision,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

    def _write_evidence(
        self,
        *,
        request: ExternalActionRequest,
        response: ExternalActionResponse,
        run_id: str | None,
    ) -> None:
        self.store.write_json_atomic(
            f"external-gateway/evidence/{request.request_id}.json",
            {
                "version": "control-plane.external-gateway-evidence/v1",
                "request_id": request.request_id,
                "agent_id": request.agent_id,
                "run_id": run_id,
                "request": {
                    "actorId": request.actor_id,
                    "intent": request.intent,
                    "actionKind": request.action_kind,
                    "targetRef": request.target_ref,
                    "payloadHash": request.payload_hash,
                    "payloadRedactionSummary": request.payload_redaction_summary,
                    "requestedAt": request.requested_at.isoformat(),
                    "dryRun": request.dry_run,
                },
                "response": response.model_dump(mode="json", by_alias=True),
                "request_hash": canonical_json_hash(
                    request.model_dump(mode="json", by_alias=True)
                ),
                "response_hash": canonical_json_hash(
                    response.model_dump(mode="json", by_alias=True)
                ),
                "generated_at": datetime.now(UTC).isoformat(),
            },
        )

    def _enrollment_error_for_record(self, record: Any) -> str | None:
        from imperaos.control_plane.agent_enrollment import (
            EnterpriseEnrollmentError,
            require_active_enrollment,
        )

        workspace_id = _metadata_string_or_none(record.spec.metadata, "workspace_id")
        try:
            require_active_enrollment(
                agent_id=record.agent_id,
                workspace_id=workspace_id,
                root_dir=self.store.root_dir,
            )
        except EnterpriseEnrollmentError as exc:
            return exc.error_code
        return None

    def _read_v1_1_idempotency(self, idempotency_key: str) -> dict[str, Any] | None:
        safe_key = _safe_file_key(idempotency_key)
        return self.store.read_json(f"external-gateway/idempotency/{safe_key}.json")

    def _write_v1_1_idempotency(
        self,
        *,
        request: ExternalAgentRequestV11,
        request_hash: str,
        response: ExternalAgentV11Result,
    ) -> None:
        safe_key = _safe_file_key(request.idempotency_key)
        self.store.write_json_atomic(
            f"external-gateway/idempotency/{safe_key}.json",
            {
                "version": EXTERNAL_GATEWAY_V1_1_CONTRACT_VERSION,
                "idempotencyKey": request.idempotency_key,
                "requestId": request.request_id,
                "requestHash": request_hash,
                "response": response.model_dump(mode="json", by_alias=True),
                "generatedAt": datetime.now(UTC).isoformat(),
            },
        )

    def _write_v1_1_evidence(
        self,
        *,
        request: ExternalAgentRequestV11,
        request_hash: str,
        result: ExternalAgentV11Result,
    ) -> None:
        evidence_ref = result.evidence_ref
        if evidence_ref is None:
            return
        evidence = self.store.read_json(evidence_ref, default={})
        if not isinstance(evidence, dict):
            evidence = {}
        evidence.update(
            {
                "contract_version": EXTERNAL_GATEWAY_V1_1_CONTRACT_VERSION,
                "workflow_id": request.workflow_id,
                "idempotency_key": request.idempotency_key,
                "risk_hint": request.risk_hint,
                "request_hash_v1_1": request_hash,
                "request_v1_1": {
                    "requestId": request.request_id,
                    "agentId": request.agent_id,
                    "workflowId": request.workflow_id,
                    "intent": request.intent,
                    "actions": [
                        action.model_dump(mode="json", by_alias=True)
                        for action in request.actions
                    ],
                    "requestedBy": request.requested_by,
                    "riskHint": request.risk_hint,
                    "dryRun": request.dry_run,
                },
                "result_v1_1": result.model_dump(mode="json", by_alias=True),
            }
        )
        self.store.write_json_atomic(evidence_ref, evidence)


def submit_external_action_file(
    *,
    path: str | Path,
    config: RuntimeConfig,
    registry: AgentRegistry,
    root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
) -> ExternalActionResponse:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        request = ExternalActionRequest.model_validate(payload)
    except (json.JSONDecodeError, OSError, ValidationError) as exc:
        _ = exc
        return ExternalActionResponse(
            request_id="invalid",
            agent_id="unknown",
            status="invalid_request",
            reason_code="EXTERNAL_ACTION_CONTRACT_INVALID",
            dry_run=True,
            next_actions=["fix.request.schema"],
            evidence_ref=None,
        )
    return ExternalAgentGateway(
        config=config,
        registry=registry,
        root_dir=root_dir,
    ).submit_action(request)


def submit_external_action_v1_1_file(
    *,
    path: str | Path,
    config: RuntimeConfig,
    registry: AgentRegistry,
    root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
) -> ExternalAgentV11Result:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        request = ExternalAgentRequestV11.model_validate(payload)
    except (json.JSONDecodeError, OSError, ValidationError) as exc:
        _ = exc
        return ExternalAgentV11Result(
            requestId="invalid",
            agentId="unknown",
            workflowId="unknown",
            status="invalid_request",
            reasonCode="EXTERNAL_AGENT_V1_1_CONTRACT_INVALID",
            policyDecision="unknown",
            replayStatus="missing",
            idempotencyStatus="conflict",
            requestHash="sha256:invalid",
        )
    return ExternalAgentGateway(
        config=config,
        registry=registry,
        root_dir=root_dir,
    ).submit_action_v1_1(request)


def _proposal_from_request(*, request: ExternalActionRequest, run_id: str) -> ActionProposal:
    return ActionProposal(
        version="control-plane.action-proposal/v1",
        correlation_id=request.request_id,
        run_id=run_id,
        agent_id=request.agent_id,
        phase="tool",
        action_id=f"external_{request.action_kind}",
        action_type="external_agent_action",
        target_kind=request.action_kind,
        target_ref=request.target_ref or "",
        risk_class=_risk_for_action_kind(request.action_kind),
        effect_summary=request.intent,
        args_fingerprint=request.payload_hash,
        idempotency_key=request.request_id,
        payload_redacted=True,
        requested_at=request.requested_at,
    )


def _risk_for_action_kind(action_kind: str) -> RiskClass:
    return {
        "read": RiskClass.READ_ONLY,
        "mutate": RiskClass.MUTATION,
        "external_write": RiskClass.EXTERNAL_WRITE,
        "destructive": RiskClass.DESTRUCTIVE,
        "credential_sensitive": RiskClass.CREDENTIAL_SENSITIVE,
        "unknown": RiskClass.UNKNOWN,
    }.get(action_kind, RiskClass.UNKNOWN)


def _v1_request_from_v1_1(request: ExternalAgentRequestV11) -> ExternalActionRequest:
    action_kind = _action_kind_for_v1_1(request)
    target_ref = next((action.target_ref for action in request.actions if action.target_ref), None)
    return ExternalActionRequest(
        requestId=request.request_id,
        agentId=request.agent_id,
        actorId=request.requested_by,
        intent=request.intent,
        actionKind=action_kind,
        targetRef=target_ref,
        payloadHash=canonical_json_hash(
            {
                "workflowId": request.workflow_id,
                "actions": [
                    action.model_dump(mode="json", by_alias=True)
                    for action in request.actions
                ],
                "metadata": request.metadata,
            }
        ),
        payloadRedactionSummary={
            "payloadRedacted": True,
            "sensitiveValuesFound": False,
            "contractVersion": "v1.1",
        },
        requestedAt=request.requested_at,
        dryRun=request.dry_run,
    )


def _action_kind_for_v1_1(
    request: ExternalAgentRequestV11,
) -> Literal["read", "mutate", "external_write", "destructive", "credential_sensitive", "unknown"]:
    by_hint = {
        "read_only": "read",
        "mutation": "mutate",
        "external_write": "external_write",
        "destructive": "destructive",
        "credential_sensitive": "credential_sensitive",
        "unknown": "unknown",
    }
    if request.risk_hint != "unknown":
        return by_hint[request.risk_hint]  # type: ignore[return-value]
    risk_order = {
        "destructive": 5,
        "credential_sensitive": 4,
        "external_write": 3,
        "mutate": 2,
        "unknown": 1,
        "read": 0,
    }
    highest = max((action.kind for action in request.actions), key=lambda item: risk_order[item])
    return highest


def _v1_1_result_from_v1_response(
    *,
    request: ExternalAgentRequestV11,
    response: ExternalActionResponse,
    request_hash: str,
    replay_status: Literal["recorded", "replayed", "verified", "mismatch", "missing"],
    idempotency_status: Literal["created", "replayed", "conflict"],
) -> ExternalAgentV11Result:
    decision = "unknown"
    if response.status == "accepted":
        decision = "allow"
    elif response.status in {"requires_approval", "blocked_pending_approval"}:
        decision = "require_approval"
    elif response.status == "denied":
        decision = "deny"
    status = response.status
    if status == "requires_approval":
        status = "blocked_pending_approval"
    return ExternalAgentV11Result(
        requestId=request.request_id,
        agentId=request.agent_id,
        workflowId=request.workflow_id,
        status=status,  # type: ignore[arg-type]
        reasonCode=response.reason_code,
        policyDecision=decision,  # type: ignore[arg-type]
        runId=response.run_id,
        approvalId=response.approval_id,
        evidenceRef=response.evidence_ref,
        replayStatus=replay_status,
        idempotencyStatus=idempotency_status,
        requestHash=request_hash,
    )


def _redaction_summary_safe(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in SENSITIVE_REDACTION_KEYS):
                return False
            if not _redaction_summary_safe(nested):
                return False
        return True
    if isinstance(value, list):
        return all(_redaction_summary_safe(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return not any(marker in lowered for marker in SENSITIVE_REDACTION_KEYS)
    return True


def _gateway_run_id(request_id: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in request_id)
    return f"cp-ext-run-{safe[:72]}"


def _safe_file_key(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-"
        for char in value
    )[:120]


def _metadata_string_or_none(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value.strip() else None
