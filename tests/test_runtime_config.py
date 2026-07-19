from imperaos.runtime.config import RuntimeConfig


def test_runtime_config_loads_balanced_profile() -> None:
    cfg = RuntimeConfig.from_profile("balanced")

    assert cfg.profile_name == "balanced"
    assert cfg.router_mode == "rule"
    assert cfg.shadow_router_enabled is True
    assert cfg.shadow_router_mode == "sltc"
    assert cfg.sltc.enabled is True
    assert cfg.enable_persistent_memory is True
    assert cfg.team.enabled is True
    assert cfg.team.max_parallel_tasks >= 1


def test_runtime_config_exposes_llm_timeout() -> None:
    cfg = RuntimeConfig.from_profile("lite")

    assert cfg.limits.llm_timeout_ms >= 1000


def test_runtime_config_loads_restricted_profile() -> None:
    cfg = RuntimeConfig.from_profile("restricted")

    assert cfg.profile_name == "restricted"
    assert cfg.governance.policy_path.endswith("config/policies/restricted.toml")
    assert cfg.team.max_parallel_tasks <= 4
