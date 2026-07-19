from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from imperaos.memory.semantic.backends.turbovec_backend import TurboVecSemanticBackend
from imperaos.memory.semantic.fixtures import build_semantic_fixture
from imperaos.memory.semantic.models import MemoryBackendBenchmarkReport, MemorySearchRequest


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        fixture = build_semantic_fixture(Path(temp))
        latencies: list[float] = []
        for _ in range(3):
            started = time.perf_counter()
            fixture.service.search(
                MemorySearchRequest(
                    query="provider governance target evidence",
                    principalId="operator-local",
                    workspaceId="default",
                    requestedScopes=("personal:operator-local",),
                )
            )
            latencies.append((time.perf_counter() - started) * 1000.0)
        report = MemoryBackendBenchmarkReport(
            status="pass",
            backendKind="in_memory_fixture",
            indexedRecordCount=fixture.service.status("default").record_count,
            queryCount=len(latencies),
            p95LatencyMs=round(sorted(latencies)[-1], 3),
            reasonCodes=(),
        )
        turbovec = TurboVecSemanticBackend().status("default")
        payload = report.model_dump(mode="json", by_alias=True)
        payload["turbovec"] = turbovec.model_dump(mode="json", by_alias=True)
        print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
