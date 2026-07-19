from __future__ import annotations

from imperaos.release_decision.models import ReleaseDecisionDossier


def render_release_decision_summary(dossier: ReleaseDecisionDossier) -> str:
    return "\n".join(
        [
            "# RC Release Decision Dossier",
            "",
            f"- Status: `{dossier.status}`",
            f"- Hat A: `{dossier.hat_a_status}`",
            f"- Hat B: `{dossier.hat_b_status}`",
            f"- Design Partner RC: `{dossier.design_partner_rc_status}`",
            f"- Sign-off: `{dossier.signoff_status}`",
            f"- No-ship blockers: `{dossier.no_ship_register.blocking_count}`",
            "",
            "This dossier is hash-only and does not approve public desktop release claims.",
            "",
        ]
    )
