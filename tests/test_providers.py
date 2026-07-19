from __future__ import annotations

from dataclasses import dataclass

from imperaos.core.llm_ollama import OllamaLLM, check_provider_chain


@dataclass
class _FakeProvider:
    name: str
    should_fail: bool

    def is_available(self) -> bool:
        return True

    def health(self, model_name: str) -> dict[str, object]:
        return {
            "provider": self.name,
            "model_name": model_name,
            "daemon_ok": not self.should_fail,
            "model_present": not self.should_fail,
        }

    def generate(self, prompt: str, system: str | None = None, json_mode: bool = False) -> str:
        del system, json_mode
        if self.should_fail:
            raise RuntimeError("provider unavailable")
        return f"{self.name}:{prompt[:20]}"


def test_llm_provider_fallback_uses_secondary(monkeypatch) -> None:
    def fake_builder(**kwargs):  # type: ignore[no-untyped-def]
        provider_name = kwargs["provider_name"]
        if provider_name in {"auto", "ollama"}:
            return _FakeProvider(name="ollama", should_fail=True)
        return _FakeProvider(name="transformers", should_fail=False)

    monkeypatch.setattr(
        "imperaos.core.llm_ollama.OllamaLLM._build_provider",
        staticmethod(fake_builder),
    )

    llm = OllamaLLM(
        model_name="fake",
        provider_name="auto",
        fallback_provider="transformers",
        fallback_enabled=True,
    )

    output = llm.generate("hello")
    report = llm.chain_report()

    assert output.startswith("transformers:")
    assert report.selected_provider == "transformers"
    assert len(report.attempts) == 2


def test_check_provider_chain_selects_fallback_when_primary_unhealthy(monkeypatch) -> None:
    def fake_builder(**kwargs):  # type: ignore[no-untyped-def]
        provider_name = kwargs["provider_name"]
        if provider_name in {"auto", "ollama"}:
            return _FakeProvider(name="ollama", should_fail=True)
        return _FakeProvider(name="transformers", should_fail=False)

    monkeypatch.setattr(
        "imperaos.core.llm_ollama.OllamaLLM._build_provider",
        staticmethod(fake_builder),
    )

    report = check_provider_chain(
        model_name="fake",
        provider_name="auto",
        fallback_provider="transformers",
        fallback_enabled=True,
        hf_model_id="distilgpt2",
        device="cpu",
    )

    assert report["selected_provider"] == "transformers"
    assert report["status"] == "degraded_fallback"
    assert report["fallback_used"] is True
    assert report["requested_provider"] == "auto"
    assert report["effective_hf_model_id"] == "distilgpt2"


def test_check_provider_chain_unrunnable_when_all_providers_unusable(monkeypatch) -> None:
    def fake_builder(**kwargs):  # type: ignore[no-untyped-def]
        provider_name = kwargs["provider_name"]
        if provider_name in {"auto", "ollama"}:
            return _FakeProvider(name="ollama", should_fail=True)
        return _FakeProvider(name="transformers", should_fail=True)

    monkeypatch.setattr(
        "imperaos.core.llm_ollama.OllamaLLM._build_provider",
        staticmethod(fake_builder),
    )

    report = check_provider_chain(
        model_name="fake",
        provider_name="auto",
        fallback_provider="transformers",
        fallback_enabled=True,
        hf_model_id="distilgpt2",
        device="cpu",
    )

    assert report["selected_provider"] is None
    assert report["status"] == "unrunnable"
