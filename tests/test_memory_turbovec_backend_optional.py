from imperaos.memory.semantic.backends.turbovec_backend import TurboVecSemanticBackend


def test_turbovec_backend_is_optional() -> None:
    status = TurboVecSemanticBackend().status("default")

    assert status.raw_persistence is False
    assert status.status in {"unavailable_optional", "blocked"}
