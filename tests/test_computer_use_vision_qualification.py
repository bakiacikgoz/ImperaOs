from __future__ import annotations

import json
from pathlib import Path

from imperaos.computer_use.vision_runtime.qualification import run_vision_qualification
from imperaos.runtime.config import ComputerUseRuntimeConfig


def test_deterministic_qualification_writes_machine_readable_report(tmp_path: Path) -> None:
    task_path = tmp_path / "tasks.jsonl"
    task_path.write_text(
        "\n".join(
            [
                json.dumps({"task_id": "safe-click", "expected": "verified_click"}),
                json.dumps({"task_id": "sensitive", "expected": "sensitive_surface_detected"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = run_vision_qualification(
        config=ComputerUseRuntimeConfig(vision_provider="mock"),
        mode="deterministic",
        suite="smoke",
        task_path=task_path,
        output_root=tmp_path / "qualification",
    )

    assert report["artifact_version"] == "computer_use_vision_qualification/v1"
    assert report["mode"] == "deterministic"
    assert report["status"] == "pass"
    assert report["summary"]["task_count"] == 2
    assert report["summary"]["raw_screenshot_persisted_count"] == 0
    assert (tmp_path / "qualification" / "qualification.json").exists()


def test_live_qualification_blocks_without_opt_in(tmp_path: Path) -> None:
    report = run_vision_qualification(
        config=ComputerUseRuntimeConfig(vision_provider="ollama", vision_model="llava"),
        mode="live",
        suite="smoke",
        task_path=tmp_path / "missing.jsonl",
        output_root=tmp_path / "qualification",
        env={},
    )

    assert report["status"] == "skipped"
    assert report["blocking_reasons"] == ["IMPERAOS_ENABLE_REAL_VISION_COMPUTER_USE_TESTS_NOT_SET"]
