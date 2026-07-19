from __future__ import annotations

import time
from pathlib import Path

from imperaos.experts.base import ExpertBase
from imperaos.schemas.expert_payloads import ResearchCitation, ResearchExpertPayload
from imperaos.schemas.models import ExpertName, ExpertRequest, ExpertResult, ExpertStatus
from imperaos.tools.local_search import find_matches
from imperaos.tools.retrieval import retrieve_top_chunks


class ResearchExpert(ExpertBase):
    name = ExpertName.RESEARCH
    estimated_tool_calls_per_run = 2

    def __init__(self, workspace: str | Path = "."):
        self.workspace = Path(workspace)

    def run(self, request: ExpertRequest) -> ExpertResult:
        started = time.perf_counter()
        chunks = retrieve_top_chunks(request.user_input, root_dir=self.workspace, max_chunks=5)
        matches = find_matches(request.user_input, root_dir=self.workspace, max_matches=5)

        if not chunks and not matches:
            payload = ResearchExpertPayload(
                summary="Yerel kaynaklarda doğrudan eşleşme bulunamadı.",
                evidence=["No local match found"],
                citations=[],
                uncertainty=0.72,
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            return ExpertResult(
                expert_name=self.name,
                status=ExpertStatus.OK,
                confidence=0.28,
                payload=payload.model_dump(mode="json"),
                elapsed_ms=elapsed,
            )

        citations: list[ResearchCitation] = []
        evidence: list[str] = []

        for match in matches[:3]:
            citation = ResearchCitation(
                path=str(match["path"]),
                line=int(match["line"]),
                snippet=str(match["text"]),
            )
            citations.append(citation)
            evidence.append(f"{citation.path}:{citation.line} -> {citation.snippet}")

        for chunk in chunks[:2]:
            evidence.append(
                f"{chunk['path']}:{chunk['line_start']}-{chunk['line_end']} score={chunk['score']}"
            )
            citations.append(
                ResearchCitation(
                    path=str(chunk["path"]),
                    line=int(chunk["line_start"]),
                    snippet=str(chunk["text"]).splitlines()[0][:220],
                )
            )

        confidence = 0.84 if citations else 0.65
        payload = ResearchExpertPayload(
            summary="Yerel belgelerde ilişkili kanıtlar bulundu ve özetlendi.",
            evidence=evidence,
            citations=citations,
            uncertainty=round(max(0.0, 1.0 - confidence), 2),
        )

        elapsed = int((time.perf_counter() - started) * 1000)
        return ExpertResult(
            expert_name=self.name,
            status=ExpertStatus.OK,
            confidence=confidence,
            payload=payload.model_dump(mode="json"),
            elapsed_ms=elapsed,
        )
