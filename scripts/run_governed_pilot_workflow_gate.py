from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.pilot_workflow import (  # noqa: E402
    load_governed_pilot_workflow_spec,
    run_governed_pilot_workflow,
    validate_governed_pilot_workflow_spec,
)
from imperaos.control_plane.pilot_workflow_verifier import (  # noqa: E402
    verify_governed_pilot_workflow_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run governed pilot workflow release gate.")
    parser.add_argument(
        "--spec",
        default="examples/pilot_workflows/enterprise_governed_memory_provider.yaml",
    )
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--output-root", default="artifacts/governed-pilot-workflow")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    spec_path = REPO_ROOT / args.spec
    output_root = REPO_ROOT / args.output_root
    validation = validate_governed_pilot_workflow_spec(spec_path)
    if validation.status != "pass":
        _emit(
            {
                "status": "fail",
                "phase": "validate",
                "validation": validation.model_dump(mode="json", by_alias=True),
            },
            json_output=args.json_output,
        )
        raise SystemExit(1)
    report = run_governed_pilot_workflow(
        load_governed_pilot_workflow_spec(spec_path),
        profile=args.profile,
        output_root=output_root,
    )
    verification = verify_governed_pilot_workflow_report(report.report_path or "")
    status = "pass" if report.status == "pass" and verification.status == "pass" else "fail"
    payload = {
        "schemaVersion": "control-plane.governed-pilot-workflow-gate/v1",
        "status": status,
        "reportPath": report.report_path,
        "summaryPath": report.summary_path,
        "reportHash": report.report_hash,
        "verification": verification.model_dump(mode="json", by_alias=True),
    }
    gate_path = output_root / "gate_result.json"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _emit(payload, json_output=args.json_output)
    if status != "pass":
        raise SystemExit(1)


def _emit(payload: dict[str, object], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload["status"])


if __name__ == "__main__":
    main()
