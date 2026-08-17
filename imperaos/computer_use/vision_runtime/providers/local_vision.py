from __future__ import annotations


class LocalVisionProviderUnavailable(RuntimeError):
    pass


def create_local_vision_provider() -> None:
    raise LocalVisionProviderUnavailable(
        "Vision-first runtime requires a configured vision interpreter; local VLM is not bundled."
    )
