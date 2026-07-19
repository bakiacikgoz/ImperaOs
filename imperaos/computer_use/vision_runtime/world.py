from __future__ import annotations

from imperaos.computer_use.vision_runtime.models import VisionObservation


def observation_summary(observation: VisionObservation) -> dict[str, str | None]:
    return {
        "screenshot_hash": observation.screenshot_hash,
        "platform": observation.platform,
        "active_app": observation.active_app,
        "active_window_title": observation.active_window_title,
        "surface_kind": observation.surface_kind.value,
    }
