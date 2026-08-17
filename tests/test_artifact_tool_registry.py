from __future__ import annotations

from pathlib import Path

import pytest

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import OperationContext, PrincipalType
from imperaos.artifacts.service import ArtifactService
from imperaos.artifacts.tools import (
    PUBLIC_ARTIFACT_TOOL_NAMES,
    ArtifactToolRegistry,
)
from imperaos.governance.approval_store import ApprovalStore
from imperaos.model_providers.models import DataClass, ProviderPolicy
from imperaos.model_providers.native.types import ProviderRequestedTool, ProviderRequestedToolType
from imperaos.model_providers.tool_policy import evaluate_provider_tool_policy


def _context() -> OperationContext:
    return OperationContext(
        workspace_id="workspace-1",
        principal_type=PrincipalType.ASSISTANT,
        principal_id="assistant-1",
        roles=("artifact_editor",),
        request_id="request-tool-1",
        trace_id="trace-tool-1",
    )


def _document(text: str) -> dict[str, object]:
    return {
        "kind": "document",
        "schemaVersion": 1,
        "language": "en",
        "pageMode": "document",
        "blocks": [
            {
                "id": "block-1",
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def _registry(tmp_path: Path) -> ArtifactToolRegistry:
    approvals = ApprovalStore(tmp_path / "approvals.sqlite3")
    return ArtifactToolRegistry(
        ArtifactService(tmp_path / "artifact-root", approval_store=approvals)
    )


def test_registry_exposes_exactly_five_public_artifact_tools(tmp_path: Path) -> None:
    registry = _registry(tmp_path)

    assert registry.names == PUBLIC_ARTIFACT_TOOL_NAMES == (
        "artifact.create_draft",
        "artifact.get_context",
        "artifact.propose_mutation",
        "artifact.request_form",
        "artifact.request_export",
    )
    tools = registry.provider_tools()
    assert tuple(tool.name for tool in tools) == registry.names
    assert all(tool.tool_type is ProviderRequestedToolType.CUSTOM_FUNCTION for tool in tools)
    assert all(tool.parameters.get("additionalProperties") is False for tool in tools)
    assert not {
        "artifact.apply_mutation",
        "artifact.write_file",
        "artifact.import_asset_path",
        "artifact.execute_code",
        "artifact.delete_permanently",
        "artifact.send_external",
        "artifact.commit_export",
    } & set(registry.names)


def test_registry_denies_unknown_and_model_hidden_artifact_tools(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    for name in ("artifact.unknown", "artifact.apply_mutation", "artifact.commit_export"):
        with pytest.raises(ArtifactDomainError) as caught:
            registry.invoke(name, {}, _context())
        assert caught.value.code is ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED

        decision = evaluate_provider_tool_policy(
            requested_tool=ProviderRequestedTool(
                tool_type=ProviderRequestedToolType.CUSTOM_FUNCTION,
                name=name,
            ),
            provider_policy=ProviderPolicy(provider_id="provider-1", allow_tool_calls=True),
            data_class=DataClass.INTERNAL,
        )
        assert decision.status.value == "deny"
        assert decision.reason_code == "ARTIFACT_TOOL_NOT_PUBLIC"


def test_registry_routes_five_tools_through_governed_boundaries(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    context = _context()
    created = registry.invoke(
        "artifact.create_draft",
        {
            "artifactId": "artifact-1",
            "kind": "document",
            "title": "AI draft",
            "dataClass": "internal",
            "content": _document("draft"),
            "idempotencyKey": "tool-create-1",
            "sourceSessionId": "session-1",
            "sourceTurnId": "turn-1",
        },
        context,
    )
    context_result = registry.invoke(
        "artifact.get_context",
        {
            "artifactId": "artifact-1",
            "revisionId": created.revision_id,
            "purpose": "edit",
            "selection": {"kind": "document", "blockIds": ["block-1"]},
        },
        context,
    )
    proposal = registry.invoke(
        "artifact.propose_mutation",
        {
            "proposalId": "proposal-1",
            "artifactId": "artifact-1",
            "baseRevisionNumber": 1,
            "mutationType": "replace_content",
            "content": _document("proposal"),
            "idempotencyKey": "tool-proposal-1",
            "summary": "Update draft",
            "contextSha256": context_result.projection_sha256,
            "selectionSha256": context_result.selection_sha256,
            "sourceSessionId": "session-1",
            "sourceTurnId": "turn-1",
        },
        context,
        trusted_context=context_result,
    )
    form = registry.invoke(
        "artifact.request_form",
        {
            "artifactId": "form-1",
            "title": "Collect name",
            "dataClass": "internal",
            "schema": {
                "type": "object",
                "properties": {"name": {"type": "string", "maxLength": 100}},
                "required": ["name"],
                "additionalProperties": False,
            },
            "sensitivePaths": [],
            "externalContinuation": "deny",
            "idempotencyKey": "tool-form-1",
        },
        context,
    )
    export = registry.invoke(
        "artifact.request_export",
        {
            "artifactId": "artifact-1",
            "revisionId": created.revision_id,
            "format": "markdown",
            "idempotencyKey": "tool-export-1",
        },
        context,
    )

    assert created.status == "draft_created"
    assert context_result.artifact_id == "artifact-1"
    assert proposal.status == "approval_required"
    assert proposal.approval_id and proposal.action_hash
    assert form.status == "form_requested"
    assert export.status == "confirmation_required"
    assert export.native_write_started is False
