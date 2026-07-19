from __future__ import annotations

from typing import Any, Protocol

from imperaos.control_plane.models import NativeRequestEnvelope, ProviderNativeResult


class NativeProviderAdapter(Protocol):
    kind: str

    def build_request(
        self,
        *,
        prompt: str,
        model: str,
        profile: str = "enterprise",
        server_tools: list[str] | None = None,
        custom_tools: list[dict[str, Any]] | None = None,
    ) -> NativeRequestEnvelope:
        ...

    def parse_response(self, raw: dict[str, Any]) -> ProviderNativeResult:
        ...

    def conformance_fixtures(self) -> list[dict[str, Any]]:
        ...
