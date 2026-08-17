from __future__ import annotations

from imperaos.release_decision.no_ship import build_no_ship_register


def test_no_ship_blocks_public_desktop_overclaim() -> None:
    register = build_no_ship_register(
        gate_ledger_ready=True,
        rc_freeze_reconciled=True,
        signoff_verified=True,
        public_desktop_claim=True,
    )

    assert register.status == "blocked"
    assert "PUBLIC_WINDOWS_DESKTOP_WITHOUT_PUBLIC_GATE" in {item.id for item in register.items}


def test_no_ship_hata_not_blocked_by_hatb_external_credentials() -> None:
    register = build_no_ship_register(
        gate_ledger_ready=True,
        rc_freeze_reconciled=True,
        signoff_verified=True,
    )

    assert register.status == "clear"
    assert register.external_blocker_count >= 1
