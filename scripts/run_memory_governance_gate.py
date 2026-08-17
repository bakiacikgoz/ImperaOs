from __future__ import annotations

import json
from pathlib import Path

from imperaos.memory.authority import build_memory_authority, proposal_from_cli
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    config = RuntimeConfig.from_profile("enterprise")
    authority = build_memory_authority(config)
    secret = authority.propose_write(
        proposal_from_cli(
            actor="governance-gate",
            scope="personal",
            owner_type="user",
            owner="governance-gate",
            visibility="private",
            text="remember sk-test-secret-token-123456789",
            role="Research Analyst Agent",
            reason="secret negative test",
        )
    )
    org = authority.propose_write(
        proposal_from_cli(
            actor="governance-gate",
            scope="organization",
            owner_type="org",
            owner="imperaos",
            visibility="organization",
            text="organization policy memory",
            role="Research Analyst Agent",
            reason="org approval test",
        )
    )
    status = "pass" if secret.status == "denied" and org.status == "approval_required" else "fail"
    payload = {
        "status": status,
        "secretDecision": secret.status,
        "organizationDecision": org.status,
        "rawPersistence": False,
    }
    out = Path("artifacts/memory-governance/memory_governance_gate.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
