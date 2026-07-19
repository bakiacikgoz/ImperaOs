from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from imperaos.core.providers.base import ProviderGenerationError


class TransformersProvider:
    name = "transformers"

    def __init__(
        self,
        *,
        model_name: str,
        temperature: float = 0.2,
        hf_model_id: str = "distilgpt2",
        device: str = "cpu",
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.hf_model_id = hf_model_id
        self.device = device

        self._pipe: Any | None = None
        self._load_error: str | None = None
        self._bootstrap_pipeline()

    def _bootstrap_pipeline(self) -> None:
        try:
            from transformers import pipeline
        except Exception as exc:  # noqa: BLE001
            self._load_error = f"transformers import failed: {exc}"
            self._pipe = None
            return

        try:
            # CPU-safe default for local fallback. We keep deterministic low-sampling.
            self._pipe = pipeline(
                task="text-generation",
                model=self.hf_model_id,
                device=-1,
            )
            self._load_error = None
        except Exception as exc:  # noqa: BLE001
            self._pipe = None
            self._load_error = f"pipeline init failed: {exc}"

    def is_available(self) -> bool:
        # Degrade gracefully to heuristic mode when transformers stack is unavailable.
        return True

    def health(self, model_name: str) -> dict[str, object]:
        return {
            "provider": self.name,
            "runtime_available": True,
            "transformers_pipeline_ready": self._pipe is not None,
            "load_error": self._load_error,
            "model_name": model_name,
            "hf_model_id": self.hf_model_id,
            "device": self.device,
            "heuristic_fallback": self._pipe is None,
        }

    def generate(self, prompt: str, system: str | None = None, json_mode: bool = False) -> str:
        if self._pipe is not None:
            try:
                text_prompt = self._render_prompt(prompt=prompt, system=system, json_mode=json_mode)
                outputs = self._pipe(
                    text_prompt,
                    max_new_tokens=256,
                    do_sample=False,
                    temperature=max(self.temperature, 0.01),
                    num_return_sequences=1,
                )
                generated = outputs[0].get("generated_text", "")
                if generated.startswith(text_prompt):
                    content = generated[len(text_prompt) :].strip()
                else:
                    content = generated
                if not content:
                    raise ProviderGenerationError("transformers provider generated empty output")
                if json_mode:
                    return self._coerce_json(content)
                return content
            except Exception as exc:  # noqa: BLE001
                raise ProviderGenerationError(str(exc)) from exc

        # Heuristic fallback keeps product path alive when transformers stack is absent.
        if json_mode:
            return json.dumps(
                {
                    "task_type": "chat",
                    "intent": "hf_heuristic_fallback",
                    "needs_expert": False,
                    "expert_candidates": [],
                    "confidence": 0.3,
                    "latency_budget_ms": 3000,
                    "can_fallback": True,
                    "response_mode": "direct",
                }
            )

        preview = prompt.strip().splitlines()[0][:220] if prompt.strip() else ""
        if not preview:
            preview = "No prompt provided."
        return f"[HF fallback heuristic] {preview}"

    def generate_stream(
        self,
        prompt: str,
        system: str | None = None,
        json_mode: bool = False,
    ) -> Iterator[str]:
        content = self.generate(prompt=prompt, system=system, json_mode=json_mode)
        # Transformers pipeline fallback is not token-streaming here; emulate chunked output.
        for word in content.split(" "):
            if not word:
                continue
            yield f"{word} "

    @staticmethod
    def _render_prompt(prompt: str, system: str | None, json_mode: bool) -> str:
        pieces = []
        if system:
            pieces.append(f"System: {system}")
        pieces.append(f"User: {prompt}")
        if json_mode:
            pieces.append("Return strict JSON only.")
        pieces.append("Assistant:")
        return "\n".join(pieces)

    @staticmethod
    def _coerce_json(content: str) -> str:
        text = content.strip()
        if not text:
            raise ProviderGenerationError("empty JSON candidate")
        try:
            parsed = json.loads(text)
            return json.dumps(parsed)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                candidate = text[start : end + 1]
                parsed = json.loads(candidate)
                return json.dumps(parsed)
            raise ProviderGenerationError("could not parse JSON output") from None
