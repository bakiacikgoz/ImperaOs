from __future__ import annotations

from dataclasses import dataclass

from imperaos.memory.authority import proposal_from_cli
from imperaos.memory.models import MemoryWriteProposal


@dataclass(frozen=True, slots=True)
class MemoryWriteCandidateInput:
    actor: str
    role: str
    run_id: str
    user_input: str
    assistant_output: str
    scope: str = "personal"
    owner_type: str = "user"
    owner: str | None = None
    visibility: str = "private"
    memory_target: str | None = None
    expected_state_version: int | None = None
    agent_id: str | None = None


class MemoryWriteCandidateBuilder:
    @staticmethod
    def build(candidate: MemoryWriteCandidateInput) -> MemoryWriteProposal | None:
        text = _candidate_text(candidate.user_input, candidate.assistant_output)
        if not text:
            return None
        owner = candidate.owner or candidate.actor
        return proposal_from_cli(
            actor=candidate.actor,
            scope=candidate.scope,
            owner_type=candidate.owner_type,
            owner=owner,
            visibility=candidate.visibility,
            text=text,
            role=candidate.role,
            reason="post_run_memory_candidate",
            memory_target=candidate.memory_target,
            expected_state_version=candidate.expected_state_version,
            agent_id=candidate.agent_id,
            source_run_id=candidate.run_id,
        )


def _candidate_text(user_input: str, assistant_output: str) -> str:
    user = user_input.strip()
    assistant = assistant_output.strip()
    if not user or not assistant:
        return ""
    text = f"User request: {user}\nAssistant outcome: {assistant}"
    return text[:8000]
