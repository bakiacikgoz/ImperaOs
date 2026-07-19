from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.pilot_workflow_models import (  # noqa: E402
    GovernedPilotWorkflowReport,
    GovernedPilotWorkflowSnapshot,
    GovernedPilotWorkflowSpec,
    GovernedPilotWorkflowVerification,
)

SCHEMAS = {
    "governed_pilot_workflow_spec": GovernedPilotWorkflowSpec,
    "governed_pilot_workflow_report": GovernedPilotWorkflowReport,
    "governed_pilot_workflow_verification": GovernedPilotWorkflowVerification,
    "governed_pilot_workflow_snapshot": GovernedPilotWorkflowSnapshot,
}


def main() -> None:
    root = REPO_ROOT / "contracts" / "control_plane"
    root.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMAS.items():
        (root / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=True, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
