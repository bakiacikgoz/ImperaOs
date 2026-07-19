from __future__ import annotations

import json
from pathlib import Path

from imperaos.governance.runtime import GovernanceRuntime
from imperaos.runtime.config import RuntimeConfig


def test_finalize_run_writes_privacy_safe_audit_artifact(tmp_path: Path) -> None:
    cfg = RuntimeConfig.from_profile("default")
    cfg = cfg.model_copy(
        update={
            "governance": cfg.governance.model_copy(
                update={
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            )
        }
    )
    runtime = GovernanceRuntime(config=cfg)

    runtime.evaluate_task(
        run_id="run-audit",
        task_type="chat",
        user_input="my email is audit@example.com",
    )
    runtime.evaluate_tool_command(
        run_id="run-audit",
        command=["python", "-c", "print('token=abc123')"],
        workdir=Path("."),
    )

    path = runtime.finalize_run(
        run_id="run-audit",
        router_reason_code="RULE_ROUTE",
        model_metadata={
            "requested_provider": "auto",
            "requested_fallback_provider": "transformers",
            "requested_model_name": "lfm2.5-thinking:1.2b",
            "requested_hf_model_id": "distilgpt2",
            "selected_provider": "ollama",
            "selected_model_name": "lfm2.5-thinking:1.2b",
            "selected_hf_model_id": None,
            "fallback_used": False,
            "config_source_model_name": "cli",
            "config_source_hf_model_id": "profile",
        },
    )
    assert path is not None
    artifact = json.loads(Path(path).read_text(encoding="utf-8"))

    serialized = json.dumps(artifact, ensure_ascii=False)
    assert "audit@example.com" not in serialized
    assert "token=abc123" not in serialized
    assert "governance_decisions" in serialized
    assert artifact.get("requested_provider") == "auto"
    assert artifact.get("selected_provider") == "ollama"
    assert artifact.get("config_source_model_name") == "cli"
