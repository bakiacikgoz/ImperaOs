from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import Field, JsonValue, StringConstraints

from imperaos.artifacts.commands import (
    CreateArtifactCommand,
    GetArtifactQuery,
    ProposeArtifactMutationCommand,
)
from imperaos.artifacts.context import (
    ArtifactContextPack,
    ArtifactContextRequest,
    get_artifact_context,
)
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.exports import ArtifactExportFormat, require_export_format
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    ArtifactModel,
    BoundedId,
    OperationContext,
    Sha256,
    canonical_json,
)
from imperaos.artifacts.service import ArtifactService
from imperaos.artifacts.tool_names import PUBLIC_ARTIFACT_TOOL_NAMES
from imperaos.model_providers.native.types import (
    ProviderRequestedTool,
    ProviderRequestedToolType,
)


class ArtifactCreateDraftInput(ArtifactModel):
    artifact_id: BoundedId | None = None
    kind: ArtifactKind = Field(strict=False)
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    data_class: ArtifactDataClass = Field(strict=False)
    content: dict[str, JsonValue]
    idempotency_key: BoundedId
    source_session_id: BoundedId | None = None
    source_turn_id: BoundedId | None = None


class ArtifactCreateDraftResult(ArtifactModel):
    tool_name: Literal["artifact.create_draft"] = "artifact.create_draft"
    status: Literal["draft_created"] = "draft_created"
    artifact_id: BoundedId
    revision_id: BoundedId
    revision_number: int = Field(ge=1)
    data_class: ArtifactDataClass = Field(strict=False)
    kind: ArtifactKind = Field(strict=False)
    title: str = Field(min_length=1, max_length=200)


class ArtifactProposeMutationInput(ArtifactModel):
    proposal_id: BoundedId | None = None
    artifact_id: BoundedId
    base_revision_number: int = Field(ge=1)
    mutation_type: Literal["replace_content"]
    content: dict[str, JsonValue]
    idempotency_key: BoundedId
    summary: Annotated[str, StringConstraints(max_length=500, strict=True)] = ""
    context_sha256: Sha256
    selection_sha256: Sha256
    source_session_id: BoundedId | None = None
    source_turn_id: BoundedId | None = None


class ArtifactProposalToolResult(ArtifactModel):
    tool_name: Literal["artifact.propose_mutation"] = "artifact.propose_mutation"
    status: Literal["approval_required"] = "approval_required"
    proposal_id: BoundedId
    artifact_id: BoundedId
    base_revision_number: int = Field(ge=1)
    content_sha256: Sha256
    approval_id: BoundedId
    action_hash: Sha256
    summary: Annotated[str, StringConstraints(max_length=500, strict=True)] = ""
    data_class: ArtifactDataClass = Field(strict=False)
    kind: ArtifactKind = Field(strict=False)
    title: str = Field(min_length=1, max_length=200)


class ArtifactRequestFormInput(ArtifactModel):
    artifact_id: BoundedId | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    data_class: ArtifactDataClass = Field(strict=False)
    json_schema: dict[str, JsonValue] = Field(alias="schema")
    ui_schema: dict[str, JsonValue] = Field(default_factory=dict)
    sensitive_paths: tuple[
        Annotated[str, StringConstraints(pattern=r"^/(?:[^/~]|~[01])+(?:/(?:[^/~]|~[01])+)*$")],
        ...,
    ] = Field(default_factory=tuple, max_length=100, strict=False)
    external_continuation: Literal["deny", "approval_required"] = "deny"
    idempotency_key: BoundedId
    source_session_id: BoundedId | None = None
    source_turn_id: BoundedId | None = None


class ArtifactFormToolResult(ArtifactModel):
    tool_name: Literal["artifact.request_form"] = "artifact.request_form"
    status: Literal["form_requested"] = "form_requested"
    artifact_id: BoundedId
    revision_id: BoundedId
    revision_number: int = Field(ge=1)
    data_class: ArtifactDataClass = Field(strict=False)
    kind: Literal["form"] = "form"
    title: str = Field(min_length=1, max_length=200)


class ArtifactRequestExportInput(ArtifactModel):
    artifact_id: BoundedId
    revision_id: BoundedId
    format: ArtifactExportFormat
    idempotency_key: BoundedId


class ArtifactExportRequestToolResult(ArtifactModel):
    tool_name: Literal["artifact.request_export"] = "artifact.request_export"
    status: Literal["confirmation_required"] = "confirmation_required"
    request_id: BoundedId
    artifact_id: BoundedId
    revision_id: BoundedId
    format: ArtifactExportFormat
    request_sha256: Sha256
    native_write_started: Literal[False] = False
    data_class: ArtifactDataClass = Field(strict=False)
    kind: ArtifactKind = Field(strict=False)
    title: str = Field(min_length=1, max_length=200)


ArtifactToolResult = (
    ArtifactCreateDraftResult
    | ArtifactContextPack
    | ArtifactProposalToolResult
    | ArtifactFormToolResult
    | ArtifactExportRequestToolResult
)


@dataclass(frozen=True, slots=True)
class ArtifactToolExecutionMetadata:
    persists_state: bool
    provider_result_reserve_bytes: int


_TOOL_EXECUTION_METADATA = {
    "artifact.create_draft": ArtifactToolExecutionMetadata(True, 2_048),
    "artifact.get_context": ArtifactToolExecutionMetadata(False, 0),
    "artifact.propose_mutation": ArtifactToolExecutionMetadata(True, 2_048),
    "artifact.request_form": ArtifactToolExecutionMetadata(True, 2_048),
    "artifact.request_export": ArtifactToolExecutionMetadata(False, 0),
}


class ArtifactToolRegistry:
    def __init__(self, service: ArtifactService) -> None:
        self._service = service
        self._inputs: dict[str, type[ArtifactModel]] = {
            "artifact.create_draft": ArtifactCreateDraftInput,
            "artifact.get_context": ArtifactContextRequest,
            "artifact.propose_mutation": ArtifactProposeMutationInput,
            "artifact.request_form": ArtifactRequestFormInput,
            "artifact.request_export": ArtifactRequestExportInput,
        }

    @property
    def names(self) -> tuple[str, ...]:
        return PUBLIC_ARTIFACT_TOOL_NAMES

    def provider_tools(self) -> tuple[ProviderRequestedTool, ...]:
        descriptions = {
            "artifact.create_draft": (
                "Create a governed editable draft without applying external effects."
            ),
            "artifact.get_context": "Read a bounded redacted artifact selection context pack.",
            "artifact.propose_mutation": "Create a reviewable mutation proposal; never applies it.",
            "artifact.request_form": "Create a governed form draft for explicit user submission.",
            "artifact.request_export": "Request user-confirmed native export; never writes a file.",
        }
        return tuple(
            ProviderRequestedTool(
                tool_type=ProviderRequestedToolType.CUSTOM_FUNCTION,
                name=name,
                description=descriptions[name],
                parameters=self._inputs[name].model_json_schema(by_alias=True),
                mutating=False,
            )
            for name in self.names
        )

    def execution_metadata(self, name: str) -> ArtifactToolExecutionMetadata:
        metadata = _TOOL_EXECUTION_METADATA.get(name)
        if metadata is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
                "artifact tool execution metadata is unavailable",
                details={"reasonCode": "ARTIFACT_TOOL_NOT_PUBLIC"},
            )
        return metadata

    def invoke(
        self,
        name: str,
        arguments: dict[str, Any],
        context: OperationContext,
        *,
        trusted_context: ArtifactContextPack | None = None,
    ) -> ArtifactToolResult:
        model = self._inputs.get(name)
        if model is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
                "artifact tool is not model-visible",
                details={"reasonCode": "ARTIFACT_TOOL_NOT_PUBLIC"},
            )
        parsed = model.model_validate(arguments)
        if name == "artifact.create_draft":
            return self._create_draft(parsed, context)
        if name == "artifact.get_context":
            return get_artifact_context(self._service, parsed, context)
        if name == "artifact.propose_mutation":
            return self._propose_mutation(parsed, context, trusted_context)
        if name == "artifact.request_form":
            return self._request_form(parsed, context)
        if name == "artifact.request_export":
            return self._request_export(parsed, context)
        raise AssertionError("unreachable artifact tool route")

    def _create_draft(
        self,
        value: ArtifactModel,
        context: OperationContext,
    ) -> ArtifactCreateDraftResult:
        request = ArtifactCreateDraftInput.model_validate(value)
        result = self._service.create(
            CreateArtifactCommand(**request.model_dump(mode="python")),
            context,
        )
        return ArtifactCreateDraftResult(
            artifact_id=result.artifact.artifact_id,
            revision_id=result.revision.revision_id,
            revision_number=result.revision.revision_number,
            data_class=result.artifact.data_class,
            kind=result.artifact.kind,
            title=result.artifact.title,
        )

    def _propose_mutation(
        self,
        value: ArtifactModel,
        context: OperationContext,
        trusted_context: ArtifactContextPack | None,
    ) -> ArtifactProposalToolResult:
        request = ArtifactProposeMutationInput.model_validate(value)
        if trusted_context is None or trusted_context.selection is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
                "artifact mutation proposal requires a trusted selection context",
                details={"reasonCode": "ARTIFACT_CONTEXT_GRANT_EXCEEDED"},
            )
        command = ProposeArtifactMutationCommand(
            **request.model_dump(mode="python"),
            context_revision_id=trusted_context.revision_id,
            context_purpose=trusted_context.purpose.value,
            target_selection=trusted_context.selection.model_dump(
                mode="json", by_alias=True
            ),
        )
        result = self._service.propose_mutation(command, context)
        artifact = self._service.store.get_artifact(context.workspace_id, request.artifact_id)
        return ArtifactProposalToolResult(
            proposal_id=result.proposal_id,
            artifact_id=result.artifact_id,
            base_revision_number=result.base_revision_number,
            content_sha256=result.content_sha256,
            approval_id=result.approval_id,
            action_hash=result.action_hash,
            summary=result.summary,
            data_class=artifact.data_class,
            kind=artifact.kind,
            title=artifact.title,
        )

    def _request_form(
        self,
        value: ArtifactModel,
        context: OperationContext,
    ) -> ArtifactFormToolResult:
        request = ArtifactRequestFormInput.model_validate(value)
        result = self._service.create(
            CreateArtifactCommand(
                artifact_id=request.artifact_id,
                kind=ArtifactKind.FORM,
                title=request.title,
                data_class=request.data_class,
                content={
                    "kind": "form",
                    "schemaVersion": 1,
                    "schema": request.json_schema,
                    "uiSchema": request.ui_schema,
                    "behavior": {
                        "submitMode": "explicit",
                        "externalContinuation": request.external_continuation,
                    },
                    "sensitivePaths": list(request.sensitive_paths),
                },
                idempotency_key=request.idempotency_key,
                source_session_id=request.source_session_id,
                source_turn_id=request.source_turn_id,
            ),
            context,
        )
        return ArtifactFormToolResult(
            artifact_id=result.artifact.artifact_id,
            revision_id=result.revision.revision_id,
            revision_number=result.revision.revision_number,
            data_class=result.artifact.data_class,
            title=result.artifact.title,
        )

    def _request_export(
        self,
        value: ArtifactModel,
        context: OperationContext,
    ) -> ArtifactExportRequestToolResult:
        request = ArtifactRequestExportInput.model_validate(value)
        loaded = self._service.get(
            GetArtifactQuery(
                artifact_id=request.artifact_id,
                revision_id=request.revision_id,
            ),
            context,
        )
        require_export_format(loaded.artifact.kind, request.format)
        payload = {
            "workspaceId": context.workspace_id,
            "artifactId": request.artifact_id,
            "revisionId": request.revision_id,
            "format": request.format,
            "idempotencyKey": request.idempotency_key,
        }
        digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        return ArtifactExportRequestToolResult(
            request_id=f"export-request-{digest[:24]}",
            artifact_id=request.artifact_id,
            revision_id=request.revision_id,
            format=request.format,
            request_sha256=digest,
            data_class=loaded.artifact.data_class,
            kind=loaded.artifact.kind,
            title=loaded.artifact.title,
        )
