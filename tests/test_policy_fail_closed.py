from __future__ import annotations

from pathlib import Path

from imperaos.governance.runtime import build_governance_runtime, governance_startup_abort
from imperaos.runtime.config import RuntimeConfig


def test_fail_closed_aborts_when_policy_file_missing(tmp_path: Path) -> None:
    cfg = RuntimeConfig.from_profile("lite")
    broken_cfg = cfg.model_copy(
        update={
            "governance": cfg.governance.model_copy(
                update={
                    "policy_path": str(tmp_path / "missing-policy.toml"),
                    "policy_fail_mode": "fail_closed",
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            )
        }
    )
    runtime = build_governance_runtime(broken_cfg)

    assert runtime is not None
    assert governance_startup_abort(broken_cfg, runtime) is not None
