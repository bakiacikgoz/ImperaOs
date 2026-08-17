from __future__ import annotations

import subprocess
from collections.abc import Iterator
from shutil import which
from typing import Any

from imperaos.core.providers.base import ProviderGenerationError, ProviderUnavailableError


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        *,
        model_name: str,
        temperature: float = 0.2,
        host: str | None = None,
        timeout_s: float = 60.0,
        client: Any | None = None,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.timeout_s = timeout_s
        self._host = host

        if client is not None:
            self._client = client
            return

        self._client = None
        if self.is_available():
            from ollama import Client

            self._client = Client(host=host, timeout=timeout_s)

    def is_available(self) -> bool:
        return which("ollama") is not None

    def health(self, model_name: str) -> dict[str, object]:
        ollama_path = which("ollama")
        runtime_available = ollama_path is not None

        version = "not-found"
        daemon_ok = False
        model_present = False

        if runtime_available:
            version_proc = subprocess.run(
                ["ollama", "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            if version_proc.returncode == 0:
                version = version_proc.stdout.strip() or "unknown"

            list_proc = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                check=False,
            )
            daemon_ok = list_proc.returncode == 0
            if daemon_ok:
                model_present = model_name in list_proc.stdout

        return {
            "provider": self.name,
            "runtime_available": runtime_available,
            "ollama_path": ollama_path,
            "version": version,
            "daemon_ok": daemon_ok,
            "model_present": model_present,
            "model_name": model_name,
        }

    def generate(self, prompt: str, system: str | None = None, json_mode: bool = False) -> str:
        if self._client is None:
            raise ProviderUnavailableError("ollama runtime unavailable")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "options": {"temperature": self.temperature},
        }
        if json_mode:
            kwargs["format"] = "json"

        try:
            response = self._client.chat(**kwargs)
            content = response.get("message", {}).get("content", "").strip()
            if not content:
                raise ProviderGenerationError("ollama returned empty output")
            return content
        except Exception as exc:  # noqa: BLE001
            raise ProviderGenerationError(str(exc)) from exc

    def generate_stream(
        self,
        prompt: str,
        system: str | None = None,
        json_mode: bool = False,
    ) -> Iterator[str]:
        if self._client is None:
            raise ProviderUnavailableError("ollama runtime unavailable")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "options": {"temperature": self.temperature},
            "stream": True,
        }
        if json_mode:
            kwargs["format"] = "json"

        try:
            stream = self._client.chat(**kwargs)
            for chunk in stream:
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
        except Exception as exc:  # noqa: BLE001
            raise ProviderGenerationError(str(exc)) from exc
