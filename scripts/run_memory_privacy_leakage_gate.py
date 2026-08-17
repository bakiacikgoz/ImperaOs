from __future__ import annotations

import json
import tempfile
from pathlib import Path

from imperaos.memory.semantic.fixtures import build_semantic_fixture
from imperaos.memory.semantic.models import MemorySearchRequest


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        fixture = build_semantic_fixture(Path(temp))
        result = fixture.service.search(
            MemorySearchRequest(
                query="provider governance target evidence",
                principalId="operator-local",
                workspaceId="default",
                requestedScopes=("personal:operator-local",),
            )
        )
        evidence_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (Path(temp) / "memory-semantic" / "events").glob("*.json")
        )
        forbidden = ["provider governance target evidence", "Private unrelated", "sk-"]
        raw_leak_count = sum(1 for item in forbidden if item in evidence_text)
        passed = (
            result.raw_leak_count == 0
            and raw_leak_count == 0
            and result.scope_violation_count == 0
        )
        payload = {
            "status": "pass" if passed else "fail",
            "rawLeakCount": raw_leak_count + result.raw_leak_count,
            "scopeViolationCount": result.scope_violation_count,
            "rawContentIncluded": False,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        if not passed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
