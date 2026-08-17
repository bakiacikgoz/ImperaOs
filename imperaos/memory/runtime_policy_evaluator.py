from __future__ import annotations

import json
from pathlib import Path

from imperaos.memory.models import hash_identity
from imperaos.memory.runtime_bridge import RuntimeMemoryRequest
from imperaos.memory.runtime_policy import (
    MemoryRuntimePolicyEvaluationCase,
    MemoryRuntimePolicyEvaluationReport,
)
from imperaos.memory.runtime_policy_fixtures import build_memory_runtime_policy_fixture
from imperaos.runtime.paths import state_path


def run_policy_evaluation(
    *,
    suite_path: Path,
    output_path: Path,
    profile: str = "enterprise",
) -> MemoryRuntimePolicyEvaluationReport:
    cases = _load_cases(suite_path)
    fixture = build_memory_runtime_policy_fixture(
        Path(state_path("memory-runtime-policy-gate")),
        profile=profile,
        semantic_mode="enforced",
        semantic_enabled=True,
    )
    failures: list[dict[str, str]] = []
    for case in cases:
        status = _run_case(case, fixture.bridge)
        if status != case.expected_status:
            failures.append(
                {
                    "caseId": case.case_id,
                    "expectedStatus": case.expected_status,
                    "actualStatus": status,
                }
            )
    report = MemoryRuntimePolicyEvaluationReport(
        status="pass" if not failures else "fail",
        caseCount=len(cases),
        passedCount=len(cases) - len(failures),
        failedCount=len(failures),
        failures=tuple(failures),
        artifactPath=str(output_path),
        rawContentIncluded=False,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return report


def _load_cases(path: Path) -> list[MemoryRuntimePolicyEvaluationCase]:
    cases: list[MemoryRuntimePolicyEvaluationCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            cases.append(MemoryRuntimePolicyEvaluationCase.model_validate_json(stripped))
    return cases


def _run_case(case: MemoryRuntimePolicyEvaluationCase, bridge: object) -> str:
    if case.operation == "read":
        pack = bridge.retrieve_context(
            RuntimeMemoryRequest(
                run_id=f"gate-{hash_identity(case.case_id)[:12]}",
                query=case.query,
                actor_id=case.actor_id,
                requester_role=case.requester_role,
                principal_id=case.principal_id,
                agent_id=case.agent_id,
                team_id=case.team_id,
                case_id=case.case_scope_id,
                workspace_id="workspace-main",
            )
        )
        return pack.status
    result = bridge.propose_post_run_write(
        run_id=f"gate-{hash_identity(case.case_id)[:12]}",
        actor_id=case.actor_id,
        role=case.requester_role,
        user_input="runtime policy gate input",
        assistant_output=case.summary,
        scope=case.scope,
        owner=case.team_id,
        agent_id=case.agent_id,
    )
    return result.status
