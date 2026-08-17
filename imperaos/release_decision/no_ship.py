from __future__ import annotations

from imperaos.release_decision.models import NoShipItem, NoShipRegister


def build_no_ship_register(
    *,
    gate_ledger_ready: bool,
    rc_freeze_reconciled: bool,
    signoff_verified: bool,
    public_desktop_claim: bool = False,
    live_windows_computer_use: bool = False,
    live_linux_computer_use: bool = False,
) -> NoShipRegister:
    items: list[NoShipItem] = [
        NoShipItem(
            id="PUBLIC_MACOS_DESKTOP_WITHOUT_NOTARIZATION",
            severity="external_blocker",
            status="accepted_boundary",
            claimId="hat_b_public_desktop",
            reasonCode="HAT_B_EXTERNAL_CREDENTIALS_REQUIRED",
            resolutionPath="Complete signing and notarization outside this local gate.",
        ),
        NoShipItem(
            id="PUBLIC_WINDOWS_DESKTOP_WITHOUT_PUBLIC_GATE",
            severity="external_blocker",
            status="accepted_boundary",
            claimId="hat_b_public_desktop",
            reasonCode="WINDOWS_PUBLIC_GATE_REQUIRED",
            resolutionPath="Complete signed Windows public release gate.",
        ),
    ]
    if public_desktop_claim:
        items.append(
            NoShipItem(
                id="PUBLIC_WINDOWS_DESKTOP_WITHOUT_PUBLIC_GATE",
                severity="blocker",
                status="open",
                claimId="public_desktop_release",
                reasonCode="PUBLIC_DESKTOP_OVERCLAIM",
                resolutionPath="Remove the public desktop claim or attach Hat B evidence.",
            )
        )
    if live_windows_computer_use:
        items.append(
            NoShipItem(
                id="LIVE_WINDOWS_COMPUTER_USE_ENABLED",
                severity="blocker",
                status="open",
                claimId="live_computer_use",
                reasonCode="LIVE_WINDOWS_COMPUTER_USE_NO_SHIP",
            )
        )
    if live_linux_computer_use:
        items.append(
            NoShipItem(
                id="LIVE_LINUX_COMPUTER_USE_ENABLED",
                severity="blocker",
                status="open",
                claimId="live_computer_use",
                reasonCode="LIVE_LINUX_COMPUTER_USE_NO_SHIP",
            )
        )
    if not gate_ledger_ready:
        items.append(
            NoShipItem(
                id="GATE_LEDGER_NOT_READY",
                severity="blocker",
                status="open",
                claimId="mainline_rc_gate_ledger",
                reasonCode="GATE_LEDGER_NOT_READY",
            )
        )
    if not rc_freeze_reconciled:
        items.append(
            NoShipItem(
                id="RC_FREEZE_NOT_RECONCILED",
                severity="blocker",
                status="open",
                claimId="mainline_rc_freeze",
                reasonCode="RC_FREEZE_NOT_RECONCILED",
            )
        )
    if not signoff_verified:
        items.append(
            NoShipItem(
                id="MISSING_HUMAN_SIGNOFF",
                severity="warning",
                status="open",
                claimId="human_release_approval",
                reasonCode="MISSING_HUMAN_SIGNOFF",
            )
        )
    return NoShipRegister(status="clear", items=items)
