from __future__ import annotations

from imperaos.control_plane.claim_guard import ClaimGuard
from imperaos.runtime.config import RuntimeConfig


def test_claim_guard_blocks_public_desktop_and_cross_platform_computer_use(tmp_path) -> None:
    matrix = ClaimGuard(config=RuntimeConfig.from_profile("lite")).evaluate(evidence_root=tmp_path)
    claims = {item.claim_id: item for item in matrix.claims}

    assert claims["public-desktop-installer"].status == "blocked"
    assert "HAT_B_EVIDENCE_MISSING" in claims["public-desktop-installer"].blocking_reasons
    assert claims["live-windows-computer-use"].status == "blocked"
    windows_blockers = claims["live-windows-computer-use"].blocking_reasons
    assert "WINDOWS_COMPUTER_USE_NOT_QUALIFIED" in windows_blockers


def test_claim_guard_blocks_raw_screenshot_public_claim(tmp_path) -> None:
    config = RuntimeConfig.from_profile("lite")
    config = config.model_copy(
        update={
            "computer_use": config.computer_use.model_copy(
                update={"macos_live_enabled": True, "raw_screenshot_persistence": True}
            )
        }
    )

    matrix = ClaimGuard(config=config).evaluate(evidence_root=tmp_path)
    macos = {item.claim_id: item for item in matrix.claims}["live-macos-computer-use"]

    assert macos.status == "blocked"
    assert "RAW_SCREENSHOT_PERSISTED" in macos.blocking_reasons
