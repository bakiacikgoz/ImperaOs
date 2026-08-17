from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol


class ProviderGenerationError(RuntimeError):
    """Raised when a provider cannot generate a response."""


class ProviderUnavailableError(RuntimeError):
    """Raised when a provider is not available in current runtime."""


class ChatProvider(Protocol):
    name: str

    def is_available(self) -> bool:
        ...

    def health(self, model_name: str) -> dict[str, object]:
        ...

    def generate(self, prompt: str, system: str | None = None, json_mode: bool = False) -> str:
        ...

    def generate_stream(
        self,
        prompt: str,
        system: str | None = None,
        json_mode: bool = False,
    ) -> Iterator[str]:
        ...


@dataclass(slots=True)
class ProviderAttempt:
    provider: str
    success: bool
    error: str | None = None


@dataclass(slots=True)
class ProviderChainReport:
    selected_provider: str | None
    attempts: list[ProviderAttempt]

    def as_json(self) -> dict[str, object]:
        return {
            "selected_provider": self.selected_provider,
            "attempts": [
                {"provider": item.provider, "success": item.success, "error": item.error}
                for item in self.attempts
            ],
        }
