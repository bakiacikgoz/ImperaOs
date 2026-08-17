from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.release_decision.models import (  # noqa: E402
    HumanSignoffRecord,
    HumanSignoffVerificationReport,
    NoShipRegister,
    RcFreezeReconciliationReport,
    ReleaseDecisionDossier,
    ReleaseDecisionVerificationReport,
)

SCHEMAS = {
    "rc_freeze_reconciliation": RcFreezeReconciliationReport,
    "no_ship_register": NoShipRegister,
    "human_signoff": HumanSignoffRecord,
    "human_signoff_verification": HumanSignoffVerificationReport,
    "release_decision_dossier": ReleaseDecisionDossier,
    "release_decision_verification": ReleaseDecisionVerificationReport,
}


def main() -> None:
    root = REPO_ROOT / "contracts" / "release_decision"
    root.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMAS.items():
        (root / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
