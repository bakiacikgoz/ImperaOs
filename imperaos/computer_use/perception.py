from __future__ import annotations

import hashlib
import json
from typing import Any

from imperaos.computer_use.models import PerceptionSource

PERCEPTION_PRIORITY = [
    PerceptionSource.DOM,
    PerceptionSource.DETERMINISTIC_SELECTOR,
    PerceptionSource.SCREENSHOT,
    PerceptionSource.OCR,
]


def select_perception_source(available_sources: list[PerceptionSource]) -> PerceptionSource:
    available = set(available_sources)
    for candidate in PERCEPTION_PRIORITY:
        if candidate in available:
            return candidate
    return PerceptionSource.OCR


def build_perception_fingerprint(
    *,
    window_or_tab_identity: str,
    app_identity: str,
    selector_context: dict[str, Any],
    screenshot_hash: str | None,
) -> str:
    payload = {
        "window_or_tab_identity": window_or_tab_identity,
        "app_identity": app_identity,
        "selector_context": selector_context,
        "screenshot_hash": screenshot_hash,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
