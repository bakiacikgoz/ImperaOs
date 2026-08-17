from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from imperaos.memory.semantic.models import (
    MemoryRetrievalQualityReport,
    MemorySearchRequest,
    MemorySearchResult,
)

SearchFn = Callable[[MemorySearchRequest], MemorySearchResult]


def run_retrieval_quality_suite(
    *,
    suite_path: str | Path,
    search_fn: SearchFn,
    output_path: str | Path,
    top_k: int = 8,
) -> MemoryRetrievalQualityReport:
    cases = [
        json.loads(line)
        for line in Path(suite_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    recalls: list[float] = []
    hard_negative_leaks = 0
    scope_violations = 0
    raw_leaks = 0
    stale_results = 0
    expired_results = 0
    for case in cases:
        result = search_fn(
            MemorySearchRequest(
                query=case["query"],
                principalId=case["principalId"],
                workspaceId=case["workspaceId"],
                requestedScopes=tuple(case.get("requestedScopes", ())),
                limit=top_k,
            )
        )
        hit_ids = {hit.memory_id for hit in result.hits}
        expected = set(case.get("expectedMemoryIds", ()))
        recalls.append(len(hit_ids & expected) / max(1, len(expected)))
        hard_negative_leaks += len(hit_ids & set(case.get("hardNegativeMemoryIds", ())))
        scope_violations += result.scope_violation_count
        raw_leaks += result.raw_leak_count
        stale_results += result.stale_result_count
        expired_results += result.expired_result_count
    top_k_recall = sum(recalls) / max(1, len(recalls))
    status = (
        "pass"
        if top_k_recall >= 0.8 and hard_negative_leaks == 0 and raw_leaks == 0
        else "fail"
    )
    report = MemoryRetrievalQualityReport(
        status=status,
        queryCount=len(cases),
        topKRecall=round(top_k_recall, 6),
        hardNegativeLeakCount=hard_negative_leaks,
        scopeViolationCount=scope_violations,
        rawLeakCount=raw_leaks,
        staleResultCount=stale_results,
        expiredResultCount=expired_results,
        artifactPath=str(output_path),
    )
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report
