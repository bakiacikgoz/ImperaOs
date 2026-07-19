from __future__ import annotations

import base64
import binascii
import hashlib
import json
import sqlite3
from collections import deque
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from imperaos.artifacts.assets import ArtifactAssetStore
from imperaos.artifacts.commands import (
    ApplyArtifactProposalCommand,
    ArchiveArtifactCommand,
    ArtifactHistoryQuery,
    BeginArtifactExportCommand,
    CancelArtifactExportCommand,
    CommitArtifactExportCommand,
    CreateArtifactCommand,
    DuplicateArtifactCommand,
    GetArtifactAssetQuery,
    GetArtifactQuery,
    ImportArtifactAssetCommand,
    ImportEvidenceArtifactCommand,
    ListArtifactsQuery,
    MutateArtifactCommand,
    PatchArtifactSlideCommand,
    PatchSpreadsheetCellsCommand,
    PreflightArtifactExportCommand,
    ProposeArtifactMutationCommand,
    RestoreArtifactCommand,
    SubmitArtifactFormCommand,
)
from imperaos.artifacts.content import (
    ArtifactContent,
    FormContentV1,
    SlidesContentV2,
    SpreadsheetContentV2,
    validate_artifact_content,
)
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.evidence import (
    ArtifactEvidenceRecorder,
    record_artifact_evidence,
)
from imperaos.artifacts.evidence_import import (
    ArtifactEvidenceResolver,
    DenyArtifactEvidenceResolver,
)
from imperaos.artifacts.exports import (
    DEFAULT_ARTIFACT_EXPORT_MAX_BYTES,
    canonical_export_basename,
    require_export_format,
)
from imperaos.artifacts.form_continuation import ArtifactFormContinuationGateway
from imperaos.artifacts.forms import validate_form_response
from imperaos.artifacts.licenses import ArtifactLicenseCapability
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactDescriptor,
    ArtifactKind,
    ArtifactModel,
    ArtifactMutationType,
    ArtifactRevisionDescriptor,
    ArtifactStatus,
    OperationContext,
    PrincipalType,
    can_transition_data_class,
    canonical_json,
)
from imperaos.artifacts.mutation_scope import require_scoped_replacement
from imperaos.artifacts.operations import ArtifactOperationMetrics
from imperaos.artifacts.policy import ArtifactPermission, ArtifactPolicyGateway
from imperaos.artifacts.proposal_approval import ArtifactProposalApprovalGateway
from imperaos.artifacts.results import (
    ArtifactAssetImportResult,
    ArtifactAssetReadResult,
    ArtifactExportBeginResult,
    ArtifactExportResult,
    ArtifactFormSubmissionResult,
    ArtifactHistoryResult,
    ArtifactListResult,
    ArtifactMutationProposalResult,
    ArtifactOperationResult,
    ArtifactReadResult,
)
from imperaos.artifacts.store import ArtifactStore, revision_content_relpath
from imperaos.governance.approval_store import ApprovalStore
from imperaos.runtime.paths import state_path

_DEFAULT_CONTINUATION_GATEWAY = object()
_ASSET_IMPORT_RESERVATION_TTL = timedelta(minutes=5)
_EDITOR_FLAG_SAFE_OPERATIONS = {
    "artifact.list",
    "artifact.get",
    "artifact.history",
    "artifact.archive",
    "artifact.asset.read",
}


class ArtifactService:
    """Policy-enforced application service for governed artifact operations."""

    def __init__(
        self,
        root: str | Path,
        *,
        policy: ArtifactPolicyGateway | None = None,
        evidence: ArtifactEvidenceRecorder | None = None,
        continuation_gateway: ArtifactFormContinuationGateway | None | object = (
            _DEFAULT_CONTINUATION_GATEWAY
        ),
        license_capabilities: Mapping[ArtifactKind, ArtifactLicenseCapability] | None = None,
        fallback_editor_capabilities: Mapping[ArtifactKind, bool] | None = None,
        evidence_resolver: ArtifactEvidenceResolver | None = None,
        approval_store: ApprovalStore | None = None,
        feature_flags: Mapping[str, bool] | None = None,
    ) -> None:
        self.store = ArtifactStore(root)
        self.assets = ArtifactAssetStore(root)
        self.evidence_resolver = evidence_resolver or DenyArtifactEvidenceResolver()
        self.policy = policy or ArtifactPolicyGateway()
        self.evidence = evidence or ArtifactEvidenceRecorder(self.store.database_path)
        self.operations = ArtifactOperationMetrics()
        self.operation_logs: deque[dict[str, object]] = deque(maxlen=256)
        self._feature_flags = None if feature_flags is None else dict(feature_flags)
        self._approval_store = approval_store or ApprovalStore(
            Path(state_path("governance", "approvals.sqlite3"))
        )
        self._proposal_approvals = ArtifactProposalApprovalGateway(self._approval_store)
        self._continuation_gateway = continuation_gateway
        supplied = dict(license_capabilities or {})
        self._license_capabilities = {
            kind: supplied.get(kind) or ArtifactLicenseCapability(
                kind=kind.value,  # type: ignore[arg-type]
                enabled=False,
                reason_code="ARTIFACT_LICENSE_EVIDENCE_MISSING",
            )
            for kind in (ArtifactKind.SPREADSHEET, ArtifactKind.CANVAS)
        }
        self._fallback_editor_capabilities = {
            kind: (fallback_editor_capabilities or {}).get(kind) is True
            for kind in (ArtifactKind.SPREADSHEET, ArtifactKind.CANVAS)
        }
        if any(
            capability.kind != kind.value
            for kind, capability in self._license_capabilities.items()
        ):
            raise ValueError("artifact license capability kind mismatch")

    def license_capabilities(self) -> tuple[ArtifactLicenseCapability, ...]:
        return tuple(self._license_capabilities.values())

    def feature_flags(self) -> dict[str, bool]:
        """Return the already-resolved rollout state without process configuration."""

        return dict(self._feature_flags or {})

    def require_operation_enabled(
        self,
        operation: str,
        subject: object,
        context: OperationContext,
    ) -> None:
        flags = self._feature_flags
        if flags is None:
            return
        required = "artifact_workspace.enabled"
        if flags.get(required) is not True:
            self._raise_feature_disabled(required)
        if operation.startswith("artifact.export."):
            required = "artifact_workspace.export.enabled"
            if flags.get(required) is not True:
                self._raise_feature_disabled(required)
        kind = self._operation_artifact_kind(subject, context)
        if kind is not None:
            required = f"artifact_workspace.{kind.value}.enabled"
            safe_without_editor = (
                operation in _EDITOR_FLAG_SAFE_OPERATIONS
                or operation.startswith("artifact.export.")
            )
            if flags.get(required) is not True and not safe_without_editor:
                self._raise_feature_disabled(required)

    def _operation_artifact_kind(
        self,
        subject: object,
        context: OperationContext,
    ) -> ArtifactKind | None:
        kind = getattr(subject, "kind", None)
        if isinstance(kind, ArtifactKind):
            return kind
        artifact_id = getattr(subject, "artifact_id", None) or getattr(
            subject, "source_artifact_id", None
        )
        if not isinstance(artifact_id, str):
            proposal_id = getattr(subject, "proposal_id", None)
            if isinstance(proposal_id, str):
                with self.store._connect() as connection:
                    row = connection.execute(
                        "SELECT artifact_id FROM artifact_mutation_proposals "
                        "WHERE proposal_id = ? AND workspace_id = ?",
                        (proposal_id, context.workspace_id),
                    ).fetchone()
                artifact_id = row["artifact_id"] if row is not None else None
        if not isinstance(artifact_id, str):
            return None
        try:
            return self.store.get_artifact(context.workspace_id, artifact_id).kind
        except ArtifactDomainError as exc:
            if exc.code is ArtifactErrorCode.ARTIFACT_NOT_FOUND:
                return None
            raise

    @staticmethod
    def _raise_feature_disabled(flag_name: str) -> None:
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE,
            "artifact workspace capability is disabled",
            details={
                "reasonCode": "ARTIFACT_FEATURE_DISABLED",
                "featureFlag": flag_name,
            },
        )

    def _require_licensed_editor(self, kind: ArtifactKind) -> None:
        if (
            kind in self._license_capabilities
            and not self._license_capabilities[kind].enabled
            and not self._fallback_editor_capabilities[kind]
        ):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_LICENSE_UNAVAILABLE,
                "artifact editor adapter is unavailable",
                details={
                    "kind": kind.value,
                    "reasonCode": self._license_capabilities[kind].reason_code,
                    "fallbackAvailable": False,
                },
            )

    @record_artifact_evidence("artifact.create")
    def create(
        self,
        command: CreateArtifactCommand,
        context: OperationContext,
    ) -> ArtifactOperationResult:
        self.policy.authorize(ArtifactPermission.CREATE, context)
        request_hash = self._request_hash(command)
        replay = self._load_operation_replay(
            context.workspace_id,
            command.idempotency_key,
            "create",
            request_hash,
        )
        if replay is not None:
            return replay

        content = self._validate_content(command.kind, command.content)
        effective_data_class = self._effective_content_data_class(
            context.workspace_id, content, command.data_class
        )
        self.policy.authorize(
            ArtifactPermission.CREATE,
            context,
            artifact_workspace_id=context.workspace_id,
            target_data_class=effective_data_class,
        )
        payload = canonical_json(content).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        artifact_id = command.artifact_id or self._stable_id(
            "artifact", context.workspace_id, command.idempotency_key
        )
        revision_id = self._stable_id("revision", artifact_id, command.idempotency_key)
        now = datetime.now(UTC)
        revision = ArtifactRevisionDescriptor(
            revision_id=revision_id,
            artifact_id=artifact_id,
            revision_number=1,
            schema_version=content.schema_version,
            mutation_type=ArtifactMutationType.CREATE,
            content_relpath=revision_content_relpath(
                context.workspace_id, artifact_id, 1, revision_id, "json"
            ),
            content_sha256=digest,
            content_size_bytes=len(payload),
            content_encoding="json",
            change_summary="Artifact created",
            author_type=context.principal_type,
            author_id=context.principal_id,
            idempotency_key=command.idempotency_key,
            created_at_utc=now,
        )
        artifact = ArtifactDescriptor(
            artifact_id=artifact_id,
            workspace_id=context.workspace_id,
            kind=command.kind,
            title=command.title,
            status=ArtifactStatus.DRAFT,
            schema_version=content.schema_version,
            data_class=effective_data_class,
            current_revision_id=revision_id,
            current_revision_number=1,
            source_session_id=command.source_session_id,
            source_turn_id=command.source_turn_id,
            created_by_type=context.principal_type,
            created_by_id=context.principal_id,
            updated_by_id=context.principal_id,
            created_at_utc=now,
            updated_at_utc=now,
            etag=digest,
            metadata=command.metadata,
        )
        result = self.store.create_artifact(
            artifact,
            revision,
            payload,
            operation="create",
            request_hash=request_hash,
        )
        operation = ArtifactOperationResult(
            artifact=result.artifact,
            revision=result.revision,
            created=result.created,
            disposition=result.disposition,
        )
        return operation

    @record_artifact_evidence("artifact.spreadsheet.cell_patch")
    def patch_spreadsheet_cells(
        self,
        command: PatchSpreadsheetCellsCommand,
        context: OperationContext,
    ) -> ArtifactOperationResult:
        artifact = self.store.get_artifact(context.workspace_id, command.artifact_id)
        if artifact.kind is not ArtifactKind.SPREADSHEET or artifact.schema_version != 2:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_SCHEMA_VERSION_UNSUPPORTED,
                "cell patches require a spreadsheet.v2 artifact",
            )
        self._require_licensed_editor(ArtifactKind.SPREADSHEET)
        request_hash = self._request_hash(command)
        replay = self._load_operation_replay(
            context.workspace_id,
            command.idempotency_key,
            "spreadsheet_cell_patch",
            request_hash,
        )
        if replay is not None:
            return replay
        stored = self.store.get_revision(
            context.workspace_id, artifact.artifact_id, artifact.current_revision_id
        )
        content = self._decode_content(
            artifact.kind, stored.content, schema_version=stored.descriptor.schema_version
        )
        if not isinstance(content, SpreadsheetContentV2):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "stored spreadsheet content has an invalid type",
            )
        payload = content.model_dump(mode="json", by_alias=True)
        target = next(
            (sheet for sheet in payload["sheets"] if sheet["id"] == command.sheet_id),
            None,
        )
        if target is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID,
                "spreadsheet patch sheet does not exist",
            )
        cells = target["cells"]
        for operation in command.operations:
            if operation.op == "set":
                cells[operation.address] = {"value": operation.value}
            else:
                cells.pop(operation.address, None)
        validated = self._validate_content(
            ArtifactKind.SPREADSHEET, payload, schema_version=2
        )
        return self._mutate(
            MutateArtifactCommand(
                artifact_id=artifact.artifact_id,
                expected_revision_number=command.expected_revision_number,
                mutation_type=ArtifactMutationType.REPLACE_CONTENT,
                content=validated.model_dump(mode="json", by_alias=True),
                idempotency_key=command.idempotency_key,
                change_summary=command.change_summary,
            ),
            context,
            _operation="spreadsheet_cell_patch",
            _request_hash=request_hash,
            _revision_mutation_type=ArtifactMutationType.CELL_PATCH,
        )

    @record_artifact_evidence("artifact.slides.slide_patch")
    def patch_artifact_slide(
        self,
        command: PatchArtifactSlideCommand,
        context: OperationContext,
    ) -> ArtifactOperationResult:
        artifact = self.store.get_artifact(context.workspace_id, command.artifact_id)
        if artifact.kind is not ArtifactKind.SLIDES or artifact.schema_version != 2:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_SCHEMA_VERSION_UNSUPPORTED,
                "slide patches require a slides.v2 artifact",
            )
        request_hash = self._request_hash(command)
        replay = self._load_operation_replay(
            context.workspace_id,
            command.idempotency_key,
            "slides_slide_patch",
            request_hash,
        )
        if replay is not None:
            return replay
        stored = self.store.get_revision(
            context.workspace_id, artifact.artifact_id, artifact.current_revision_id
        )
        content = self._decode_content(
            artifact.kind, stored.content, schema_version=stored.descriptor.schema_version
        )
        if not isinstance(content, SlidesContentV2):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "stored slides content has an invalid type",
            )
        payload = content.model_dump(mode="json", by_alias=True)
        slide = next(
            (item for item in payload["slides"] if item["id"] == command.slide_id),
            None,
        )
        if slide is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID,
                "slide patch target does not exist",
            )
        for operation in command.operations:
            if operation.op == "set_title":
                slide["title"] = operation.title
            elif operation.op == "upsert_element":
                element_id = operation.element.get("id")
                index = next(
                    (i for i, item in enumerate(slide["elements"]) if item["id"] == element_id),
                    None,
                )
                if index is None:
                    slide["elements"].append(operation.element)
                else:
                    slide["elements"][index] = operation.element
            else:
                before = len(slide["elements"])
                slide["elements"] = [
                    item for item in slide["elements"] if item["id"] != operation.element_id
                ]
                if len(slide["elements"]) == before:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID,
                        "slide patch element does not exist",
                    )
        validated = self._validate_content(ArtifactKind.SLIDES, payload, schema_version=2)
        return self._mutate(
            MutateArtifactCommand(
                artifact_id=artifact.artifact_id,
                expected_revision_number=command.expected_revision_number,
                mutation_type=ArtifactMutationType.REPLACE_CONTENT,
                content=validated.model_dump(mode="json", by_alias=True),
                idempotency_key=command.idempotency_key,
                change_summary=command.change_summary,
            ),
            context,
            _operation="slides_slide_patch",
            _request_hash=request_hash,
            _revision_mutation_type=ArtifactMutationType.SLIDE_PATCH,
        )

    @record_artifact_evidence("artifact.get")
    def get(
        self,
        query: GetArtifactQuery,
        context: OperationContext,
    ) -> ArtifactReadResult:
        artifact = self.store.get_artifact(context.workspace_id, query.artifact_id)
        self.policy.authorize(
            ArtifactPermission.READ,
            context,
            artifact_workspace_id=artifact.workspace_id,
        )
        revision = self.store.get_revision(
            context.workspace_id,
            query.artifact_id,
            query.revision_id or artifact.current_revision_id,
        )
        content = self._decode_content(
            artifact.kind, revision.content, schema_version=revision.descriptor.schema_version
        )
        return ArtifactReadResult(artifact, revision.descriptor, content)

    @record_artifact_evidence("artifact.list")
    def list(
        self,
        query: ListArtifactsQuery,
        context: OperationContext,
    ) -> ArtifactListResult:
        self.policy.authorize(ArtifactPermission.READ, context)
        offset = self._decode_cursor(query.cursor)
        items = self.store.list_artifacts(
            context.workspace_id,
            kind=query.kind.value if query.kind else None,
            status=query.status.value if query.status else None,
            limit=query.limit + 1,
            offset=offset,
        )
        has_more = len(items) > query.limit
        return ArtifactListResult(
            items=items[: query.limit],
            next_cursor=str(offset + query.limit) if has_more else None,
        )

    @record_artifact_evidence("artifact.mutate")
    def mutate(
        self,
        command: MutateArtifactCommand,
        context: OperationContext,
        *,
        _operation: str = "mutate",
        _request_hash: str | None = None,
        _approval_verified: bool = False,
        _proposal_id: str | None = None,
        _revision_mutation_type: ArtifactMutationType | None = None,
    ) -> ArtifactOperationResult:
        return self._mutate(
            command,
            context,
            _operation=_operation,
            _request_hash=_request_hash,
            _approval_verified=_approval_verified,
            _proposal_id=_proposal_id,
            _revision_mutation_type=_revision_mutation_type,
        )

    def _mutate(
        self,
        command: MutateArtifactCommand,
        context: OperationContext,
        *,
        _operation: str = "mutate",
        _request_hash: str | None = None,
        _approval_verified: bool = False,
        _proposal_id: str | None = None,
        _revision_mutation_type: ArtifactMutationType | None = None,
    ) -> ArtifactOperationResult:
        current = self.store.get_artifact(context.workspace_id, command.artifact_id)
        permission = (
            ArtifactPermission.AI_APPLY
            if context.principal_type.value == "assistant"
            else ArtifactPermission.UPDATE
        )
        self.policy.authorize(
            permission,
            context,
            artifact_workspace_id=current.workspace_id,
            current_data_class=current.data_class,
            target_data_class=current.data_class,
            approval_granted=_approval_verified,
        )
        self._require_licensed_editor(current.kind)
        request_hash = _request_hash or self._request_hash(command)
        replay = self._load_operation_replay(
            context.workspace_id,
            command.idempotency_key,
            _operation,
            request_hash,
        )
        if replay is not None:
            return replay
        if current.status is ArtifactStatus.ARCHIVED:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
                "archived artifacts are read-only",
            )
        if permission is ArtifactPermission.AI_APPLY and (
            not _approval_verified or _proposal_id is None
        ):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
                "assistant mutations require an approved proposal",
            )

        content = self._validate_content(
            current.kind, command.content, schema_version=current.schema_version
        )
        effective_data_class = self._effective_content_data_class(
            context.workspace_id, content, current.data_class
        )
        self.policy.authorize(
            permission,
            context,
            artifact_workspace_id=current.workspace_id,
            current_data_class=current.data_class,
            target_data_class=effective_data_class,
            approval_granted=_approval_verified,
        )
        payload = canonical_json(content).encode("utf-8")
        revision_number = command.expected_revision_number + 1
        revision_id = self._stable_id(
            "revision", current.artifact_id, command.idempotency_key
        )
        digest = hashlib.sha256(payload).hexdigest()
        now = datetime.now(UTC)
        revision = ArtifactRevisionDescriptor(
            revision_id=revision_id,
            artifact_id=current.artifact_id,
            parent_revision_id=current.current_revision_id,
            revision_number=revision_number,
            schema_version=current.schema_version,
            mutation_type=_revision_mutation_type or command.mutation_type,
            content_relpath=revision_content_relpath(
                context.workspace_id,
                current.artifact_id,
                revision_number,
                revision_id,
                "json",
            ),
            content_sha256=digest,
            content_size_bytes=len(payload),
            content_encoding="json",
            change_summary=command.change_summary,
            author_type=context.principal_type,
            author_id=context.principal_id,
            idempotency_key=command.idempotency_key,
            created_at_utc=now,
        )
        updated = ArtifactDescriptor.model_validate(
            {
                **current.model_dump(mode="python"),
                "current_revision_id": revision_id,
                "current_revision_number": revision_number,
                "updated_by_id": context.principal_id,
                "updated_at_utc": now,
                "etag": digest,
                "data_class": effective_data_class,
            }
        )
        stored = self.store.append_revision(
            updated,
            revision,
            payload,
            expected_revision_number=command.expected_revision_number,
            operation=_operation,
            request_hash=request_hash,
        )
        operation = ArtifactOperationResult(
            stored.artifact,
            stored.revision,
            stored.created,
            stored.disposition,
        )
        return operation

    @record_artifact_evidence("artifact.propose_mutation")
    def propose_mutation(
        self,
        command: ProposeArtifactMutationCommand,
        context: OperationContext,
    ) -> ArtifactMutationProposalResult:
        artifact = self.store.get_artifact(context.workspace_id, command.artifact_id)
        self.policy.authorize(
            ArtifactPermission.AI_PROPOSE,
            context,
            artifact_workspace_id=artifact.workspace_id,
        )
        from imperaos.artifacts.context import (
            ArtifactContextRequest,
            build_artifact_context_pack,
        )

        base_read = self.get(
            GetArtifactQuery(
                artifact_id=command.artifact_id,
                revision_id=command.context_revision_id,
            ),
            context,
        )
        context_request = ArtifactContextRequest.model_validate(
            {
                "artifactId": command.artifact_id,
                "revisionId": command.context_revision_id,
                "purpose": command.context_purpose,
                "allowedScopes": ["metadata", "selection"],
                "selection": command.target_selection,
            }
        )
        context_pack = build_artifact_context_pack(base_read, context_request)
        if (
            context_pack.revision_number != command.base_revision_number
            or context_pack.projection_sha256 != command.context_sha256
            or context_pack.selection_sha256 != command.selection_sha256
        ):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
                "artifact proposal context binding is invalid",
                details={"reasonCode": "ARTIFACT_PROPOSAL_CONTEXT_INVALID"},
            )
        content = self._validate_content(
            artifact.kind, command.content, schema_version=artifact.schema_version
        )
        require_scoped_replacement(
            artifact.kind,
            base_read.content.model_dump(mode="json", by_alias=True),
            content.model_dump(mode="json", by_alias=True),
            command.target_selection,
        )
        content_json = canonical_json(content)
        digest = hashlib.sha256(content_json.encode("utf-8")).hexdigest()
        normalized_command = command.model_copy(
            update={
                "content": content.model_dump(mode="json", by_alias=True),
                "target_selection": context_pack.selection.model_dump(
                    mode="json", by_alias=True
                ),
            }
        )
        request_hash = self._request_hash(normalized_command)
        proposal_id = command.proposal_id or self._stable_id(
            "proposal", command.artifact_id, command.idempotency_key
        )
        now = datetime.now(UTC).isoformat()
        with self.store._connect() as connection:
            existing = connection.execute(
                """
                SELECT * FROM artifact_mutation_proposals
                WHERE artifact_id = ? AND idempotency_key = ?
                """,
                (command.artifact_id, command.idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["request_sha256"] != request_hash:
                    self._raise_idempotency_mismatch(
                        "proposal idempotency payload mismatch"
                    )
                return self._proposal_result(existing, context)
            if artifact.current_revision_number != command.base_revision_number:
                self._raise_conflict("proposal base revision is stale")
            try:
                connection.execute(
                    """
                    INSERT INTO artifact_mutation_proposals (
                        proposal_id, workspace_id, artifact_id, base_revision_number,
                        mutation_type, content_json, content_sha256, idempotency_key,
                        summary, proposed_by_id, status, created_at_utc, request_sha256,
                        context_sha256, selection_sha256, source_session_id, source_turn_id,
                        trace_id, context_revision_id, context_purpose, target_scope_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        proposal_id,
                        context.workspace_id,
                        command.artifact_id,
                        command.base_revision_number,
                        command.mutation_type.value,
                        content_json,
                        digest,
                        command.idempotency_key,
                        command.summary,
                        context.principal_id,
                        now,
                        request_hash,
                        command.context_sha256,
                        command.selection_sha256,
                        command.source_session_id,
                        command.source_turn_id,
                        context.trace_id,
                        command.context_revision_id,
                        command.context_purpose,
                        canonical_json(command.target_selection),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ArtifactDomainError(
                    ArtifactErrorCode.ARTIFACT_REVISION_CONFLICT,
                    "proposal identity conflicts with an existing proposal",
                ) from exc
        with self.store._connect() as connection:
            stored = connection.execute(
                "SELECT * FROM artifact_mutation_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        if stored is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "stored artifact proposal is missing",
            )
        return self._proposal_result(stored, context)

    @record_artifact_evidence("artifact.apply_proposal")
    def apply_proposal(
        self,
        command: ApplyArtifactProposalCommand,
        context: OperationContext,
    ) -> ArtifactOperationResult:
        with self.store._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM artifact_mutation_proposals
                WHERE proposal_id = ? AND workspace_id = ?
                """,
                (command.proposal_id, context.workspace_id),
            ).fetchone()
        if row is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_NOT_FOUND,
                "artifact mutation proposal does not exist",
            )
        artifact = self.store.get_artifact(context.workspace_id, row["artifact_id"])
        if row["status"] == "applied" and row["applied_revision_id"]:
            approval = self._proposal_approvals.claim(
                row, context, command.approval_id
            )
            self.policy.authorize(
                ArtifactPermission.AI_APPLY,
                context,
                artifact_workspace_id=artifact.workspace_id,
                approval_granted=True,
            )
            stored = self.store.get_revision(
                context.workspace_id, artifact.artifact_id, row["applied_revision_id"]
            )
            replay = ArtifactOperationResult(
                artifact, stored.descriptor, False, "idempotent_replay"
            )
            self._proposal_approvals.complete(row, command.approval_id)
            return replay
        if row["status"] != "pending":
            self._raise_conflict("proposal is not pending")
        if (
            artifact.current_revision_number != row["base_revision_number"]
            or command.expected_revision_number != row["base_revision_number"]
        ):
            with self.store._connect() as connection:
                connection.execute(
                    """
                    UPDATE artifact_mutation_proposals
                    SET status = 'stale', completed_at_utc = ?
                    WHERE proposal_id = ? AND status = 'pending'
                    """,
                    (datetime.now(UTC).isoformat(), command.proposal_id),
                )
                connection.commit()
            self._raise_conflict("proposal base revision is stale")

        content = self._revalidate_stored_proposal(row, artifact, context)
        approval = self._proposal_approvals.claim(row, context, command.approval_id)
        self.policy.authorize(
            ArtifactPermission.AI_APPLY,
            context,
            artifact_workspace_id=artifact.workspace_id,
            approval_granted=True,
        )

        result = self.mutate(
            MutateArtifactCommand(
                artifact_id=artifact.artifact_id,
                expected_revision_number=command.expected_revision_number,
                mutation_type=row["mutation_type"],
                content=content.model_dump(mode="json", by_alias=True),
                idempotency_key=row["idempotency_key"],
                change_summary=row["summary"],
            ),
            context,
            _approval_verified=True,
            _proposal_id=command.proposal_id,
        )
        with self.store._connect() as connection:
            connection.execute(
                """
                UPDATE artifact_mutation_proposals
                SET status = 'applied', applied_revision_id = ?, completed_at_utc = ?,
                    approval_id = ?, action_hash = ?, approved_by_id = ?, applied_by_id = ?
                WHERE proposal_id = ? AND status = 'pending'
                """,
                (
                    result.revision.revision_id,
                    datetime.now(UTC).isoformat(),
                    command.approval_id,
                    row["action_hash"],
                    approval.actor,
                    context.principal_id,
                    command.proposal_id,
                ),
            )
            connection.commit()
        self._proposal_approvals.complete(row, command.approval_id)
        return result

    def _revalidate_stored_proposal(
        self,
        row: sqlite3.Row,
        artifact: ArtifactDescriptor,
        context: OperationContext,
    ) -> ArtifactContent:
        from imperaos.artifacts.context import (
            ArtifactContextRequest,
            build_artifact_context_pack,
        )

        try:
            raw_content = json.loads(row["content_json"])
            target_selection = json.loads(row["target_scope_json"])
            content = self._validate_content(
                artifact.kind,
                raw_content,
                schema_version=artifact.schema_version,
            )
            content_json = canonical_json(content)
            if hashlib.sha256(content_json.encode("utf-8")).hexdigest() != row["content_sha256"]:
                raise ValueError("proposal content hash mismatch")
            base_read = self.get(
                GetArtifactQuery(
                    artifact_id=artifact.artifact_id,
                    revision_id=row["context_revision_id"],
                ),
                context,
            )
            request = ArtifactContextRequest.model_validate(
                {
                    "artifactId": artifact.artifact_id,
                    "revisionId": row["context_revision_id"],
                    "purpose": row["context_purpose"],
                    "allowedScopes": ["metadata", "selection"],
                    "selection": target_selection,
                }
            )
            pack = build_artifact_context_pack(base_read, request)
            if (
                pack.revision_number != row["base_revision_number"]
                or pack.projection_sha256 != row["context_sha256"]
                or pack.selection_sha256 != row["selection_sha256"]
            ):
                raise ValueError("proposal context binding mismatch")
            require_scoped_replacement(
                artifact.kind,
                base_read.content.model_dump(mode="json", by_alias=True),
                content.model_dump(mode="json", by_alias=True),
                target_selection,
            )
            reconstructed = ProposeArtifactMutationCommand(
                proposal_id=row["proposal_id"],
                artifact_id=row["artifact_id"],
                base_revision_number=row["base_revision_number"],
                mutation_type=row["mutation_type"],
                content=content.model_dump(mode="json", by_alias=True),
                idempotency_key=row["idempotency_key"],
                summary=row["summary"],
                context_sha256=row["context_sha256"],
                selection_sha256=row["selection_sha256"],
                context_revision_id=row["context_revision_id"],
                context_purpose=row["context_purpose"],
                target_selection=pack.selection.model_dump(mode="json", by_alias=True),
                source_session_id=row["source_session_id"],
                source_turn_id=row["source_turn_id"],
            )
            if self._request_hash(reconstructed) != row["request_sha256"]:
                raise ValueError("proposal request hash mismatch")
        except (ArtifactDomainError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE,
                "stored artifact proposal integrity validation failed",
                details={"reasonCode": "ARTIFACT_PROPOSAL_INTEGRITY_INVALID"},
            ) from exc
        return content

    @record_artifact_evidence("artifact.history")
    def history(
        self,
        query: ArtifactHistoryQuery,
        context: OperationContext,
    ) -> ArtifactHistoryResult:
        artifact = self.store.get_artifact(context.workspace_id, query.artifact_id)
        self.policy.authorize(
            ArtifactPermission.READ,
            context,
            artifact_workspace_id=artifact.workspace_id,
        )
        offset = self._decode_cursor(query.cursor)
        revisions = self.store.list_revisions(context.workspace_id, query.artifact_id)
        page = revisions[offset : offset + query.limit + 1]
        has_more = len(page) > query.limit
        return ArtifactHistoryResult(
            items=page[: query.limit],
            next_cursor=str(offset + query.limit) if has_more else None,
        )

    @record_artifact_evidence("artifact.restore")
    def restore(
        self,
        command: RestoreArtifactCommand,
        context: OperationContext,
    ) -> ArtifactOperationResult:
        current = self.store.get_artifact(context.workspace_id, command.artifact_id)
        self.policy.authorize(
            ArtifactPermission.RESTORE,
            context,
            artifact_workspace_id=current.workspace_id,
        )
        self._require_licensed_editor(current.kind)
        request_hash = self._request_hash(command)
        replay = self._load_operation_replay(
            context.workspace_id,
            command.idempotency_key,
            "restore",
            request_hash,
        )
        if replay is not None:
            return replay
        if current.status is ArtifactStatus.ARCHIVED:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
                "archived artifacts are read-only",
            )
        source = self.store.get_revision(
            context.workspace_id, command.artifact_id, command.source_revision_id
        )
        content = self._decode_content(
            current.kind, source.content, schema_version=source.descriptor.schema_version
        )
        payload = canonical_json(content).encode("utf-8")
        revision_number = command.expected_revision_number + 1
        revision_id = self._stable_id(
            "revision", current.artifact_id, command.idempotency_key
        )
        digest = hashlib.sha256(payload).hexdigest()
        now = datetime.now(UTC)
        revision = ArtifactRevisionDescriptor(
            revision_id=revision_id,
            artifact_id=current.artifact_id,
            parent_revision_id=current.current_revision_id,
            base_revision_id=command.source_revision_id,
            revision_number=revision_number,
            schema_version=source.descriptor.schema_version,
            mutation_type=ArtifactMutationType.RESTORE,
            content_relpath=revision_content_relpath(
                context.workspace_id,
                current.artifact_id,
                revision_number,
                revision_id,
                "json",
            ),
            content_sha256=digest,
            content_size_bytes=len(payload),
            content_encoding="json",
            change_summary=command.change_summary,
            author_type=context.principal_type,
            author_id=context.principal_id,
            idempotency_key=command.idempotency_key,
            created_at_utc=now,
        )
        updated = ArtifactDescriptor.model_validate(
            {
                **current.model_dump(mode="python"),
                "current_revision_id": revision_id,
                "current_revision_number": revision_number,
                "schema_version": source.descriptor.schema_version,
                "updated_by_id": context.principal_id,
                "updated_at_utc": now,
                "etag": digest,
            }
        )
        stored = self.store.restore_revision(
            updated,
            revision,
            source_revision_id=command.source_revision_id,
            expected_revision_number=command.expected_revision_number,
            operation="restore",
            request_hash=request_hash,
        )
        operation = ArtifactOperationResult(
            stored.artifact,
            stored.revision,
            stored.created,
            stored.disposition,
        )
        return operation

    @record_artifact_evidence("artifact.archive")
    def archive(
        self,
        command: ArchiveArtifactCommand,
        context: OperationContext,
    ) -> ArtifactOperationResult:
        current = self.store.get_artifact(context.workspace_id, command.artifact_id)
        self.policy.authorize(
            ArtifactPermission.ARCHIVE,
            context,
            artifact_workspace_id=current.workspace_id,
        )
        now = datetime.now(UTC)
        archived = ArtifactDescriptor.model_validate(
            {
                **current.model_dump(mode="python"),
                "status": ArtifactStatus.ARCHIVED,
                "archived_at_utc": now,
                "updated_at_utc": now,
                "updated_by_id": context.principal_id,
            }
        )
        stored_artifact = self.store.update_artifact_metadata(
            archived,
            expected_revision_number=command.expected_revision_number,
        )
        revision = self.store.get_revision(
            context.workspace_id, current.artifact_id, current.current_revision_id
        ).descriptor
        return ArtifactOperationResult(stored_artifact, revision, False, "updated")

    @record_artifact_evidence("artifact.duplicate")
    def duplicate(
        self,
        command: DuplicateArtifactCommand,
        context: OperationContext,
    ) -> ArtifactOperationResult:
        source = self.store.get_artifact(
            context.workspace_id, command.source_artifact_id
        )
        self.policy.authorize(
            ArtifactPermission.DUPLICATE,
            context,
            artifact_workspace_id=source.workspace_id,
        )
        self._require_licensed_editor(source.kind)
        request_hash = self._request_hash(command)
        replay = self._load_operation_replay(
            context.workspace_id,
            command.idempotency_key,
            "duplicate",
            request_hash,
        )
        if replay is not None:
            return replay
        loaded = self.get(
            GetArtifactQuery(
                artifact_id=source.artifact_id,
                revision_id=command.source_revision_id,
            ),
            context,
        )
        content_input = (
            command.content_override
            if command.content_override is not None
            else loaded.content.model_dump(mode="json", by_alias=True)
        )
        content = self._validate_content(
            source.kind,
            content_input,
            schema_version=loaded.revision.schema_version,
        )
        effective_data_class = self._effective_content_data_class(
            context.workspace_id, content, source.data_class
        )
        self.policy.authorize(
            ArtifactPermission.DUPLICATE,
            context,
            artifact_workspace_id=source.workspace_id,
            current_data_class=source.data_class,
            target_data_class=effective_data_class,
        )
        payload = canonical_json(content).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        artifact_id = command.artifact_id or self._stable_id(
            "artifact", context.workspace_id, command.idempotency_key
        )
        revision_id = self._stable_id("revision", artifact_id, command.idempotency_key)
        now = datetime.now(UTC)
        revision = ArtifactRevisionDescriptor(
            revision_id=revision_id,
            artifact_id=artifact_id,
            base_revision_id=loaded.revision.revision_id,
            revision_number=1,
            schema_version=loaded.revision.schema_version,
            mutation_type=ArtifactMutationType.DUPLICATE,
            content_relpath=revision_content_relpath(
                context.workspace_id, artifact_id, 1, revision_id, "json"
            ),
            content_sha256=digest,
            content_size_bytes=len(payload),
            content_encoding="json",
            change_summary="Artifact duplicated",
            author_type=context.principal_type,
            author_id=context.principal_id,
            idempotency_key=command.idempotency_key,
            created_at_utc=now,
        )
        artifact = ArtifactDescriptor(
            artifact_id=artifact_id,
            workspace_id=context.workspace_id,
            kind=source.kind,
            title=command.title,
            status=ArtifactStatus.DRAFT,
            schema_version=loaded.revision.schema_version,
            data_class=effective_data_class,
            current_revision_id=revision_id,
            current_revision_number=1,
            source_session_id=source.source_session_id,
            source_turn_id=source.source_turn_id,
            created_by_type=context.principal_type,
            created_by_id=context.principal_id,
            updated_by_id=context.principal_id,
            created_at_utc=now,
            updated_at_utc=now,
            etag=digest,
            metadata={
                **source.metadata,
                "forkedFromArtifactId": source.artifact_id,
                "forkedFromRevisionId": loaded.revision.revision_id,
            },
        )
        stored = self.store.create_duplicate_artifact(
            artifact,
            revision,
            payload,
            source_artifact_id=source.artifact_id,
            operation="duplicate",
            request_hash=request_hash,
        )
        operation = ArtifactOperationResult(
            artifact=stored.artifact,
            revision=stored.revision,
            created=stored.created,
            disposition=stored.disposition,
        )
        return operation

    @record_artifact_evidence("artifact.asset.imported")
    def import_asset(
        self,
        command: ImportArtifactAssetCommand,
        context: OperationContext,
    ) -> ArtifactAssetImportResult:
        self.policy.authorize(
            ArtifactPermission.ASSET_IMPORT,
            context,
            artifact_workspace_id=context.workspace_id,
            target_data_class=command.data_class,
        )
        request_hash = self._request_hash(command)
        try:
            payload = base64.b64decode(command.content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID,
                "asset payload is not valid base64",
            ) from exc
        replay = self._reserve_asset_replay(
            context.workspace_id,
            command.idempotency_key,
            request_hash,
        )
        if replay is not None:
            return replay
        try:
            imported = self.assets.import_bytes(
                context.workspace_id,
                payload,
                declared_media_type=command.declared_media_type,
                data_class=command.data_class,
                created_by_id=context.principal_id,
                original_name=command.file_name,
            )
            result = ArtifactAssetImportResult(
                asset=imported.descriptor,
                disposition="deduplicated" if imported.deduplicated else "created",
            )
            self._save_asset_replay(
                context.workspace_id,
                command.idempotency_key,
                request_hash,
                result,
            )
            return result
        except Exception:
            self._release_asset_replay(
                context.workspace_id, command.idempotency_key, request_hash
            )
            raise

    @record_artifact_evidence("artifact.asset.read")
    def get_asset(
        self,
        query: GetArtifactAssetQuery,
        context: OperationContext,
    ) -> ArtifactAssetReadResult:
        descriptor = self.assets.get_descriptor(context.workspace_id, query.asset_id)
        self.policy.authorize(
            ArtifactPermission.READ,
            context,
            artifact_workspace_id=descriptor.workspace_id,
            current_data_class=descriptor.data_class,
        )
        payload = self.assets.get_bytes(context.workspace_id, query.asset_id)
        return ArtifactAssetReadResult(
            asset=descriptor,
            content_base64=base64.b64encode(payload).decode("ascii"),
        )

    @record_artifact_evidence("artifact.evidence.imported")
    def import_evidence(
        self,
        command: ImportEvidenceArtifactCommand,
        context: OperationContext,
    ) -> ArtifactOperationResult:
        self.policy.authorize(
            ArtifactPermission.IMPORT_EVIDENCE,
            context,
            artifact_workspace_id=context.workspace_id,
        )
        request_hash = self._request_hash(command)
        replay = self._load_operation_replay(
            context.workspace_id,
            command.idempotency_key,
            "import_evidence",
            request_hash,
        )
        if replay is not None:
            return replay
        source = self.evidence_resolver.resolve(context, command.evidence_id)
        if source.workspace_id != context.workspace_id:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_NOT_FOUND,
                "evidence source does not exist",
            )
        if source.content_sha256 != command.expected_sha256:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "evidence source hash does not match the requested immutable source",
                details={"classification": "evidence_hash_mismatch"},
            )
        observed_source_hash = hashlib.sha256(
            canonical_json(source.content).encode("utf-8")
        ).hexdigest()
        if observed_source_hash != source.content_sha256:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "evidence source failed integrity verification",
                details={"classification": "evidence_hash_mismatch"},
            )
        self.policy.authorize(
            ArtifactPermission.IMPORT_EVIDENCE,
            context,
            artifact_workspace_id=source.workspace_id,
            target_data_class=source.data_class,
        )
        self._require_licensed_editor(source.kind)
        self._validate_content(
            source.kind,
            source.content,
            schema_version=source.schema_version,
        )
        payload = canonical_json(source.content).encode("utf-8")
        digest = source.content_sha256
        artifact_id = command.artifact_id or self._stable_id(
            "artifact", context.workspace_id, command.idempotency_key
        )
        revision_id = self._stable_id("revision", artifact_id, command.idempotency_key)
        now = datetime.now(UTC)
        revision = ArtifactRevisionDescriptor(
            revision_id=revision_id,
            artifact_id=artifact_id,
            revision_number=1,
            schema_version=source.schema_version,
            mutation_type=ArtifactMutationType.IMPORT_EVIDENCE,
            content_relpath=revision_content_relpath(
                context.workspace_id, artifact_id, 1, revision_id, "json"
            ),
            content_sha256=digest,
            content_size_bytes=len(payload),
            content_encoding="json",
            change_summary="Verified evidence copied into editable artifact",
            author_type=PrincipalType.IMPORT,
            author_id=context.principal_id,
            idempotency_key=command.idempotency_key,
            created_at_utc=now,
        )
        artifact = ArtifactDescriptor(
            artifact_id=artifact_id,
            workspace_id=context.workspace_id,
            kind=source.kind,
            title=command.title or source.title,
            status=ArtifactStatus.DRAFT,
            schema_version=source.schema_version,
            data_class=source.data_class,
            current_revision_id=revision_id,
            current_revision_number=1,
            source_session_id=None,
            source_turn_id=None,
            created_by_type=PrincipalType.IMPORT,
            created_by_id=context.principal_id,
            updated_by_id=context.principal_id,
            created_at_utc=now,
            updated_at_utc=now,
            etag=digest,
            metadata={
                "sourceEvidenceId": source.evidence_id,
                "sourceEvidenceSha256": source.content_sha256,
                "sourceRunId": source.source_run_id,
            },
        )
        stored = self.store.create_evidence_artifact(
            artifact,
            revision,
            payload,
            source_evidence_id=source.evidence_id,
            operation="import_evidence",
            request_hash=request_hash,
        )
        return ArtifactOperationResult(
            artifact=stored.artifact,
            revision=stored.revision,
            created=stored.created,
            disposition=stored.disposition,
        )

    @record_artifact_evidence("artifact.export.started")
    def begin_export(
        self,
        command: BeginArtifactExportCommand,
        context: OperationContext,
    ) -> ArtifactExportBeginResult:
        artifact = self.store.get_artifact(context.workspace_id, command.artifact_id)
        if command.approval_id is not None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
                "artifact export approval cannot be asserted by the caller",
            )
        format_name = require_export_format(artifact.kind, command.format)
        stored_revision = self.store.get_revision(
            context.workspace_id,
            artifact.artifact_id,
            command.revision_id,
        )
        content = self._decode_content(
            artifact.kind,
            stored_revision.content,
            schema_version=stored_revision.descriptor.schema_version,
        )
        effective_data_class = self._effective_content_data_class(
            context.workspace_id, content, artifact.data_class
        )
        self.policy.authorize(
            ArtifactPermission.EXPORT,
            context,
            artifact_workspace_id=artifact.workspace_id,
            current_data_class=effective_data_class,
            approval_granted=False,
        )
        basename = canonical_export_basename(artifact, content, format_name)
        request_hash = self._request_hash(command)
        export_id = self._stable_id(
            "export", context.workspace_id, command.idempotency_key
        )
        record, created = self.store.create_export(
            export_id=export_id,
            workspace_id=context.workspace_id,
            artifact_id=artifact.artifact_id,
            revision_id=stored_revision.descriptor.revision_id,
            format_name=format_name,
            basename=basename,
            actor_type=context.principal_type.value,
            actor_id=context.principal_id,
            idempotency_key=command.idempotency_key,
            request_sha256=request_hash,
        )
        return ArtifactExportBeginResult(
            export_id=record.export_id,
            artifact_id=record.artifact_id,
            revision_id=record.revision_id,
            format=record.format,
            basename=record.basename,
            max_bytes=DEFAULT_ARTIFACT_EXPORT_MAX_BYTES,
            disposition="created" if created else "idempotent_replay",
        )

    @record_artifact_evidence("artifact.export.preflight")
    def preflight_export(
        self,
        command: PreflightArtifactExportCommand,
        context: OperationContext,
    ) -> ArtifactExportResult:
        current = self.store.get_export(context.workspace_id, command.export_id)
        artifact = self.store.get_artifact(context.workspace_id, current.artifact_id)
        stored_revision = self.store.get_revision(
            context.workspace_id, artifact.artifact_id, current.revision_id
        )
        content = self._decode_content(
            artifact.kind,
            stored_revision.content,
            schema_version=stored_revision.descriptor.schema_version,
        )
        effective_data_class = self._effective_content_data_class(
            context.workspace_id, content, artifact.data_class
        )
        self.policy.authorize(
            ArtifactPermission.EXPORT,
            context,
            artifact_workspace_id=artifact.workspace_id,
            current_data_class=effective_data_class,
            approval_granted=False,
        )
        record, updated = self.store.preflight_export(
            workspace_id=context.workspace_id,
            export_id=current.export_id,
            actor_type=context.principal_type.value,
            actor_id=context.principal_id,
            basename=command.basename,
            sha256=command.sha256,
            size_bytes=command.size_bytes,
        )
        return ArtifactExportResult(
            export_id=record.export_id,
            artifact_id=record.artifact_id,
            revision_id=record.revision_id,
            format=record.format,
            status=record.status,
            basename=record.basename,
            sha256=record.sha256,
            size_bytes=record.size_bytes,
            reason_code=record.reason_code,
            disposition="updated" if updated else "idempotent_replay",
        )

    @record_artifact_evidence("artifact.export.completed")
    def commit_export(
        self,
        command: CommitArtifactExportCommand,
        context: OperationContext,
    ) -> ArtifactExportResult:
        current = self.store.get_export(context.workspace_id, command.export_id)
        if (
            command.basename != current.basename
            or command.sha256 != current.sha256
            or command.size_bytes != current.size_bytes
        ):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_EXPORT_FAILED,
                "artifact export bytes were not preflight-authorized",
            )
        record, updated = self.store.transition_export(
            workspace_id=context.workspace_id,
            export_id=current.export_id,
            actor_type=context.principal_type.value,
            actor_id=context.principal_id,
            status="completed",
            basename=command.basename,
            sha256=command.sha256,
            size_bytes=command.size_bytes,
            reason_code=None,
            idempotency_key=command.idempotency_key,
            request_sha256=self._request_hash(command),
        )
        return ArtifactExportResult(
            export_id=record.export_id,
            artifact_id=record.artifact_id,
            revision_id=record.revision_id,
            format=record.format,
            status=record.status,
            basename=record.basename,
            sha256=record.sha256,
            size_bytes=record.size_bytes,
            reason_code=record.reason_code,
            disposition="updated" if updated else "idempotent_replay",
        )

    @record_artifact_evidence("artifact.export.cancelled")
    def cancel_export(
        self,
        command: CancelArtifactExportCommand,
        context: OperationContext,
    ) -> ArtifactExportResult:
        current = self.store.get_export(context.workspace_id, command.export_id)
        artifact = self.store.get_artifact(context.workspace_id, current.artifact_id)
        self.policy.authorize(
            ArtifactPermission.EXPORT,
            context,
            artifact_workspace_id=artifact.workspace_id,
        )
        if (
            command.reason == "user_cancelled"
            and current.sha256 is not None
            and current.size_bytes is not None
        ):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_EXPORT_FAILED,
                "preflighted artifact export requires terminal completion",
            )
        status = "failed" if command.reason != "user_cancelled" else "cancelled"
        record, updated = self.store.transition_export(
            workspace_id=context.workspace_id,
            export_id=current.export_id,
            actor_type=context.principal_type.value,
            actor_id=context.principal_id,
            status=status,
            basename=current.basename,
            sha256=current.sha256,
            size_bytes=current.size_bytes,
            reason_code=command.reason,
            idempotency_key=command.idempotency_key,
            request_sha256=self._request_hash(command),
        )
        return ArtifactExportResult(
            export_id=record.export_id,
            artifact_id=record.artifact_id,
            revision_id=record.revision_id,
            format=record.format,
            status=record.status,
            basename=record.basename,
            sha256=record.sha256,
            size_bytes=record.size_bytes,
            reason_code=record.reason_code,
            disposition="updated" if updated else "idempotent_replay",
        )

    @record_artifact_evidence("artifact.form.submitted")
    def submit_form(
        self,
        command: SubmitArtifactFormCommand,
        context: OperationContext,
    ) -> ArtifactFormSubmissionResult:
        if command.persistence_policy != "none":
            raise ArtifactDomainError(
                ArtifactErrorCode.FORM_SENSITIVE_PERSISTENCE_DENIED,
                "form response persistence is disabled",
            )
        artifact = self.store.get_artifact(context.workspace_id, command.artifact_id)
        self.policy.authorize(
            ArtifactPermission.FORM_SUBMIT,
            context,
            artifact_workspace_id=artifact.workspace_id,
            current_data_class=artifact.data_class,
        )
        if artifact.kind is not ArtifactKind.FORM:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID,
                "form submission requires a form artifact",
            )
        stored_revision = self.store.get_revision(
            context.workspace_id,
            artifact.artifact_id,
            command.schema_revision_id,
        )
        content = self._decode_content(artifact.kind, stored_revision.content)
        if not isinstance(content, FormContentV1):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "stored form schema has an invalid type",
            )
        validate_form_response(content.json_schema, command.response)
        response_sha256 = hashlib.sha256(
            canonical_json(command.response).encode("utf-8")
        ).hexdigest()
        submission_id = self._stable_id(
            "submission", artifact.artifact_id, command.idempotency_key
        )
        pending = content.behavior.external_continuation == "approval_required"
        created = self.store.create_form_submission(
            submission_id=submission_id,
            workspace_id=context.workspace_id,
            artifact_id=artifact.artifact_id,
            schema_revision_id=command.schema_revision_id,
            principal_id=context.principal_id,
            persistence_policy=command.persistence_policy,
            response_sha256=response_sha256,
            idempotency_key=command.idempotency_key,
            continuation_required=pending,
        )
        approval = None
        if pending:
            gateway = self._continuation_gateway
            if gateway is _DEFAULT_CONTINUATION_GATEWAY:
                gateway = ArtifactFormContinuationGateway(self._approval_store)
                self._continuation_gateway = gateway
            if not isinstance(gateway, ArtifactFormContinuationGateway):
                raise ArtifactDomainError(
                    ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE,
                    "form continuation approval is unavailable",
                )
            try:
                approval = gateway.request_approval(
                    context=context,
                    artifact_id=artifact.artifact_id,
                    schema_revision_id=command.schema_revision_id,
                    submission_id=submission_id,
                    response_sha256=response_sha256,
                    idempotency_key=command.idempotency_key,
                )
                self.store.mark_form_continuation_ticketed(
                    submission_id=submission_id,
                    workspace_id=context.workspace_id,
                    approval_id=approval.approval_id,
                    action_hash=approval.action_hash,
                )
            except ArtifactDomainError as exc:
                self.store.mark_form_continuation_failed(
                    submission_id=submission_id,
                    workspace_id=context.workspace_id,
                    error_code=exc.code.value,
                )
                raise
            except Exception as exc:
                self.store.mark_form_continuation_failed(
                    submission_id=submission_id,
                    workspace_id=context.workspace_id,
                    error_code=ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE.value,
                )
                raise ArtifactDomainError(
                    ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE,
                    "form continuation approval is unavailable",
                ) from exc
        return ArtifactFormSubmissionResult(
            submission_id=submission_id,
            artifact_id=artifact.artifact_id,
            schema_revision_id=command.schema_revision_id,
            status="pending_continuation" if pending else "accepted",
            response_sha256=response_sha256,
            continuation_action="require_approval" if pending else "none",
            approval_id=approval.approval_id if approval is not None else None,
            reason_code=(
                "FORM_CONTINUATION_APPROVAL_REQUIRED"
                if pending
                else "FORM_CONTINUATION_NOT_REQUIRED"
            ),
            action_hash=approval.action_hash if approval is not None else None,
            disposition="created" if created else "idempotent_replay",
        )

    @staticmethod
    def _validate_content(
        kind: ArtifactKind,
        payload: object,
        *,
        schema_version: int | None = None,
    ) -> ArtifactContent:
        try:
            return validate_artifact_content(kind, payload, schema_version=schema_version)
        except ArtifactDomainError:
            raise
        except (ValidationError, ValueError, TypeError) as exc:
            code = (
                ArtifactErrorCode.FORM_SCHEMA_UNSAFE
                if kind is ArtifactKind.FORM
                else ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID
            )
            raise ArtifactDomainError(
                code,
                (
                    "form schema is outside the safe supported subset"
                    if kind is ArtifactKind.FORM
                    else "artifact content does not match its versioned schema"
                ),
            ) from exc

    def _decode_content(
        self,
        kind: ArtifactKind,
        payload: bytes,
        *,
        schema_version: int | None = None,
    ) -> ArtifactContent:
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "stored artifact content is not valid JSON",
            ) from exc
        return self._validate_content(kind, decoded, schema_version=schema_version)

    @staticmethod
    def _request_hash(command: ArtifactModel) -> str:
        return hashlib.sha256(canonical_json(command).encode("utf-8")).hexdigest()

    @staticmethod
    def _stable_id(prefix: str, *parts: str) -> str:
        digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]
        return f"{prefix}-{digest}"

    @staticmethod
    def _decode_cursor(cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            offset = int(cursor)
        except ValueError as exc:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID,
                "artifact cursor is invalid",
            ) from exc
        if offset < 0:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID,
                "artifact cursor is invalid",
            )
        return offset

    def _load_operation_replay(
        self,
        workspace_id: str,
        idempotency_key: str,
        operation: str,
        request_hash: str,
    ) -> ArtifactOperationResult | None:
        with self.store._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM artifact_operation_dedup
                WHERE workspace_id = ? AND idempotency_key = ?
                """,
                (workspace_id, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        if row["operation"] != operation or row["request_sha256"] != request_hash:
            self._raise_idempotency_mismatch("idempotency key payload mismatch")
        result = json.loads(row["result_json"])
        artifact = self.store.get_artifact(workspace_id, result["artifactId"])
        revision = self.store.get_revision(
            workspace_id, artifact.artifact_id, result["revisionId"]
        ).descriptor
        return ArtifactOperationResult(artifact, revision, False, "idempotent_replay")

    def _save_operation_replay(
        self,
        workspace_id: str,
        idempotency_key: str,
        operation: str,
        request_hash: str,
        result: ArtifactOperationResult,
    ) -> None:
        result_json = canonical_json(
            {
                "artifactId": result.artifact.artifact_id,
                "revisionId": result.revision.revision_id,
            }
        )
        with self.store._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO artifact_operation_dedup (
                    workspace_id, idempotency_key, operation, request_sha256,
                    result_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    workspace_id,
                    idempotency_key,
                    operation,
                    request_hash,
                    result_json,
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()

    def _load_asset_replay(
        self,
        workspace_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> ArtifactAssetImportResult | None:
        with self.store._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM artifact_operation_dedup
                WHERE workspace_id = ? AND idempotency_key = ?
                """,
                (workspace_id, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        if row["operation"] != "asset_import" or row["request_sha256"] != request_hash:
            self._raise_idempotency_mismatch("idempotency key payload mismatch")
        parsed = json.loads(row["result_json"])
        descriptor = self.assets.get_descriptor(workspace_id, parsed["assetId"])
        return ArtifactAssetImportResult(
            asset=descriptor,
            disposition="idempotent_replay",
        )

    def _reserve_asset_replay(
        self,
        workspace_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> ArtifactAssetImportResult | None:
        with self.store._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT * FROM artifact_operation_dedup
                    WHERE workspace_id = ? AND idempotency_key = ?
                    """,
                    (workspace_id, idempotency_key),
                ).fetchone()
                if row is not None:
                    if (
                        row["operation"] != "asset_import"
                        or row["request_sha256"] != request_hash
                    ):
                        self._raise_idempotency_mismatch(
                            "idempotency key payload mismatch"
                        )
                    parsed = json.loads(row["result_json"])
                    if parsed.get("state") == "pending":
                        expires_at = (
                            datetime.fromisoformat(row["expires_at_utc"])
                            if row["expires_at_utc"] is not None
                            else None
                        )
                        if expires_at is None or expires_at > datetime.now(UTC):
                            self._raise_conflict("asset import is already in progress")
                        connection.execute(
                            """
                            DELETE FROM artifact_operation_dedup
                            WHERE workspace_id = ? AND idempotency_key = ?
                            """,
                            (workspace_id, idempotency_key),
                        )
                        row = None
                if row is not None:
                    parsed = json.loads(row["result_json"])
                    descriptor = self.assets.get_descriptor(
                        workspace_id, parsed["assetId"]
                    )
                    connection.commit()
                    return ArtifactAssetImportResult(
                        asset=descriptor,
                        disposition="idempotent_replay",
                    )
                connection.execute(
                    """
                    INSERT INTO artifact_operation_dedup (
                        workspace_id, idempotency_key, operation, request_sha256,
                        result_json, created_at_utc, expires_at_utc
                    ) VALUES (?, ?, 'asset_import', ?, ?, ?, ?)
                    """,
                    (
                        workspace_id,
                        idempotency_key,
                        request_hash,
                        canonical_json({"state": "pending"}),
                        datetime.now(UTC).isoformat(),
                        (datetime.now(UTC) + _ASSET_IMPORT_RESERVATION_TTL).isoformat(),
                    ),
                )
                connection.commit()
                return None
            except Exception:
                connection.rollback()
                raise

    def _save_asset_replay(
        self,
        workspace_id: str,
        idempotency_key: str,
        request_hash: str,
        result: ArtifactAssetImportResult,
    ) -> None:
        with self.store._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """
                    SELECT operation, request_sha256, result_json
                    FROM artifact_operation_dedup
                    WHERE workspace_id = ? AND idempotency_key = ?
                    """,
                    (workspace_id, idempotency_key),
                ).fetchone()
                if existing is None:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                        "asset import reservation disappeared",
                    )
                if (
                    existing["operation"] != "asset_import"
                    or existing["request_sha256"] != request_hash
                ):
                    self._raise_idempotency_mismatch(
                        "idempotency key payload mismatch"
                    )
                parsed = json.loads(existing["result_json"])
                if parsed.get("state") != "pending":
                    connection.commit()
                    return
                connection.execute(
                    """
                    UPDATE artifact_operation_dedup
                    SET result_json = ?, expires_at_utc = NULL
                    WHERE workspace_id = ? AND idempotency_key = ?
                    """,
                    (
                        canonical_json({"assetId": result.asset.asset_id}),
                        workspace_id,
                        idempotency_key,
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _release_asset_replay(
        self,
        workspace_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> None:
        with self.store._connect() as connection:
            connection.execute(
                """
                DELETE FROM artifact_operation_dedup
                WHERE workspace_id = ? AND idempotency_key = ?
                  AND operation = 'asset_import' AND request_sha256 = ?
                  AND result_json = ?
                """,
                (
                    workspace_id,
                    idempotency_key,
                    request_hash,
                    canonical_json({"state": "pending"}),
                ),
            )
            connection.commit()

    def _effective_content_data_class(
        self,
        workspace_id: str,
        content: ArtifactContent,
        base: ArtifactDataClass,
    ) -> ArtifactDataClass:
        effective = base
        for asset_id in getattr(content, "asset_ids", ()):
            attached = self.assets.get_descriptor(workspace_id, asset_id)
            if can_transition_data_class(effective, attached.data_class):
                effective = attached.data_class
        return effective

    def _proposal_result(
        self,
        row: sqlite3.Row,
        context: OperationContext,
    ) -> ArtifactMutationProposalResult:
        approval = self._proposal_approvals.request_approval(row, context)
        with self.store._connect() as connection:
            connection.execute(
                """
                UPDATE artifact_mutation_proposals
                SET approval_id = ?, action_hash = ?
                WHERE proposal_id = ?
                  AND (approval_id IS NULL OR approval_id = ?)
                  AND (action_hash IS NULL OR action_hash = ?)
                """,
                (
                    approval.approval_id,
                    approval.action_hash,
                    row["proposal_id"],
                    approval.approval_id,
                    approval.action_hash,
                ),
            )
            connection.commit()
        return ArtifactMutationProposalResult(
            row["proposal_id"],
            row["artifact_id"],
            row["base_revision_number"],
            row["status"],
            row["content_sha256"],
            row["summary"],
            approval.approval_id,
            approval.action_hash,
        )

    @staticmethod
    def _raise_conflict(message: str) -> None:
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_REVISION_CONFLICT,
            message,
        )

    @staticmethod
    def _raise_idempotency_mismatch(message: str) -> None:
        raise ArtifactDomainError(
            ArtifactErrorCode.IDEMPOTENCY_KEY_REUSE_MISMATCH,
            message,
        )
