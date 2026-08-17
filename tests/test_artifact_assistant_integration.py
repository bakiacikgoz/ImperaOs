from __future__ import annotations

from pathlib import Path

import pytest

from imperaos.artifacts.assistant import (
    ArtifactAssistantProviderResponse,
    ArtifactAssistantToolCall,
    ArtifactAssistantToolLoop,
    CoreLlmArtifactProvider,
    _require_grant_bound_proposal,
    extract_artifact_context_request,
)
from imperaos.artifacts.commands import CreateArtifactCommand, GetArtifactQuery
from imperaos.artifacts.context import ArtifactContextRequest, build_artifact_context_pack
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    OperationContext,
    PrincipalType,
)
from imperaos.artifacts.service import ArtifactService
from imperaos.artifacts.tools import PUBLIC_ARTIFACT_TOOL_NAMES, ArtifactToolRegistry
from imperaos.cli import _artifact_tool_stream_event, _effective_artifact_prompt_data_class
from imperaos.model_providers.errors import ProviderGenerationError
from imperaos.model_providers.models import DataClass


def _context() -> OperationContext:
    return OperationContext(
        workspace_id="workspace-1",
        principal_type=PrincipalType.ASSISTANT,
        principal_id="user-1",
        roles=("artifact_admin",),
        request_id="assistant-turn-1",
    )


def _document() -> dict[str, object]:
    return {
        "kind": "document",
        "schemaVersion": 1,
        "language": "en",
        "pageMode": "document",
        "blocks": [
            {
                "id": "block-1",
                "type": "paragraph",
                "content": [{"type": "text", "text": "bounded context"}],
            }
        ],
    }


class FakeArtifactProvider:
    def __init__(self, revision_id: str) -> None:
        self.calls: list[tuple[tuple[dict[str, object], ...], tuple[object, ...]]] = []
        self.revision_id = revision_id

    def complete(self, messages, tools):
        self.calls.append((messages, tools))
        if len(self.calls) == 1:
            return ArtifactAssistantProviderResponse(
                tool_call=ArtifactAssistantToolCall(
                    call_id="call-1",
                    name="artifact.get_context",
                    arguments={
                        "artifactId": "artifact-1",
                        "revisionId": self.revision_id,
                        "purpose": "explain",
                        "allowedScopes": ["metadata", "selection"],
                        "selection": {"kind": "document", "blockIds": ["block-1"]},
                    },
                )
            )
        return ArtifactAssistantProviderResponse(final_text="The selected block is ready.")


def test_artifact_assistant_loop_exposes_exact_tools_and_invokes_results(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    created = service.create(
        CreateArtifactCommand(
            artifact_id="artifact-1",
            kind=ArtifactKind.DOCUMENT,
            title="Brief",
            data_class=ArtifactDataClass.INTERNAL,
            content=_document(),
            idempotency_key="create-1",
        ),
        _context(),
    )
    provider = FakeArtifactProvider(created.revision.revision_id)
    loop = ArtifactAssistantToolLoop(ArtifactToolRegistry(service), max_tool_calls=2)

    result = loop.run(
        provider,
        prompt="Explain the selected block.",
        context=_context(),
        initial_context={
            "artifactId": "artifact-1",
            "revisionId": created.revision.revision_id,
            "purpose": "explain",
            "allowedScopes": ["metadata", "selection"],
            "selection": {"kind": "document", "blockIds": ["block-1"]},
        },
    )

    assert result.final_text == "The selected block is ready."
    assert tuple(tool.name for tool in provider.calls[0][1]) == PUBLIC_ARTIFACT_TOOL_NAMES
    assert [event["toolName"] for event in result.events] == [
        "artifact.get_context",
        "artifact.get_context",
    ]
    assert all("projection" not in event for event in result.events)
    assert "bounded context" in str(provider.calls[-1][0])
    assert "canonicalProjection" not in str(provider.calls[-1][0])


def test_artifact_tool_execution_metadata_is_internal_and_fail_closed(tmp_path: Path) -> None:
    registry = ArtifactToolRegistry(ArtifactService(tmp_path / "artifact-root"))
    assert all(not tool.mutating for tool in registry.provider_tools())
    assert {
        name
        for name in registry.names
        if registry.execution_metadata(name).persists_state
    } == {
        "artifact.create_draft",
        "artifact.propose_mutation",
        "artifact.request_form",
    }
    with pytest.raises(ArtifactDomainError):
        registry.execution_metadata("artifact.not_public")


def test_model_cannot_expand_the_trusted_context_grant(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    first = service.create(
        CreateArtifactCommand(
            artifact_id="artifact-1", kind="document", title="First", data_class="internal",
            content=_document(), idempotency_key="create-first",
        ),
        _context(),
    )
    second = service.create(
        CreateArtifactCommand(
            artifact_id="artifact-2", kind="document", title="Second", data_class="internal",
            content=_document(), idempotency_key="create-second",
        ),
        _context(),
    )

    class ExpandingProvider:
        def complete(self, messages, tools):
            del messages, tools
            return ArtifactAssistantProviderResponse(
                tool_call=ArtifactAssistantToolCall(
                    call_id="expand-1",
                    name="artifact.get_context",
                    arguments={
                        "artifactId": "artifact-2",
                        "revisionId": second.revision.revision_id,
                        "purpose": "explain",
                        "allowedScopes": ["metadata"],
                    },
                )
            )

    with pytest.raises(ArtifactDomainError) as caught:
        ArtifactAssistantToolLoop(ArtifactToolRegistry(service)).run(
            ExpandingProvider(),
            prompt="Explain only the authorized artifact.",
            context=_context(),
            initial_context={
                "artifactId": "artifact-1",
                "revisionId": first.revision.revision_id,
                "purpose": "explain",
                "allowedScopes": ["metadata"],
            },
        )
    assert caught.value.code is ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED
    assert caught.value.details["reasonCode"] == "ARTIFACT_CONTEXT_GRANT_EXCEEDED"


def test_proposal_base_revision_is_bound_to_the_context_grant(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    created = service.create(
        CreateArtifactCommand(
            artifact_id="artifact-1",
            kind="document",
            title="Bound revision",
            data_class="internal",
            content=_document(),
            idempotency_key="create-bound-revision",
        ),
        _context(),
    )
    grant = build_artifact_context_pack(
        service.get(
            GetArtifactQuery(
                artifact_id="artifact-1", revision_id=created.revision.revision_id
            ),
            _context(),
        ),
        ArtifactContextRequest(
            artifact_id="artifact-1",
            revision_id=created.revision.revision_id,
            purpose="transform",
            allowed_scopes=("metadata",),
        ),
    )

    with pytest.raises(ArtifactDomainError) as caught:
        _require_grant_bound_proposal(
            grant,
            {
                "artifactId": "artifact-1",
                "baseRevisionNumber": 2,
                "contextSha256": grant.projection_sha256,
                "selectionSha256": grant.selection_sha256,
            },
        )
    assert caught.value.details["reasonCode"] == "ARTIFACT_CONTEXT_GRANT_EXCEEDED"


def test_derived_draft_inherits_the_turn_classification_floor(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    source = service.create(
        CreateArtifactCommand(
            artifact_id="artifact-source", kind="document", title="Source",
            data_class="confidential", content=_document(), idempotency_key="create-source",
        ),
        _context(),
    )

    class DraftProvider:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, messages, tools):
            del messages, tools
            self.calls += 1
            if self.calls == 1:
                return ArtifactAssistantProviderResponse(
                    tool_call=ArtifactAssistantToolCall(
                        call_id="draft-1",
                        name="artifact.create_draft",
                        arguments={
                            "artifactId": "artifact-derived",
                            "kind": "document",
                            "title": "Derived",
                            "dataClass": "public",
                            "content": _document(),
                            "idempotencyKey": "create-derived",
                        },
                    )
                )
            return ArtifactAssistantProviderResponse(final_text="Created.")

    result = ArtifactAssistantToolLoop(ArtifactToolRegistry(service)).run(
        DraftProvider(),
        prompt="Create a derived draft.",
        context=_context(),
        initial_context={
            "artifactId": source.artifact.artifact_id,
            "revisionId": source.revision.revision_id,
            "purpose": "transform",
            "allowedScopes": ["metadata"],
        },
    )

    assert result.events[-1]["dataClass"] == "confidential"
    assert (
        service.store.get_artifact("workspace-1", "artifact-derived").data_class.value
        == "confidential"
    )


def test_accumulated_provider_context_has_one_hard_turn_budget(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    document = _document()
    document["blocks"][0]["content"] = [{"type": "text", "text": "x" * 20_000}]
    source = service.create(
        CreateArtifactCommand(
            artifact_id="artifact-large", kind="document", title="Large", data_class="internal",
            content=document, idempotency_key="create-large",
        ),
        _context(),
    )
    request = {
        "artifactId": source.artifact.artifact_id,
        "revisionId": source.revision.revision_id,
        "purpose": "explain",
        "allowedScopes": ["metadata", "selection"],
        "selection": {"kind": "document", "blockIds": ["block-1"]},
    }

    class RepeatingProvider:
        def complete(self, messages, tools):
            del messages, tools
            return ArtifactAssistantProviderResponse(
                tool_call=ArtifactAssistantToolCall(
                    call_id="repeat-1", name="artifact.get_context", arguments=request,
                )
            )

    with pytest.raises(ArtifactDomainError) as caught:
        ArtifactAssistantToolLoop(ArtifactToolRegistry(service)).run(
            RepeatingProvider(), prompt="Explain.", context=_context(), initial_context=request,
        )
    assert caught.value.code is ArtifactErrorCode.ARTIFACT_CONTENT_TOO_LARGE
    assert caught.value.details["reasonCode"] == "ARTIFACT_CONTEXT_BUDGET_EXCEEDED"


def test_oversized_mutating_tool_call_is_rejected_before_side_effects(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    oversized = _document()
    oversized["blocks"][0]["content"] = [{"type": "text", "text": "x" * 40_000}]

    class OversizedDraftProvider:
        def complete(self, messages, tools):
            del messages, tools
            return ArtifactAssistantProviderResponse(
                tool_call=ArtifactAssistantToolCall(
                    call_id="oversized-draft",
                    name="artifact.create_draft",
                    arguments={
                        "artifactId": "artifact-oversized",
                        "kind": "document",
                        "title": "Oversized",
                        "dataClass": "internal",
                        "content": oversized,
                        "idempotencyKey": "oversized-draft",
                    },
                )
            )

    with pytest.raises(ArtifactDomainError) as caught:
        ArtifactAssistantToolLoop(ArtifactToolRegistry(service)).run(
            OversizedDraftProvider(),
            prompt="Create a draft.",
            context=_context(),
        )

    assert caught.value.details["reasonCode"] == "ARTIFACT_CONTEXT_BUDGET_EXCEEDED"
    with pytest.raises(ArtifactDomainError) as missing:
        service.store.get_artifact("workspace-1", "artifact-oversized")
    assert missing.value.code is ArtifactErrorCode.ARTIFACT_NOT_FOUND


def test_multibyte_dynamic_content_uses_conservative_token_bound(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    content = _document()
    content["blocks"][0]["content"] = [{"type": "text", "text": "🙂" * 5_000}]

    class MultibyteProvider:
        def complete(self, messages, tools):
            del messages, tools
            return ArtifactAssistantProviderResponse(
                tool_call=ArtifactAssistantToolCall(
                    call_id="multibyte-draft",
                    name="artifact.create_draft",
                    arguments={
                        "artifactId": "artifact-multibyte",
                        "kind": "document",
                        "title": "Multibyte",
                        "dataClass": "internal",
                        "content": content,
                        "idempotencyKey": "multibyte-draft",
                    },
                )
            )

    with pytest.raises(ArtifactDomainError) as caught:
        ArtifactAssistantToolLoop(ArtifactToolRegistry(service)).run(
            MultibyteProvider(), prompt="Create a draft.", context=_context()
        )
    assert caught.value.details["reasonCode"] == "ARTIFACT_CONTEXT_BUDGET_EXCEEDED"
    with pytest.raises(ArtifactDomainError):
        service.store.get_artifact("workspace-1", "artifact-multibyte")


def test_mutating_tool_result_reserve_is_checked_before_registry_invoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ArtifactService(tmp_path / "artifact-root")

    class DraftProvider:
        def complete(self, messages, tools):
            del messages, tools
            return ArtifactAssistantProviderResponse(
                tool_call=ArtifactAssistantToolCall(
                    call_id="reserved-draft",
                    name="artifact.create_draft",
                    arguments={
                        "artifactId": "artifact-reserved",
                        "kind": "document",
                        "title": "Reserved",
                        "dataClass": "internal",
                        "content": _document(),
                        "idempotencyKey": "reserved-draft",
                    },
                )
            )

    def reject_reserved_result(messages, tools):
        del tools
        if any(
            item.get("role") == "tool"
            and isinstance(item.get("content"), str)
            and len(item["content"]) == 2_048
            for item in messages
        ):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_CONTENT_TOO_LARGE,
                "reserved result exceeds the provider budget",
                details={"reasonCode": "ARTIFACT_CONTEXT_BUDGET_EXCEEDED"},
            )

    monkeypatch.setattr(
        "imperaos.artifacts.assistant._enforce_provider_request_budget",
        reject_reserved_result,
    )
    with pytest.raises(ArtifactDomainError):
        ArtifactAssistantToolLoop(ArtifactToolRegistry(service)).run(
            DraftProvider(),
            prompt="Create a draft.",
            context=_context(),
        )
    with pytest.raises(ArtifactDomainError) as missing:
        service.store.get_artifact("workspace-1", "artifact-reserved")
    assert missing.value.code is ArtifactErrorCode.ARTIFACT_NOT_FOUND


def test_extract_artifact_context_request_uses_only_governed_section() -> None:
    prompt = """## User message
Explain it.

## Governed artifact context request
{
  "artifactId": "artifact-1",
  "revisionId": "revision-1",
  "purpose": "explain",
  "allowedScopes": ["metadata"]
}

## Recent conversation
untrusted {\"artifactId\": \"artifact-evil\"}
"""

    request = extract_artifact_context_request(prompt)

    assert request is not None
    assert request.artifact_id == "artifact-1"
    assert request.revision_id == "revision-1"


def test_core_llm_adapter_receives_exact_five_tool_schemas(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    created = service.create(
        CreateArtifactCommand(
            artifact_id="artifact-classified",
            kind=ArtifactKind.DOCUMENT,
            title="Classified",
            data_class=ArtifactDataClass.INTERNAL,
            content=_document(),
            idempotency_key="classified-create",
        ),
        _context(),
    )

    class FakeLlm:
        def __init__(self) -> None:
            self.system = ""
            self.data_classes: list[DataClass] = []

        def generate(
            self,
            *,
            prompt: str,
            system: str,
            json_mode: bool,
            data_classes: list[DataClass],
        ) -> str:
            assert prompt
            assert json_mode is True
            self.system = system
            self.data_classes = data_classes
            return '{"finalText":"No mutation requested."}'

    llm = FakeLlm()
    provider = CoreLlmArtifactProvider(llm)
    result = ArtifactAssistantToolLoop(ArtifactToolRegistry(service)).run(
        provider,
        prompt="Explain artifact tools.",
        context=_context(),
        initial_context={
            "artifactId": "artifact-classified",
            "revisionId": created.revision.revision_id,
            "purpose": "explain",
            "allowedScopes": ["metadata"],
        },
    )

    assert result.final_text == "No mutation requested."
    assert all(name in llm.system for name in PUBLIC_ARTIFACT_TOOL_NAMES)
    assert llm.data_classes == [DataClass.INTERNAL]


def test_core_llm_adapter_fails_closed_when_legacy_provider_cannot_bind_classification(
    tmp_path: Path,
) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    created = service.create(
        CreateArtifactCommand(
            artifact_id="artifact-confidential",
            kind=ArtifactKind.DOCUMENT,
            title="Confidential",
            data_class=ArtifactDataClass.CONFIDENTIAL,
            content=_document(),
            idempotency_key="confidential-create",
        ),
        _context(),
    )

    class LegacyLlm:
        def generate(self, *, prompt: str, system: str, json_mode: bool) -> str:
            raise AssertionError("classified content must not reach a legacy provider")

    with pytest.raises(ProviderGenerationError, match="PROVIDER_DATA_BOUNDARY_DENIED"):
        ArtifactAssistantToolLoop(ArtifactToolRegistry(service)).run(
            CoreLlmArtifactProvider(LegacyLlm()),
            prompt="Explain confidential artifact.",
            context=_context(),
            initial_context={
                "artifactId": "artifact-confidential",
                "revisionId": created.revision.revision_id,
                "purpose": "explain",
                "allowedScopes": ["metadata"],
            },
        )


def test_governed_tool_summaries_map_to_typed_renderer_events() -> None:
    proposal = _artifact_tool_stream_event(
        {
            "toolName": "artifact.propose_mutation",
            "status": "approval_required",
            "artifactId": "artifact-1",
            "proposalId": "proposal-1",
            "approvalId": "approval-1",
            "actionHash": "a" * 64,
            "baseRevisionNumber": 2,
            "summary": "Review this change",
        }
    )
    form = _artifact_tool_stream_event(
        {
            "toolName": "artifact.request_form",
            "status": "form_requested",
            "artifactId": "form-1",
            "revisionId": "revision-1",
        }
    )

    assert proposal["event"] == "artifact_patch_proposed"
    assert proposal["data"]["actionHash"] == "a" * 64
    assert proposal["data"]["baseRevisionNumber"] == 2
    assert form["event"] == "form_requested"


def test_core_loop_can_create_a_classified_draft_without_active_artifact_context(
    tmp_path: Path,
) -> None:
    service = ArtifactService(tmp_path / "artifact-root")

    class SequencedLlm:
        def __init__(self) -> None:
            self.data_classes: list[list[DataClass]] = []

        def generate(
            self,
            *,
            prompt: str,
            system: str,
            json_mode: bool,
            data_classes: list[DataClass],
        ) -> str:
            del prompt, system, json_mode
            self.data_classes.append(data_classes)
            if len(self.data_classes) == 1:
                return """{
                  "toolCall": {
                    "callId": "create-1",
                    "name": "artifact.create_draft",
                    "arguments": {
                      "artifactId": "artifact-new",
                      "kind": "document",
                      "title": "New draft",
                      "dataClass": "internal",
                      "content": {
                        "kind": "document",
                        "schemaVersion": 1,
                        "language": "en",
                        "pageMode": "document",
                        "blocks": []
                      },
                      "idempotencyKey": "assistant-create-1"
                    }
                  }
                }"""
            return '{"finalText":"Draft created."}'

    llm = SequencedLlm()
    result = ArtifactAssistantToolLoop(ArtifactToolRegistry(service)).run(
        CoreLlmArtifactProvider(llm),
        prompt="Create a document draft.",
        context=_context(),
        initial_context=None,
    )

    assert result.final_text == "Draft created."
    assert result.events[0]["toolName"] == "artifact.create_draft"
    assert result.events[0]["kind"] == "document"
    assert llm.data_classes == [[DataClass.PUBLIC], [DataClass.INTERNAL]]


def test_core_loop_binds_trusted_prompt_classification_before_first_provider_call(
    tmp_path: Path,
) -> None:
    service = ArtifactService(tmp_path / "artifact-root")

    class ClassifiedLlm:
        def __init__(self) -> None:
            self.data_classes: list[list[DataClass]] = []

        def generate(
            self,
            *,
            prompt: str,
            system: str,
            json_mode: bool,
            data_classes: list[DataClass],
        ) -> str:
            del prompt, system, json_mode
            self.data_classes.append(data_classes)
            return '{"finalText":"Safe."}'

    llm = ClassifiedLlm()
    ArtifactAssistantToolLoop(ArtifactToolRegistry(service)).run(
        CoreLlmArtifactProvider(llm),
        prompt="Summarize trusted operational context.",
        context=_context(),
        initial_context=None,
        prompt_data_class=ArtifactDataClass.CONFIDENTIAL,
    )

    assert llm.data_classes == [[DataClass.CONFIDENTIAL]]


@pytest.mark.parametrize("requested", list(ArtifactDataClass))
def test_governed_artifact_runtime_uses_regulated_provider_ceiling(
    requested: ArtifactDataClass,
) -> None:
    assert (
        _effective_artifact_prompt_data_class(
            artifact_runtime_present=True,
            requested=requested,
        )
        is ArtifactDataClass.REGULATED
    )
