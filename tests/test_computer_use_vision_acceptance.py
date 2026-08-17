from __future__ import annotations

import os

import pytest


@pytest.mark.skipif(
    os.environ.get("IMPERAOS_ENABLE_REAL_VISION_COMPUTER_USE_TESTS") != "1",
    reason="live macOS vision computer-use tests require explicit opt-in",
)
def test_live_macos_vision_acceptance_placeholder() -> None:
    pytest.skip(
        "Live macOS acceptance requires local Screen Recording, Accessibility, and provider setup."
    )
