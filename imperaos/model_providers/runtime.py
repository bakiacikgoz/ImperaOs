from __future__ import annotations

from uuid import uuid4

from imperaos.model_providers.adapters.adapter_factory import ProviderAdapterFactory
from imperaos.model_providers.envelope import (
    ProviderCallEnvelopeWriter,
    build_provider_call_envelope,
)
from imperaos.model_providers.errors import ProviderGenerationError, ProviderNotFound
from imperaos.model_providers.models import (
    ChatMessage,
    DataClass,
    ProviderAttempt,
    ProviderCallRequest,
    ProviderResponse,
    ResolvedProviderRegistry,
)
from imperaos.model_providers.policy import GovernanceContext, evaluate_provider_policy
from imperaos.model_providers.redaction import redact_provider_input


def call_model_with_governance(
    *,
    request: ProviderCallRequest,
    registry: ResolvedProviderRegistry,
    adapter_factory: ProviderAdapterFactory,
    envelope_writer: ProviderCallEnvelopeWriter | None = None,
    fallback_provider_id: str | None = None,
) -> ProviderResponse:
    provider = registry.get(request.provider_id)
    if provider is None:
        raise ProviderNotFound(f"provider not found: {request.provider_id}")
    policy = registry.policy_for(provider.provider_id)
    decision = evaluate_provider_policy(
        request=request,
        provider=provider,
        policy=policy,
        governance_context=GovernanceContext(
            remote_providers_enabled=registry.remote_providers_enabled,
            fallback_provider_id=fallback_provider_id,
        ),
    )
    redacted_input = redact_provider_input(request=request, decision=decision)
    attempts: list[ProviderAttempt] = []
    response: ProviderResponse | None = None
    error: Exception | None = None
    try:
        if not decision.safe_to_call_provider:
            raise ProviderGenerationError(decision.reason_code)
        adapter = adapter_factory.create(provider.provider_id)
        if (
            hasattr(adapter, "generate")
            and adapter.__class__.__name__ == "OpenAICompatibleProvider"
        ):
            governed_request = request.model_copy(
                update={
                    "messages": redacted_input.messages,
                    "system": redacted_input.system,
                    "data_classes": redacted_input.data_classes,
                }
            )
            response = adapter.generate(governed_request)
        else:
            prompt = "\n".join(item.content for item in redacted_input.messages)
            content = adapter.generate(
                prompt=prompt,
                system=redacted_input.system,
                json_mode=request.json_mode,
            )
            response = ProviderResponse(
                provider_id=provider.provider_id,
                model=request.model,
                content=content,
            )
        attempts.append(
            ProviderAttempt(
                provider_id=provider.provider_id,
                provider_kind=provider.kind,
                success=True,
            )
        )
        return response
    except Exception as exc:
        error = exc
        raise
    finally:
        if envelope_writer is not None and (
            decision.evidence_required or response is not None or error is not None
        ):
            envelope = build_provider_call_envelope(
                request=request,
                decision=decision,
                provider_kind=str(provider.kind),
                redacted_input=redacted_input,
                response=response,
                error=error,
                attempts=attempts,
            )
            envelope_writer.write(envelope)


def build_chat_request(
    *,
    provider_id: str,
    model: str,
    prompt: str,
    system: str | None = None,
    data_classes: list[DataClass] | None = None,
    json_mode: bool = False,
    stream: bool = False,
    run_id: str = "cli-chat",
) -> ProviderCallRequest:
    return ProviderCallRequest(
        call_id=f"call-{uuid4()}",
        run_id=run_id,
        provider_id=provider_id,
        model=model,
        messages=[ChatMessage(role="user", content=prompt)],
        system=system,
        data_classes=data_classes or [DataClass.PUBLIC],
        json_mode=json_mode,
        stream=stream,
    )


class ProviderGovernanceLLM:
    def __init__(
        self,
        *,
        registry: ResolvedProviderRegistry,
        provider_id: str,
        model: str,
        envelope_writer: ProviderCallEnvelopeWriter | None = None,
        fallback_provider_id: str | None = None,
    ):
        self.registry = registry
        self.provider_id = provider_id
        self.model = model
        self.envelope_writer = envelope_writer
        self.fallback_provider_id = fallback_provider_id
        self._factory = ProviderAdapterFactory(registry=registry)

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        json_mode: bool = False,
        data_classes: list[DataClass] | None = None,
    ) -> str:
        request = build_chat_request(
            provider_id=self.provider_id,
            model=self.model,
            prompt=prompt,
            system=system,
            data_classes=data_classes,
            json_mode=json_mode,
        )
        response = call_model_with_governance(
            request=request,
            registry=self.registry,
            adapter_factory=self._factory,
            envelope_writer=self.envelope_writer,
            fallback_provider_id=self.fallback_provider_id,
        )
        return response.content

    def generate_stream(self, prompt: str, system: str | None = None, json_mode: bool = False):
        yield self.generate(prompt=prompt, system=system, json_mode=json_mode)
