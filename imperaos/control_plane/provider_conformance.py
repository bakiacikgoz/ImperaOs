from __future__ import annotations

import json
from pathlib import Path

from imperaos.control_plane.models import ProviderConformanceCheck, ProviderConformanceReport
from imperaos.control_plane.provider_governance import evaluate_provider_policy
from imperaos.control_plane.providers import get_native_provider_adapter

NATIVE_PROVIDER_KINDS = ["openai_responses", "anthropic_messages"]


def _safe_report_payload(report: ProviderConformanceReport) -> dict[str, object]:
    payload = report.model_dump(mode="json", by_alias=True)
    payload["rawRequestPersisted"] = False
    payload["rawResponsePersisted"] = False
    return payload


def run_provider_native_conformance(
    provider_kind: str,
    *,
    profile: str,
    offline: bool = True,
    output_dir: str | Path,
) -> ProviderConformanceReport:
    if not offline:
        return ProviderConformanceReport(
            status="fail",
            providerKind=provider_kind,
            offline=False,
            fixturesRun=0,
            blockingReasons=["PROVIDER_LIVE_CANARY_REQUIRES_EXPLICIT_OPT_IN"],
        )

    adapter = get_native_provider_adapter(provider_kind)
    checks: list[ProviderConformanceCheck] = []
    blocking: list[str] = []
    request_hashes: list[str] = []

    for fixture in adapter.conformance_fixtures():
        request = adapter.build_request(
            prompt=str(fixture["prompt"]),
            model=str(fixture["model"]),
            profile=profile,
            custom_tools=list(fixture.get("custom_tools", [])),
        )
        request_hashes.append(request.request_hash)
        decision = evaluate_provider_policy(request, profile=profile)
        status = "pass" if decision.decision == "allow" else "fail"
        checks.append(
            ProviderConformanceCheck(
                checkId=f"{fixture['fixture_id']}.strict_policy",
                status=status,
                reasonCode=",".join(decision.reason_codes),
                summary="strict retention/tool policy evaluated before outbound",
            )
        )
        if status == "fail":
            blocking.extend(decision.reason_codes)

        denied_request = adapter.build_request(
            prompt=str(fixture["prompt"]),
            model=str(fixture["model"]),
            profile=profile,
            server_tools=["web_search"],
        )
        denied = evaluate_provider_policy(denied_request, profile=profile)
        deny_passed = (
            denied.decision == "deny" and "PROVIDER_SERVER_TOOLS_DENIED" in denied.reason_codes
        )
        checks.append(
            ProviderConformanceCheck(
                checkId=f"{fixture['fixture_id']}.server_tools_denied",
                status="pass" if deny_passed else "fail",
                reasonCode="PROVIDER_SERVER_TOOLS_DENIED",
                summary="server tools are denied before outbound",
            )
        )
        if not deny_passed:
            blocking.append("PROVIDER_SERVER_TOOLS_DENY_CHECK_FAILED")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report_path = output_path / f"{provider_kind}_conformance.json"
    report = ProviderConformanceReport(
        status="pass" if not blocking else "fail",
        providerKind=provider_kind,
        offline=True,
        fixturesRun=len(adapter.conformance_fixtures()),
        policyChecks=checks,
        evidencePath=str(report_path),
        blockingReasons=sorted(set(blocking)),
        rawPersistence=False,
        requestHashes=request_hashes,
    )
    report_path.write_text(
        json.dumps(_safe_report_payload(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def run_provider_native_gate(
    *,
    profile: str,
    output_dir: str | Path,
) -> dict[str, object]:
    reports = [
        run_provider_native_conformance(kind, profile=profile, offline=True, output_dir=output_dir)
        for kind in NATIVE_PROVIDER_KINDS
    ]
    return {
        "contractVersion": "control-plane.provider-native-gate/v1",
        "profile": profile,
        "status": "pass" if all(report.status == "pass" for report in reports) else "fail",
        "reports": [report.model_dump(mode="json", by_alias=True) for report in reports],
    }
