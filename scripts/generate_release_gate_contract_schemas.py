from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.release.gate_models import (  # noqa: E402
    GateEvidenceLedger,
    GateEvidenceVerificationReport,
    GateRunResult,
    RcEvidenceBackfillReport,
    RcEvidenceOrchestrationReport,
    ReleaseGatePlan,
)

SCHEMAS = {
    "release_gate_plan": ReleaseGatePlan,
    "gate_run_result": GateRunResult,
    "gate_evidence_ledger": GateEvidenceLedger,
    "gate_evidence_verification_report": GateEvidenceVerificationReport,
    "rc_evidence_backfill_report": RcEvidenceBackfillReport,
    "rc_evidence_orchestration_report": RcEvidenceOrchestrationReport,
}


def main() -> None:
    root = REPO_ROOT / "contracts" / "release"
    root.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMAS.items():
        (root / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
