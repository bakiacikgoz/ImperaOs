from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from imperaos.core.providers import (
    ChatProvider,
    OllamaProvider,
    ProviderAttempt,
    ProviderChainReport,
    ProviderGenerationError,
    TransformersProvider,
)


class LLMClient(Protocol):
    def generate(self, prompt: str, system: str | None = None, json_mode: bool = False) -> str:
        ...

    def generate_stream(
        self,
        prompt: str,
        system: str | None = None,
        json_mode: bool = False,
    ) -> Iterator[str]:
        ...


class LLMGenerationError(RuntimeError):
    """Raised when LLM generation fails across all configured providers."""


class OllamaLLM:
    """Provider-backed client kept for backward compatibility with existing imports.

    The class now supports `auto` selection and optional fallback provider chains.
    """

    def __init__(
        self,
        model_name: str,
        temperature: float = 0.2,
        host: str | None = None,
        timeout_s: float = 60.0,
        client: Any | None = None,
        provider_name: str = "auto",
        fallback_provider: str = "transformers",
        fallback_enabled: bool = True,
        hf_model_id: str = "distilgpt2",
        device: str = "cpu",
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.provider_name = provider_name
        self.fallback_provider = fallback_provider
        self.fallback_enabled = fallback_enabled
        self._last_chain_report = ProviderChainReport(selected_provider=None, attempts=[])

        self._primary = self._build_provider(
            provider_name=provider_name,
            model_name=model_name,
            temperature=temperature,
            host=host,
            timeout_s=timeout_s,
            client=client,
            hf_model_id=hf_model_id,
            device=device,
        )
        self._fallback = None
        if fallback_enabled and fallback_provider and fallback_provider != provider_name:
            self._fallback = self._build_provider(
                provider_name=fallback_provider,
                model_name=model_name,
                temperature=temperature,
                host=host,
                timeout_s=timeout_s,
                client=None,
                hf_model_id=hf_model_id,
                device=device,
            )

    @staticmethod
    def _build_provider(
        *,
        provider_name: str,
        model_name: str,
        temperature: float,
        host: str | None,
        timeout_s: float,
        client: Any | None,
        hf_model_id: str,
        device: str,
    ) -> ChatProvider:
        normalized = provider_name.strip().lower()
        if normalized in {"auto", "ollama"}:
            return OllamaProvider(
                model_name=model_name,
                temperature=temperature,
                host=host,
                timeout_s=timeout_s,
                client=client,
            )
        if normalized in {"transformers", "hf", "huggingface"}:
            return TransformersProvider(
                model_name=model_name,
                temperature=temperature,
                hf_model_id=hf_model_id,
                device=device,
            )
        raise ValueError(f"unsupported provider: {provider_name}")

    def generate(self, prompt: str, system: str | None = None, json_mode: bool = False) -> str:
        attempts: list[ProviderAttempt] = []

        providers: list[ChatProvider] = []
        if self.provider_name == "auto":
            providers.append(self._primary)
            if self._fallback is not None:
                providers.append(self._fallback)
        else:
            providers.append(self._primary)
            if self._fallback is not None:
                providers.append(self._fallback)

        last_error: str | None = None
        for provider in providers:
            try:
                content = provider.generate(prompt=prompt, system=system, json_mode=json_mode)
                attempts.append(ProviderAttempt(provider=provider.name, success=True, error=None))
                self._last_chain_report = ProviderChainReport(
                    selected_provider=provider.name,
                    attempts=attempts,
                )
                return content
            except ProviderGenerationError as exc:
                last_error = str(exc)
                attempts.append(
                    ProviderAttempt(provider=provider.name, success=False, error=str(exc))
                )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                attempts.append(
                    ProviderAttempt(provider=provider.name, success=False, error=str(exc))
                )

        self._last_chain_report = ProviderChainReport(selected_provider=None, attempts=attempts)
        raise LLMGenerationError(last_error or "all providers failed")

    def chain_report(self) -> ProviderChainReport:
        return self._last_chain_report

    def generate_stream(
        self,
        prompt: str,
        system: str | None = None,
        json_mode: bool = False,
    ) -> Iterator[str]:
        attempts: list[ProviderAttempt] = []
        providers: list[ChatProvider] = []
        if self.provider_name == "auto":
            providers.append(self._primary)
            if self._fallback is not None:
                providers.append(self._fallback)
        else:
            providers.append(self._primary)
            if self._fallback is not None:
                providers.append(self._fallback)

        last_error: str | None = None
        for provider in providers:
            try:
                yielded = False
                for token in provider.generate_stream(
                    prompt=prompt,
                    system=system,
                    json_mode=json_mode,
                ):
                    yielded = True
                    yield token
                attempts.append(ProviderAttempt(provider=provider.name, success=True, error=None))
                self._last_chain_report = ProviderChainReport(
                    selected_provider=provider.name,
                    attempts=attempts,
                )
                if yielded:
                    return
            except ProviderGenerationError as exc:
                last_error = str(exc)
                attempts.append(
                    ProviderAttempt(provider=provider.name, success=False, error=str(exc))
                )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                attempts.append(
                    ProviderAttempt(provider=provider.name, success=False, error=str(exc))
                )

        self._last_chain_report = ProviderChainReport(selected_provider=None, attempts=attempts)
        raise LLMGenerationError(last_error or "all providers failed")


@dataclass(slots=True)
class StubLLM:
    responses: list[str]
    default_response: str = "OK"
    calls: list[dict[str, object]] = field(default_factory=list)

    def generate(self, prompt: str, system: str | None = None, json_mode: bool = False) -> str:
        self.calls.append({"prompt": prompt, "system": system, "json_mode": json_mode})
        if self.responses:
            return self.responses.pop(0)
        return self.default_response

    def generate_stream(
        self,
        prompt: str,
        system: str | None = None,
        json_mode: bool = False,
    ) -> Iterator[str]:
        content = self.generate(prompt=prompt, system=system, json_mode=json_mode)
        yield from content


def check_ollama_runtime(model_name: str) -> dict[str, object]:
    provider = OllamaProvider(model_name=model_name)
    return provider.health(model_name=model_name)


def check_provider_chain(
    *,
    model_name: str,
    provider_name: str,
    fallback_provider: str,
    fallback_enabled: bool,
    hf_model_id: str,
    device: str,
) -> dict[str, object]:
    requested_provider = _normalize_provider_name(provider_name)
    requested_fallback = _normalize_provider_name(fallback_provider)
    primary = OllamaLLM._build_provider(
        provider_name=requested_provider,
        model_name=model_name,
        temperature=0.0,
        host=None,
        timeout_s=20.0,
        client=None,
        hf_model_id=hf_model_id,
        device=device,
    )
    primary_health = primary.health(model_name=model_name)
    primary_usable = _is_provider_usable(primary.name, primary_health)
    report: dict[str, object] = {
        "provider": requested_provider,
        "requested_provider": requested_provider,
        "requested_fallback_provider": requested_fallback,
        "requested_model_name": model_name,
        "requested_hf_model_id": hf_model_id,
        "fallback_enabled": fallback_enabled,
        "fallback_provider": requested_fallback,
        "primary": primary_health,
        "selected_provider": None,
        "effective_model_name": None,
        "effective_hf_model_id": None,
        "fallback_used": False,
        "status": "unrunnable",
    }

    secondary_usable = False
    secondary_name: str | None = None
    if fallback_enabled and requested_fallback and requested_fallback != requested_provider:
        secondary = OllamaLLM._build_provider(
            provider_name=requested_fallback,
            model_name=model_name,
            temperature=0.0,
            host=None,
            timeout_s=20.0,
            client=None,
            hf_model_id=hf_model_id,
            device=device,
        )
        secondary_health = secondary.health(model_name=model_name)
        report["secondary"] = secondary_health
        secondary_name = secondary.name
        secondary_usable = _is_provider_usable(secondary.name, secondary_health)

    selected_provider: str | None = None
    fallback_used = False
    status = "unrunnable"
    if primary_usable:
        selected_provider = primary.name
        status = "healthy"
    elif secondary_name is not None and secondary_usable:
        selected_provider = secondary_name
        fallback_used = True
        status = "degraded_fallback"

    report["selected_provider"] = selected_provider
    report["fallback_used"] = fallback_used
    report["status"] = status
    if selected_provider == "ollama":
        report["effective_model_name"] = model_name
    elif selected_provider == "transformers":
        report["effective_hf_model_id"] = hf_model_id

    return report


def _normalize_provider_name(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"hf", "huggingface"}:
        return "transformers"
    return normalized


def _is_provider_usable(provider_name: str, health: dict[str, object]) -> bool:
    normalized = _normalize_provider_name(provider_name)
    if normalized == "ollama":
        runtime_available = bool(health.get("runtime_available", True))
        daemon_ok = bool(health.get("daemon_ok", False))
        model_present = bool(health.get("model_present", False))
        return runtime_available and daemon_ok and model_present
    if normalized == "transformers":
        runtime_available = bool(health.get("runtime_available", True))
        has_transformers_fields = (
            "transformers_pipeline_ready" in health or "heuristic_fallback" in health
        )
        if has_transformers_fields:
            pipeline_ready = bool(health.get("transformers_pipeline_ready", False))
            heuristic_fallback = bool(health.get("heuristic_fallback", False))
            return runtime_available and (pipeline_ready or heuristic_fallback)
        daemon_ok = health.get("daemon_ok")
        model_present = health.get("model_present")
        if isinstance(daemon_ok, bool) and isinstance(model_present, bool):
            return runtime_available and daemon_ok and model_present
        return runtime_available
    runtime_available = health.get("runtime_available")
    if isinstance(runtime_available, bool):
        return runtime_available
    return True
