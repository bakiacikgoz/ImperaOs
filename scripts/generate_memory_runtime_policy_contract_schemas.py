from __future__ import annotations

import json
from pathlib import Path

from imperaos.memory.runtime_policy import (
    AgentMemoryRuntimePolicyDecision,
    AgentMemoryRuntimePolicyDoctorReport,
    AgentMemoryRuntimePolicyReadResult,
    MemoryRuntimePolicyEvaluationReport,
)
from imperaos.memory.runtime_policy_snapshot import MemoryPolicyEnforcementSnapshot

SCHEMAS = {
    "runtime_policy_decision.schema.json": AgentMemoryRuntimePolicyDecision,
    "runtime_policy_read_result.schema.json": AgentMemoryRuntimePolicyReadResult,
    "runtime_policy_doctor.schema.json": AgentMemoryRuntimePolicyDoctorReport,
    "runtime_policy_evaluation.schema.json": MemoryRuntimePolicyEvaluationReport,
    "runtime_policy_snapshot.schema.json": MemoryPolicyEnforcementSnapshot,
}


def main() -> None:
    output_dir = Path("contracts/memory")
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        path = output_dir / filename
        schema = model.model_json_schema(mode="validation")
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
