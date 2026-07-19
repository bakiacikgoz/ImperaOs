from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from imperaos.model_providers.native.conformance import (
    run_all_native_conformance,
    verify_native_conformance_evidence,
    write_native_conformance_report,
)


def run_provider_native_adapter_gate(
    *,
    profile: str,
    output_root: Path,
) -> dict[str, Any]:
    reports = run_all_native_conformance(profile=profile)
    paths = {
        str(report.provider_kind): write_native_conformance_report(
            report=report,
            output_root=output_root,
            stem=f"{report.provider_kind}_native_adapter_report",
        )
        for report in reports
    }
    verify = verify_native_conformance_evidence(output_root=output_root)
    status = (
        "pass"
        if all(report.status == "pass" for report in reports) and verify["status"] == "pass"
        else "fail"
    )
    openai_report = next(
        report for report in reports if str(report.provider_kind) == "openai_responses"
    )
    gate = {
        "version": "model_provider.native_adapter_gate/v1",
        "status": status,
        "profile": profile,
        "liveCanaryAttempted": False,
        "nativeConformance": openai_report.model_dump(mode="json"),
        "nativeConformanceReports": [report.model_dump(mode="json") for report in reports],
        "totalCases": sum(report.total_cases for report in reports),
        "passCount": sum(report.pass_count for report in reports),
        "expectedBlockedCount": sum(report.expected_blocked_count for report in reports),
        "unexpectedFailureCount": sum(report.unexpected_failure_count for report in reports),
        "evidenceVerify": verify,
        "paths": paths,
    }
    gate_path = output_root / "provider_native_adapter_gate.json"
    gate_path.write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run provider native adapter V2 gate.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/model-provider-governance/native-v2"),
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    gate = run_provider_native_adapter_gate(profile=args.profile, output_root=args.output_root)
    if args.json_output:
        print(json.dumps(gate, indent=2, sort_keys=True))
    else:
        print(f"status={gate['status']} profile={gate['profile']}")
    return 0 if gate["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
