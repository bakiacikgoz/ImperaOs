from pathlib import Path

from imperaos.memory.evidence import MemoryEvidenceWriter
from imperaos.memory.models import MemoryPolicyAction, MemoryPolicyDecision


def test_writer_recreates_evidence_directories_if_fixture_root_was_replaced(tmp_path: Path) -> None:
    writer = MemoryEvidenceWriter(tmp_path / "evidence")
    writer.events_root.rmdir()
    writer.output_root.rmdir()

    _event, reference = writer.write_event(
        event_type="memory_written",
        policy_decision=MemoryPolicyDecision(
            decision=MemoryPolicyAction.ALLOW,
            reasonCode="ALLOW",
            redactionRequired=False,
            indexWriteAllowed=True,
            blockingReasons=[],
        ),
    )

    assert Path(reference).exists()
