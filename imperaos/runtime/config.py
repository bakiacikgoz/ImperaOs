from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from imperaos.product_identity import PRODUCT_IDENTITY
from imperaos.runtime.paths import state_path


class RuntimeLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expert_timeout_ms: int = Field(default=2500, ge=1)
    max_retries: int = Field(default=1, ge=0)
    circuit_breaker_threshold: int = Field(default=3, ge=1)
    circuit_breaker_cooldown_s: int = Field(default=300, ge=1)
    llm_timeout_ms: int = Field(default=60000, ge=1000)
    max_tool_calls: int = Field(default=4, ge=1)
    max_recursion_depth: int = Field(default=3, ge=1)


class SLTCConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = False
    router_mode: Literal["active", "shadow", "off"] = "shadow"
    decay: float = Field(default=0.82, ge=0.0, le=1.0)
    spike_threshold: float = Field(default=0.55, ge=0.0, le=2.0)
    confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    failure_penalty_weight: float = Field(default=0.35, ge=0.0, le=2.0)
    latency_penalty_weight: float = Field(default=0.12, ge=0.0, le=2.0)
    need_bonus: float = Field(default=0.12, ge=0.0, le=2.0)
    conf_bonus: float = Field(default=0.2, ge=0.0, le=2.0)
    task_bias_overrides: dict[str, float] = Field(default_factory=dict)


class MemoryRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = False
    policy_enforcement_enabled: bool = False
    semantic_runtime_mode: Literal["disabled", "shadow", "enforced"] = "disabled"
    context_top_k: int = Field(default=4, ge=0, le=50)
    max_context_chars: int = Field(default=4000, ge=0, le=16000)
    post_run_write_enabled: bool = False
    post_run_default_scope: Literal[
        "personal",
        "agent",
        "team",
        "case",
        "project",
        "organization",
    ] = "personal"
    strict_fail_closed_profiles: list[str] = Field(
        default_factory=lambda: ["enterprise", "restricted"]
    )


class MemorySyncConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = False
    export_raw_content: bool = False
    import_apply_requires_approval: bool = True
    allow_cross_environment_import: bool = False


class MemoryWorkspaceAuthorityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = False
    mode: Literal["local"] = "local"
    default_workspace_id: str = "default"
    default_principal_id: str = "agent-local"
    db_path: str = state_path("workspace_memory.sqlite3")
    raw_content_persistence: bool = False
    network_listener_enabled: bool = False
    migration_apply_enabled: bool = False


class MemorySemanticTurboVecConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = False
    experimental: bool = True
    bit_width: int = Field(default=4, ge=1, le=8)
    allow_runtime_injection: bool = False


class MemorySemanticBackendsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    turbovec: MemorySemanticTurboVecConfig = Field(default_factory=MemorySemanticTurboVecConfig)


class MemorySemanticConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = False
    runtime_injection_enabled: bool = False
    backend: Literal["in_memory_fixture", "sqlite_text", "turbovec", "null"] = "in_memory_fixture"
    embedding_profile: str = "deterministic-fixture-v1"
    max_hits: int = Field(default=8, ge=1, le=50)
    allow_stale_index: bool = False
    raw_persistence: bool = False
    backends: MemorySemanticBackendsConfig = Field(default_factory=MemorySemanticBackendsConfig)

    @field_validator("raw_persistence")
    @classmethod
    def _raw_persistence_must_stay_disabled(cls, value: bool) -> bool:
        if value:
            raise ValueError("memory.semantic.raw_persistence must remain false")
        return value


class MemoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    db_path: str = state_path("memory.sqlite3")
    v3_enabled: bool = False
    v3_authority_mode: Literal["local"] = "local"
    raw_prompt_persistence: bool = False
    raw_response_persistence: bool = False
    raw_content_artifacts: bool = False
    primary_ui_raw_content: bool = False
    semantic_index_enabled: bool = True
    semantic_index_backend: Literal["sqlite_text", "dense_json", "turbovec_experimental"] = (
        "sqlite_text"
    )
    turbovec_experimental_enabled: bool = False
    turbovec_bits_per_coord: int = Field(default=4, ge=1, le=8)
    turbovec_dim_guard_max: int = Field(default=4096, ge=1, le=65536)
    salience_threshold: float = Field(default=0.62, ge=0.0, le=1.0)
    salience_decay: float = Field(default=0.82, ge=0.0, le=1.0)
    max_rows: int = Field(default=5000, ge=100)
    context_top_k: int = Field(default=4, ge=0)
    keyword_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "remember": 0.18,
            "hatırla": 0.18,
            "plan": 0.12,
            "adım": 0.12,
            "deadline": 0.1,
            "todo": 0.1,
            "bug": 0.12,
            "hata": 0.12,
            "important": 0.16,
            "önemli": 0.16,
        }
    )
    expert_bonus: float = Field(default=0.06, ge=0.0, le=1.0)
    task_bonus: float = Field(default=0.08, ge=0.0, le=1.0)
    spike_reduction: float = Field(default=0.5, ge=0.0, le=1.0)
    rank_salience_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    rank_recency_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    runtime: MemoryRuntimeConfig = Field(default_factory=MemoryRuntimeConfig)
    sync: MemorySyncConfig = Field(default_factory=MemorySyncConfig)
    workspace_authority: MemoryWorkspaceAuthorityConfig = Field(
        default_factory=MemoryWorkspaceAuthorityConfig
    )
    semantic: MemorySemanticConfig = Field(default_factory=MemorySemanticConfig)


class PlannerTuningConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    repair_enabled: bool = True
    repair_max_attempts: int = Field(default=1, ge=0, le=2)
    prompt_variant: Literal["strict_v1", "strict_v2", "strict_v3"] = "strict_v2"


class CodeVerifyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = True
    lint_enabled: bool = True
    test_collect_enabled: bool = True
    targeted_tests_enabled: bool = False
    timeout_s: int = Field(default=15, ge=1, le=120)
    retry_max: int = Field(default=1, ge=0, le=3)
    retry_strategy: Literal["failure_aware", "minimal_only"] = "failure_aware"


class GovernanceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = True
    policy_path: str = "config/policies/default.toml"
    policy_fail_mode: Literal["fail_closed", "fail_open"] = "fail_closed"
    approval_store_path: str = state_path("governance", "approvals.sqlite3")
    audit_dir: str = state_path("audit")
    pii_redaction_enabled: bool = True
    approval_ttl_seconds: int = Field(default=86400, ge=60)
    decision_engine_version: str = "v0.3"


class TeamRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = True
    max_parallel_tasks: int = Field(default=4, ge=1, le=64)
    max_total_tasks: int = Field(default=64, ge=1)
    max_handoff_depth: int = Field(default=8, ge=1)
    checkpoint_db_path: str = state_path("team", "checkpoints.sqlite3")
    artifact_dir: str = state_path("team", "jobs")


class SecurityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mode: Literal["default", "enterprise"] = "default"
    require_immutable_audit_export: bool = False
    allow_debug_privacy_override: bool = False
    restricted_vs_admin_boundary: bool = False


class IdentityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = False
    mode: Literal["disabled", "external_assertion", "break_glass_only"] = "disabled"
    required_for_mutations: bool = False
    assertion_path: str = state_path("identity", "current_assertion.json")
    break_glass_assertion_path: str = state_path("identity", "break_glass_assertion.json")
    trusted_keys_dir: str = state_path("keys", "trusted")
    allow_break_glass: bool = True
    max_clock_skew_seconds: int = Field(default=60, ge=0, le=600)
    permission_model_version: str = "1.0"


class KeyManagementConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    provider: Literal[
        "disabled",
        "env_hmac",
        "local_file",
        "managed_kms",
        "pkcs11_hsm",
    ] = "disabled"
    current_key_id: str | None = None
    private_key_path: str = state_path("keys", "private", "current_key.json")
    trusted_public_keys_dir: str = state_path("keys", "trusted")
    key_manifest_path: str = state_path("keys", "manifest.json")
    managed_signer_command: list[str] = Field(default_factory=list)
    allow_env_hmac_compat: bool = True


class ObservabilityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    metrics_dir: str = state_path("metrics")
    file_snapshot_enabled: bool = True
    prometheus_textfile_path: str = state_path("metrics", "imperaos.prom")
    http_exporter_enabled: bool = False
    http_bind: str = "127.0.0.1:9464"


class MaintenanceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    maintenance_flag_path: str = state_path("maintenance.lock")
    backup_dir: str = state_path("backups")
    restore_dir: str = state_path("restores")
    migration_dir: str = state_path("migrations")
    support_bundle_dir: str = state_path("support")


class ComputerUseRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = True
    runtime_mode: Literal["legacy_pilot", "vision_first", "auto"] = "legacy_pilot"
    vision_enabled: bool = False
    vision_provider: Literal["mock", "ollama", "none"] = "none"
    vision_model: str | None = None
    vision_provider_timeout_s: float = Field(default=30.0, ge=1.0, le=120.0)
    vision_provider_max_retries: int = Field(default=1, ge=0, le=3)
    default_mode: Literal["dry_run", "step_approval", "execute"] = "step_approval"
    max_steps: int = Field(default=50, ge=1, le=300)
    max_recovery_attempts: int = Field(default=3, ge=0, le=10)
    max_consecutive_wait_actions: int = Field(default=3, ge=1, le=50)
    screenshot_interval_ms: int = Field(default=750, ge=100, le=10000)
    min_action_confidence: float = Field(default=0.82, ge=0.0, le=1.0)
    min_verification_confidence: float = Field(default=0.80, ge=0.0, le=1.0)
    macos_live_enabled: bool = False
    macos_capture_backend: Literal[
        "disabled",
        "screencapture",
        "quartz",
        "screencapturekit",
    ] = "disabled"
    macos_input_backend: Literal["quartz", "disabled"] = "disabled"
    macos_primary_display_only: bool = True
    macos_require_fresh_qualification: bool = True
    macos_qualification_report: str = ""
    macos_max_steps: int = Field(default=25, ge=1, le=100)
    macos_step_delay_ms: int = Field(default=150, ge=0, le=10000)
    macos_require_step_approval: bool = True
    windows_live_enabled: bool = False
    windows_capture_backend: Literal["disabled", "mock", "gdi", "windows_graphics_capture"] = (
        "disabled"
    )
    windows_input_backend: Literal["disabled", "mock", "win32_sendinput"] = "disabled"
    linux_live_enabled: bool = False
    linux_capture_backend: Literal["disabled", "mock", "x11", "wayland_portal"] = "disabled"
    linux_input_backend: Literal["disabled", "mock", "xdotool", "ydotool", "uinput"] = (
        "disabled"
    )
    action_set: list[
        Literal[
            "move_mouse",
            "click",
            "double_click",
            "right_click",
            "scroll",
            "type_text",
            "press_key",
            "hotkey",
            "wait",
            "switch_window",
            "focus_window_or_app",
        ]
    ] = Field(default_factory=lambda: ["move_mouse", "click", "double_click", "scroll", "wait"])
    require_approval_for_type_text: bool = True
    require_approval_for_hotkey: bool = True
    require_approval_for_download: bool = True
    require_approval_for_upload: bool = True
    max_action_duration_ms: int = Field(default=5000, ge=100, le=30000)
    post_action_observe_delay_ms: int = Field(default=500, ge=100, le=5000)
    approval_snapshot_max_age_ms: int = Field(default=10000, ge=1000, le=120000)
    raw_screenshot_persistence: bool = False
    raw_screenshot_retention: Literal["disabled", "debug_only", "explicit_opt_in"] = "disabled"
    raw_screenshot_max_count: int = Field(default=0, ge=0, le=100)
    allowed_apps: list[str] = Field(default_factory=list)
    blocked_apps: list[str] = Field(
        default_factory=lambda: [
            "System Settings",
            "Settings",
            "Keychain Access",
            "Password Manager",
        ]
    )
    terminal_control: Literal["deny", "approval_required", "allow_read_only"] = "deny"
    sensitive_surface_policy: Literal["stop", "approval_required"] = "stop"
    platform_qualification_required: bool = True

    @field_validator("vision_model", mode="before")
    @classmethod
    def _empty_vision_model_as_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    model_name: str = "lfm2.5-thinking:1.2b"
    profile_name: str = "default"
    llm_provider: str = "auto"
    fallback_provider: str = "transformers"
    fallback_enabled: bool = True
    hf_model_id: str = "distilgpt2"
    device: str = "cpu"
    router_mode: str = "rule"
    shadow_router_enabled: bool = False
    shadow_router_mode: str = "sltc"
    planner_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    answer_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    router_confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    latency_budget_ms: int = Field(default=4000, ge=1)
    debug_mode: bool = False
    privacy_mode: bool = True
    enable_persistent_memory: bool = False
    memory_ttl_days: int = Field(default=30, ge=1)
    fast_path_regret_window: int = Field(default=2, ge=1, le=10)
    fast_path_regret_threshold: float = Field(default=0.2, ge=0.0, le=1.0)
    env_prefix: Literal["IMPERAOS"] = PRODUCT_IDENTITY.env_prefix
    web_enabled: bool = False
    remote_providers_enabled: bool = False
    provider_registry_enabled: bool = True
    provider_registry_path: str = "config/providers.toml"
    workspace_root: str = "."
    trace_dir: str = state_path("traces")
    router_dataset_path: str = state_path("research", "router_dataset.jsonl")
    limits: RuntimeLimits = Field(default_factory=RuntimeLimits)
    sltc: SLTCConfig = Field(default_factory=SLTCConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    planner_tuning: PlannerTuningConfig = Field(default_factory=PlannerTuningConfig)
    code_verify: CodeVerifyConfig = Field(default_factory=CodeVerifyConfig)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    team: TeamRuntimeConfig = Field(default_factory=TeamRuntimeConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    keys: KeyManagementConfig = Field(default_factory=KeyManagementConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    maintenance: MaintenanceConfig = Field(default_factory=MaintenanceConfig)
    computer_use: ComputerUseRuntimeConfig = Field(default_factory=ComputerUseRuntimeConfig)

    @classmethod
    def from_profile(cls, profile: str = "default", root_dir: Path | None = None) -> RuntimeConfig:
        resolved, _sources = resolve_runtime_config(profile=profile, root_dir=root_dir)
        return resolved

    @classmethod
    def from_toml(cls, path: str | Path) -> RuntimeConfig:
        config_path = Path(path)
        with config_path.open("rb") as file_obj:
            data = tomllib.load(file_obj)

        app_data = data.get("app", {})
        limits_data = data.get("limits", {})
        sltc_data = data.get("sltc", {})
        memory_data = data.get("memory", {})
        memory_runtime_data = memory_data.get("runtime", {})
        memory_sync_data = memory_data.get("sync", {})
        memory_workspace_authority_data = memory_data.get("workspace_authority", {})
        memory_semantic_data = memory_data.get("semantic", {})
        memory_semantic_backends_data = memory_semantic_data.get("backends", {})
        memory_semantic_turbovec_data = memory_semantic_backends_data.get("turbovec", {})
        planner_data = data.get("planner", {})
        code_verify_data = data.get("code_verify", {})
        governance_data = data.get("governance", {})
        team_data = data.get("team", {})
        security_data = data.get("security", {})
        identity_data = data.get("identity", {})
        keys_data = data.get("keys", {})
        observability_data = data.get("observability", {})
        maintenance_data = data.get("maintenance", {})
        computer_use_data = data.get("computer_use", {})
        return cls(
            model_name=app_data.get("model_name", "lfm2.5-thinking:1.2b"),
            profile_name=app_data.get("profile_name", "default"),
            llm_provider=app_data.get("llm_provider", "auto"),
            fallback_provider=app_data.get("fallback_provider", "transformers"),
            fallback_enabled=app_data.get("fallback_enabled", True),
            hf_model_id=app_data.get("hf_model_id", "distilgpt2"),
            device=app_data.get("device", "cpu"),
            router_mode=app_data.get("router_mode", "rule"),
            shadow_router_enabled=app_data.get("shadow_router_enabled", False),
            shadow_router_mode=app_data.get("shadow_router_mode", "sltc"),
            planner_temperature=app_data.get("planner_temperature", 0.0),
            answer_temperature=app_data.get("answer_temperature", 0.2),
            router_confidence_threshold=app_data.get("router_confidence_threshold", 0.6),
            latency_budget_ms=app_data.get("latency_budget_ms", 4000),
            debug_mode=app_data.get("debug_mode", False),
            privacy_mode=app_data.get("privacy_mode", True),
            enable_persistent_memory=app_data.get("enable_persistent_memory", False),
            memory_ttl_days=app_data.get("memory_ttl_days", 30),
            fast_path_regret_window=app_data.get("fast_path_regret_window", 2),
            fast_path_regret_threshold=app_data.get("fast_path_regret_threshold", 0.2),
            env_prefix=app_data.get("env_prefix", PRODUCT_IDENTITY.env_prefix),
            web_enabled=app_data.get("web_enabled", False),
            remote_providers_enabled=app_data.get("remote_providers_enabled", False),
            provider_registry_enabled=app_data.get("provider_registry_enabled", True),
            provider_registry_path=app_data.get("provider_registry_path", "config/providers.toml"),
            workspace_root=app_data.get("workspace_root", "."),
            trace_dir=app_data.get("trace_dir", state_path("traces")),
            router_dataset_path=app_data.get(
                "router_dataset_path",
                state_path("research", "router_dataset.jsonl"),
            ),
            limits=RuntimeLimits(
                expert_timeout_ms=limits_data.get("expert_timeout_ms", 2500),
                max_retries=limits_data.get("max_retries", 1),
                circuit_breaker_threshold=limits_data.get("circuit_breaker_threshold", 3),
                circuit_breaker_cooldown_s=limits_data.get("circuit_breaker_cooldown_s", 300),
                llm_timeout_ms=limits_data.get("llm_timeout_ms", 60000),
                max_tool_calls=limits_data.get("max_tool_calls", 4),
                max_recursion_depth=limits_data.get("max_recursion_depth", 3),
            ),
            sltc=SLTCConfig(
                enabled=sltc_data.get("enabled", False),
                router_mode=sltc_data.get("router_mode", "shadow"),
                decay=sltc_data.get("decay", 0.82),
                spike_threshold=sltc_data.get("spike_threshold", 0.55),
                confidence_threshold=sltc_data.get("confidence_threshold", 0.6),
                failure_penalty_weight=sltc_data.get("failure_penalty_weight", 0.35),
                latency_penalty_weight=sltc_data.get("latency_penalty_weight", 0.12),
                need_bonus=sltc_data.get("need_bonus", 0.12),
                conf_bonus=sltc_data.get("conf_bonus", 0.2),
                task_bias_overrides=sltc_data.get("task_bias_overrides", {}),
            ),
            memory=MemoryConfig(
                db_path=memory_data.get("db_path", state_path("memory.sqlite3")),
                v3_enabled=memory_data.get("v3_enabled", False),
                v3_authority_mode=memory_data.get("v3_authority_mode", "local"),
                raw_prompt_persistence=memory_data.get("raw_prompt_persistence", False),
                raw_response_persistence=memory_data.get("raw_response_persistence", False),
                raw_content_artifacts=memory_data.get("raw_content_artifacts", False),
                primary_ui_raw_content=memory_data.get("primary_ui_raw_content", False),
                semantic_index_enabled=memory_data.get("semantic_index_enabled", True),
                semantic_index_backend=memory_data.get("semantic_index_backend", "sqlite_text"),
                turbovec_experimental_enabled=memory_data.get(
                    "turbovec_experimental_enabled", False
                ),
                turbovec_bits_per_coord=memory_data.get("turbovec_bits_per_coord", 4),
                turbovec_dim_guard_max=memory_data.get("turbovec_dim_guard_max", 4096),
                salience_threshold=memory_data.get("salience_threshold", 0.62),
                salience_decay=memory_data.get("salience_decay", 0.82),
                max_rows=memory_data.get("max_rows", 5000),
                context_top_k=memory_data.get("context_top_k", 4),
                keyword_weights=memory_data.get("keyword_weights", MemoryConfig().keyword_weights),
                expert_bonus=memory_data.get("expert_bonus", 0.06),
                task_bonus=memory_data.get("task_bonus", 0.08),
                spike_reduction=memory_data.get("spike_reduction", 0.5),
                rank_salience_weight=memory_data.get("rank_salience_weight", 0.7),
                rank_recency_weight=memory_data.get("rank_recency_weight", 0.3),
                runtime=MemoryRuntimeConfig(
                    enabled=memory_runtime_data.get("enabled", False),
                    policy_enforcement_enabled=memory_runtime_data.get(
                        "policy_enforcement_enabled", False
                    ),
                    semantic_runtime_mode=memory_runtime_data.get(
                        "semantic_runtime_mode", "disabled"
                    ),
                    context_top_k=memory_runtime_data.get("context_top_k", 4),
                    max_context_chars=memory_runtime_data.get("max_context_chars", 4000),
                    post_run_write_enabled=memory_runtime_data.get(
                        "post_run_write_enabled", False
                    ),
                    post_run_default_scope=memory_runtime_data.get(
                        "post_run_default_scope", "personal"
                    ),
                    strict_fail_closed_profiles=memory_runtime_data.get(
                        "strict_fail_closed_profiles",
                        ["enterprise", "restricted"],
                    ),
                ),
                sync=MemorySyncConfig(
                    enabled=memory_sync_data.get("enabled", False),
                    export_raw_content=memory_sync_data.get("export_raw_content", False),
                    import_apply_requires_approval=memory_sync_data.get(
                        "import_apply_requires_approval", True
                    ),
                    allow_cross_environment_import=memory_sync_data.get(
                        "allow_cross_environment_import", False
                    ),
                ),
                workspace_authority=MemoryWorkspaceAuthorityConfig(
                    enabled=memory_workspace_authority_data.get("enabled", False),
                    mode=memory_workspace_authority_data.get("mode", "local"),
                    default_workspace_id=memory_workspace_authority_data.get(
                        "default_workspace_id", "default"
                    ),
                    default_principal_id=memory_workspace_authority_data.get(
                        "default_principal_id", "agent-local"
                    ),
                    db_path=memory_workspace_authority_data.get(
                        "db_path", state_path("workspace_memory.sqlite3")
                    ),
                    raw_content_persistence=memory_workspace_authority_data.get(
                        "raw_content_persistence", False
                    ),
                    network_listener_enabled=memory_workspace_authority_data.get(
                        "network_listener_enabled", False
                    ),
                    migration_apply_enabled=memory_workspace_authority_data.get(
                        "migration_apply_enabled", False
                    ),
                ),
                semantic=MemorySemanticConfig(
                    enabled=memory_semantic_data.get("enabled", False),
                    runtime_injection_enabled=memory_semantic_data.get(
                        "runtime_injection_enabled", False
                    ),
                    backend=memory_semantic_data.get("backend", "in_memory_fixture"),
                    embedding_profile=memory_semantic_data.get(
                        "embedding_profile", "deterministic-fixture-v1"
                    ),
                    max_hits=memory_semantic_data.get("max_hits", 8),
                    allow_stale_index=memory_semantic_data.get("allow_stale_index", False),
                    raw_persistence=memory_semantic_data.get("raw_persistence", False),
                    backends=MemorySemanticBackendsConfig(
                        turbovec=MemorySemanticTurboVecConfig(
                            enabled=memory_semantic_turbovec_data.get("enabled", False),
                            experimental=memory_semantic_turbovec_data.get(
                                "experimental", True
                            ),
                            bit_width=memory_semantic_turbovec_data.get("bit_width", 4),
                            allow_runtime_injection=memory_semantic_turbovec_data.get(
                                "allow_runtime_injection", False
                            ),
                        )
                    ),
                ),
            ),
            planner_tuning=PlannerTuningConfig(
                repair_enabled=planner_data.get("repair_enabled", True),
                repair_max_attempts=planner_data.get("repair_max_attempts", 1),
                prompt_variant=planner_data.get("prompt_variant", "strict_v2"),
            ),
            code_verify=CodeVerifyConfig(
                enabled=code_verify_data.get("enabled", True),
                lint_enabled=code_verify_data.get("lint_enabled", True),
                test_collect_enabled=code_verify_data.get("test_collect_enabled", True),
                targeted_tests_enabled=code_verify_data.get("targeted_tests_enabled", False),
                timeout_s=code_verify_data.get("timeout_s", 15),
                retry_max=code_verify_data.get("retry_max", 1),
                retry_strategy=code_verify_data.get("retry_strategy", "failure_aware"),
            ),
            governance=GovernanceConfig(
                enabled=governance_data.get("enabled", True),
                policy_path=governance_data.get("policy_path", "config/policies/default.toml"),
                policy_fail_mode=governance_data.get("policy_fail_mode", "fail_closed"),
                approval_store_path=governance_data.get(
                    "approval_store_path",
                    state_path("governance", "approvals.sqlite3"),
                ),
                audit_dir=governance_data.get("audit_dir", state_path("audit")),
                pii_redaction_enabled=governance_data.get("pii_redaction_enabled", True),
                approval_ttl_seconds=governance_data.get("approval_ttl_seconds", 86400),
                decision_engine_version=governance_data.get("decision_engine_version", "v0.3"),
            ),
            team=TeamRuntimeConfig(
                enabled=team_data.get("enabled", True),
                max_parallel_tasks=team_data.get("max_parallel_tasks", 4),
                max_total_tasks=team_data.get("max_total_tasks", 64),
                max_handoff_depth=team_data.get("max_handoff_depth", 8),
                checkpoint_db_path=team_data.get(
                    "checkpoint_db_path",
                    state_path("team", "checkpoints.sqlite3"),
                ),
                artifact_dir=team_data.get("artifact_dir", state_path("team", "jobs")),
            ),
            security=SecurityConfig(
                mode=security_data.get("mode", "default"),
                require_immutable_audit_export=security_data.get(
                    "require_immutable_audit_export", False
                ),
                allow_debug_privacy_override=security_data.get(
                    "allow_debug_privacy_override", False
                ),
                restricted_vs_admin_boundary=security_data.get(
                    "restricted_vs_admin_boundary", False
                ),
            ),
            identity=IdentityConfig(
                enabled=identity_data.get("enabled", False),
                mode=identity_data.get("mode", "disabled"),
                required_for_mutations=identity_data.get("required_for_mutations", False),
                assertion_path=identity_data.get(
                    "assertion_path", state_path("identity", "current_assertion.json")
                ),
                break_glass_assertion_path=identity_data.get(
                    "break_glass_assertion_path",
                    state_path("identity", "break_glass_assertion.json"),
                ),
                trusted_keys_dir=identity_data.get(
                    "trusted_keys_dir", state_path("keys", "trusted")
                ),
                allow_break_glass=identity_data.get("allow_break_glass", True),
                max_clock_skew_seconds=identity_data.get("max_clock_skew_seconds", 60),
                permission_model_version=identity_data.get("permission_model_version", "1.0"),
            ),
            keys=KeyManagementConfig(
                provider=keys_data.get("provider", "disabled"),
                current_key_id=keys_data.get("current_key_id"),
                private_key_path=keys_data.get(
                    "private_key_path", state_path("keys", "private", "current_key.json")
                ),
                trusted_public_keys_dir=keys_data.get(
                    "trusted_public_keys_dir", state_path("keys", "trusted")
                ),
                key_manifest_path=keys_data.get(
                    "key_manifest_path", state_path("keys", "manifest.json")
                ),
                managed_signer_command=keys_data.get("managed_signer_command", []),
                allow_env_hmac_compat=keys_data.get("allow_env_hmac_compat", True),
            ),
            observability=ObservabilityConfig(
                metrics_dir=observability_data.get("metrics_dir", state_path("metrics")),
                file_snapshot_enabled=observability_data.get("file_snapshot_enabled", True),
                prometheus_textfile_path=observability_data.get(
                    "prometheus_textfile_path",
                    state_path("metrics", "imperaos.prom"),
                ),
                http_exporter_enabled=observability_data.get("http_exporter_enabled", False),
                http_bind=observability_data.get("http_bind", "127.0.0.1:9464"),
            ),
            maintenance=MaintenanceConfig(
                maintenance_flag_path=maintenance_data.get(
                    "maintenance_flag_path", state_path("maintenance.lock")
                ),
                backup_dir=maintenance_data.get("backup_dir", state_path("backups")),
                restore_dir=maintenance_data.get("restore_dir", state_path("restores")),
                migration_dir=maintenance_data.get("migration_dir", state_path("migrations")),
                support_bundle_dir=maintenance_data.get(
                    "support_bundle_dir", state_path("support")
                ),
            ),
            computer_use=ComputerUseRuntimeConfig(
                enabled=computer_use_data.get("enabled", True),
                runtime_mode=computer_use_data.get("runtime_mode", "legacy_pilot"),
                vision_enabled=computer_use_data.get("vision_enabled", False),
                vision_provider=computer_use_data.get("vision_provider", "none"),
                vision_model=computer_use_data.get("vision_model") or None,
                vision_provider_timeout_s=computer_use_data.get(
                    "vision_provider_timeout_s", 30.0
                ),
                vision_provider_max_retries=computer_use_data.get(
                    "vision_provider_max_retries", 1
                ),
                default_mode=computer_use_data.get("default_mode", "step_approval"),
                max_steps=computer_use_data.get("max_steps", 50),
                max_recovery_attempts=computer_use_data.get("max_recovery_attempts", 3),
                max_consecutive_wait_actions=computer_use_data.get(
                    "max_consecutive_wait_actions", 3
                ),
                screenshot_interval_ms=computer_use_data.get("screenshot_interval_ms", 750),
                min_action_confidence=computer_use_data.get("min_action_confidence", 0.82),
                min_verification_confidence=computer_use_data.get(
                    "min_verification_confidence", 0.80
                ),
                macos_live_enabled=computer_use_data.get("macos_live_enabled", False),
                macos_capture_backend=computer_use_data.get(
                    "macos_capture_backend", "disabled"
                ),
                macos_input_backend=computer_use_data.get("macos_input_backend", "disabled"),
                macos_primary_display_only=computer_use_data.get(
                    "macos_primary_display_only", True
                ),
                macos_require_fresh_qualification=computer_use_data.get(
                    "macos_require_fresh_qualification", True
                ),
                macos_qualification_report=computer_use_data.get(
                    "macos_qualification_report", ""
                ),
                macos_max_steps=computer_use_data.get("macos_max_steps", 25),
                macos_step_delay_ms=computer_use_data.get("macos_step_delay_ms", 150),
                macos_require_step_approval=computer_use_data.get(
                    "macos_require_step_approval", True
                ),
                windows_live_enabled=computer_use_data.get("windows_live_enabled", False),
                windows_capture_backend=computer_use_data.get(
                    "windows_capture_backend", "disabled"
                ),
                windows_input_backend=computer_use_data.get(
                    "windows_input_backend", "disabled"
                ),
                linux_live_enabled=computer_use_data.get("linux_live_enabled", False),
                linux_capture_backend=computer_use_data.get(
                    "linux_capture_backend", "disabled"
                ),
                linux_input_backend=computer_use_data.get("linux_input_backend", "disabled"),
                action_set=computer_use_data.get(
                    "action_set",
                    ComputerUseRuntimeConfig().action_set,
                ),
                require_approval_for_type_text=computer_use_data.get(
                    "require_approval_for_type_text", True
                ),
                require_approval_for_hotkey=computer_use_data.get(
                    "require_approval_for_hotkey", True
                ),
                require_approval_for_download=computer_use_data.get(
                    "require_approval_for_download", True
                ),
                require_approval_for_upload=computer_use_data.get(
                    "require_approval_for_upload", True
                ),
                max_action_duration_ms=computer_use_data.get("max_action_duration_ms", 5000),
                post_action_observe_delay_ms=computer_use_data.get(
                    "post_action_observe_delay_ms", 500
                ),
                approval_snapshot_max_age_ms=computer_use_data.get(
                    "approval_snapshot_max_age_ms", 10000
                ),
                raw_screenshot_persistence=computer_use_data.get(
                    "raw_screenshot_persistence", False
                ),
                raw_screenshot_retention=computer_use_data.get(
                    "raw_screenshot_retention", "disabled"
                ),
                raw_screenshot_max_count=computer_use_data.get("raw_screenshot_max_count", 0),
                allowed_apps=computer_use_data.get("allowed_apps", []),
                blocked_apps=computer_use_data.get(
                    "blocked_apps",
                    ComputerUseRuntimeConfig().blocked_apps,
                ),
                terminal_control=computer_use_data.get("terminal_control", "deny"),
                sensitive_surface_policy=computer_use_data.get(
                    "sensitive_surface_policy", "stop"
                ),
                platform_qualification_required=computer_use_data.get(
                    "platform_qualification_required", True
                ),
            ),
        )


ENV_PATHS: dict[str, str] = {
    "MODEL_NAME": "model_name",
    "PROFILE_NAME": "profile_name",
    "LLM_PROVIDER": "llm_provider",
    "FALLBACK_PROVIDER": "fallback_provider",
    "FALLBACK_ENABLED": "fallback_enabled",
    "HF_MODEL_ID": "hf_model_id",
    "DEVICE": "device",
    "ROUTER_MODE": "router_mode",
    "SHADOW_ROUTER_ENABLED": "shadow_router_enabled",
    "SHADOW_ROUTER_MODE": "shadow_router_mode",
    "PLANNER_TEMPERATURE": "planner_temperature",
    "ANSWER_TEMPERATURE": "answer_temperature",
    "ROUTER_CONFIDENCE_THRESHOLD": "router_confidence_threshold",
    "LATENCY_BUDGET_MS": "latency_budget_ms",
    "DEBUG_MODE": "debug_mode",
    "PRIVACY_MODE": "privacy_mode",
    "ENABLE_PERSISTENT_MEMORY": "enable_persistent_memory",
    "MEMORY_TTL_DAYS": "memory_ttl_days",
    "FAST_PATH_REGRET_WINDOW": "fast_path_regret_window",
    "FAST_PATH_REGRET_THRESHOLD": "fast_path_regret_threshold",
    "WEB_ENABLED": "web_enabled",
    "REMOTE_PROVIDERS_ENABLED": "remote_providers_enabled",
    "PROVIDER_REGISTRY_ENABLED": "provider_registry_enabled",
    "PROVIDER_REGISTRY_PATH": "provider_registry_path",
    "WORKSPACE_ROOT": "workspace_root",
    "TRACE_DIR": "trace_dir",
    "ROUTER_DATASET_PATH": "router_dataset_path",
    "LIMITS_EXPERT_TIMEOUT_MS": "limits.expert_timeout_ms",
    "LIMITS_MAX_RETRIES": "limits.max_retries",
    "LIMITS_CIRCUIT_BREAKER_THRESHOLD": "limits.circuit_breaker_threshold",
    "LIMITS_CIRCUIT_BREAKER_COOLDOWN_S": "limits.circuit_breaker_cooldown_s",
    "LIMITS_LLM_TIMEOUT_MS": "limits.llm_timeout_ms",
    "LIMITS_MAX_TOOL_CALLS": "limits.max_tool_calls",
    "LIMITS_MAX_RECURSION_DEPTH": "limits.max_recursion_depth",
    "SLTC_ENABLED": "sltc.enabled",
    "SLTC_ROUTER_MODE": "sltc.router_mode",
    "SLTC_DECAY": "sltc.decay",
    "SLTC_SPIKE_THRESHOLD": "sltc.spike_threshold",
    "SLTC_CONFIDENCE_THRESHOLD": "sltc.confidence_threshold",
    "SLTC_FAILURE_PENALTY_WEIGHT": "sltc.failure_penalty_weight",
    "SLTC_LATENCY_PENALTY_WEIGHT": "sltc.latency_penalty_weight",
    "SLTC_NEED_BONUS": "sltc.need_bonus",
    "SLTC_CONF_BONUS": "sltc.conf_bonus",
    "MEMORY_DB_PATH": "memory.db_path",
    "MEMORY_SALIENCE_THRESHOLD": "memory.salience_threshold",
    "MEMORY_SALIENCE_DECAY": "memory.salience_decay",
    "MEMORY_MAX_ROWS": "memory.max_rows",
    "MEMORY_CONTEXT_TOP_K": "memory.context_top_k",
    "MEMORY_EXPERT_BONUS": "memory.expert_bonus",
    "MEMORY_TASK_BONUS": "memory.task_bonus",
    "MEMORY_SPIKE_REDUCTION": "memory.spike_reduction",
    "MEMORY_RANK_SALIENCE_WEIGHT": "memory.rank_salience_weight",
    "MEMORY_RANK_RECENCY_WEIGHT": "memory.rank_recency_weight",
    "PLANNER_REPAIR_ENABLED": "planner_tuning.repair_enabled",
    "PLANNER_REPAIR_MAX_ATTEMPTS": "planner_tuning.repair_max_attempts",
    "PLANNER_PROMPT_VARIANT": "planner_tuning.prompt_variant",
    "CODE_VERIFY_ENABLED": "code_verify.enabled",
    "CODE_VERIFY_LINT_ENABLED": "code_verify.lint_enabled",
    "CODE_VERIFY_TEST_COLLECT_ENABLED": "code_verify.test_collect_enabled",
    "CODE_VERIFY_TARGETED_TESTS_ENABLED": "code_verify.targeted_tests_enabled",
    "CODE_VERIFY_TIMEOUT_S": "code_verify.timeout_s",
    "CODE_RETRY_MAX": "code_verify.retry_max",
    "CODE_RETRY_STRATEGY": "code_verify.retry_strategy",
    "GOVERNANCE_ENABLED": "governance.enabled",
    "GOVERNANCE_POLICY_PATH": "governance.policy_path",
    "GOVERNANCE_POLICY_FAIL_MODE": "governance.policy_fail_mode",
    "GOVERNANCE_APPROVAL_STORE_PATH": "governance.approval_store_path",
    "GOVERNANCE_AUDIT_DIR": "governance.audit_dir",
    "GOVERNANCE_PII_REDACTION_ENABLED": "governance.pii_redaction_enabled",
    "GOVERNANCE_APPROVAL_TTL_SECONDS": "governance.approval_ttl_seconds",
    "GOVERNANCE_DECISION_ENGINE_VERSION": "governance.decision_engine_version",
    "TEAM_ENABLED": "team.enabled",
    "TEAM_MAX_PARALLEL_TASKS": "team.max_parallel_tasks",
    "TEAM_MAX_TOTAL_TASKS": "team.max_total_tasks",
    "TEAM_MAX_HANDOFF_DEPTH": "team.max_handoff_depth",
    "TEAM_CHECKPOINT_DB_PATH": "team.checkpoint_db_path",
    "TEAM_ARTIFACT_DIR": "team.artifact_dir",
    "SECURITY_MODE": "security.mode",
    "SECURITY_REQUIRE_IMMUTABLE_AUDIT_EXPORT": "security.require_immutable_audit_export",
    "SECURITY_ALLOW_DEBUG_PRIVACY_OVERRIDE": "security.allow_debug_privacy_override",
    "SECURITY_RESTRICTED_VS_ADMIN_BOUNDARY": "security.restricted_vs_admin_boundary",
    "IDENTITY_ENABLED": "identity.enabled",
    "IDENTITY_MODE": "identity.mode",
    "IDENTITY_REQUIRED_FOR_MUTATIONS": "identity.required_for_mutations",
    "IDENTITY_ASSERTION_PATH": "identity.assertion_path",
    "IDENTITY_BREAK_GLASS_ASSERTION_PATH": "identity.break_glass_assertion_path",
    "IDENTITY_TRUSTED_KEYS_DIR": "identity.trusted_keys_dir",
    "IDENTITY_ALLOW_BREAK_GLASS": "identity.allow_break_glass",
    "IDENTITY_MAX_CLOCK_SKEW_SECONDS": "identity.max_clock_skew_seconds",
    "KEYS_PROVIDER": "keys.provider",
    "KEYS_CURRENT_KEY_ID": "keys.current_key_id",
    "KEYS_PRIVATE_KEY_PATH": "keys.private_key_path",
    "KEYS_TRUSTED_PUBLIC_KEYS_DIR": "keys.trusted_public_keys_dir",
    "KEYS_KEY_MANIFEST_PATH": "keys.key_manifest_path",
    "KEYS_MANAGED_SIGNER_COMMAND": "keys.managed_signer_command",
    "KEYS_ALLOW_ENV_HMAC_COMPAT": "keys.allow_env_hmac_compat",
    "OBSERVABILITY_METRICS_DIR": "observability.metrics_dir",
    "OBSERVABILITY_FILE_SNAPSHOT_ENABLED": "observability.file_snapshot_enabled",
    "OBSERVABILITY_PROMETHEUS_TEXTFILE_PATH": "observability.prometheus_textfile_path",
    "OBSERVABILITY_HTTP_EXPORTER_ENABLED": "observability.http_exporter_enabled",
    "OBSERVABILITY_HTTP_BIND": "observability.http_bind",
    "MAINTENANCE_FLAG_PATH": "maintenance.maintenance_flag_path",
    "MAINTENANCE_BACKUP_DIR": "maintenance.backup_dir",
    "MAINTENANCE_RESTORE_DIR": "maintenance.restore_dir",
    "MAINTENANCE_MIGRATION_DIR": "maintenance.migration_dir",
    "MAINTENANCE_SUPPORT_BUNDLE_DIR": "maintenance.support_bundle_dir",
    "COMPUTER_USE_ENABLED": "computer_use.enabled",
    "COMPUTER_USE_RUNTIME_MODE": "computer_use.runtime_mode",
    "COMPUTER_USE_VISION_ENABLED": "computer_use.vision_enabled",
    "COMPUTER_USE_VISION_PROVIDER": "computer_use.vision_provider",
    "COMPUTER_USE_VISION_MODEL": "computer_use.vision_model",
    "COMPUTER_USE_VISION_PROVIDER_TIMEOUT_S": "computer_use.vision_provider_timeout_s",
    "COMPUTER_USE_VISION_PROVIDER_MAX_RETRIES": "computer_use.vision_provider_max_retries",
    "COMPUTER_USE_DEFAULT_MODE": "computer_use.default_mode",
    "COMPUTER_USE_MAX_STEPS": "computer_use.max_steps",
    "COMPUTER_USE_MAX_RECOVERY_ATTEMPTS": "computer_use.max_recovery_attempts",
    "COMPUTER_USE_MAX_CONSECUTIVE_WAIT_ACTIONS": (
        "computer_use.max_consecutive_wait_actions"
    ),
    "COMPUTER_USE_SCREENSHOT_INTERVAL_MS": "computer_use.screenshot_interval_ms",
    "COMPUTER_USE_MIN_ACTION_CONFIDENCE": "computer_use.min_action_confidence",
    "COMPUTER_USE_MIN_VERIFICATION_CONFIDENCE": "computer_use.min_verification_confidence",
    "COMPUTER_USE_MACOS_LIVE_ENABLED": "computer_use.macos_live_enabled",
    "COMPUTER_USE_MACOS_CAPTURE_BACKEND": "computer_use.macos_capture_backend",
    "COMPUTER_USE_MACOS_INPUT_BACKEND": "computer_use.macos_input_backend",
    "COMPUTER_USE_MACOS_PRIMARY_DISPLAY_ONLY": "computer_use.macos_primary_display_only",
    "COMPUTER_USE_MACOS_REQUIRE_FRESH_QUALIFICATION": (
        "computer_use.macos_require_fresh_qualification"
    ),
    "COMPUTER_USE_MACOS_QUALIFICATION_REPORT": "computer_use.macos_qualification_report",
    "COMPUTER_USE_MACOS_MAX_STEPS": "computer_use.macos_max_steps",
    "COMPUTER_USE_MACOS_STEP_DELAY_MS": "computer_use.macos_step_delay_ms",
    "COMPUTER_USE_MACOS_REQUIRE_STEP_APPROVAL": (
        "computer_use.macos_require_step_approval"
    ),
    "COMPUTER_USE_WINDOWS_LIVE_ENABLED": "computer_use.windows_live_enabled",
    "COMPUTER_USE_WINDOWS_CAPTURE_BACKEND": "computer_use.windows_capture_backend",
    "COMPUTER_USE_WINDOWS_INPUT_BACKEND": "computer_use.windows_input_backend",
    "COMPUTER_USE_LINUX_LIVE_ENABLED": "computer_use.linux_live_enabled",
    "COMPUTER_USE_LINUX_CAPTURE_BACKEND": "computer_use.linux_capture_backend",
    "COMPUTER_USE_LINUX_INPUT_BACKEND": "computer_use.linux_input_backend",
    "COMPUTER_USE_ACTION_SET": "computer_use.action_set",
    "COMPUTER_USE_REQUIRE_APPROVAL_FOR_TYPE_TEXT": (
        "computer_use.require_approval_for_type_text"
    ),
    "COMPUTER_USE_REQUIRE_APPROVAL_FOR_HOTKEY": "computer_use.require_approval_for_hotkey",
    "COMPUTER_USE_REQUIRE_APPROVAL_FOR_DOWNLOAD": "computer_use.require_approval_for_download",
    "COMPUTER_USE_REQUIRE_APPROVAL_FOR_UPLOAD": "computer_use.require_approval_for_upload",
    "COMPUTER_USE_MAX_ACTION_DURATION_MS": "computer_use.max_action_duration_ms",
    "COMPUTER_USE_POST_ACTION_OBSERVE_DELAY_MS": "computer_use.post_action_observe_delay_ms",
    "COMPUTER_USE_APPROVAL_SNAPSHOT_MAX_AGE_MS": (
        "computer_use.approval_snapshot_max_age_ms"
    ),
    "COMPUTER_USE_RAW_SCREENSHOT_PERSISTENCE": "computer_use.raw_screenshot_persistence",
    "COMPUTER_USE_RAW_SCREENSHOT_RETENTION": "computer_use.raw_screenshot_retention",
    "COMPUTER_USE_RAW_SCREENSHOT_MAX_COUNT": "computer_use.raw_screenshot_max_count",
    "COMPUTER_USE_ALLOWED_APPS": "computer_use.allowed_apps",
    "COMPUTER_USE_BLOCKED_APPS": "computer_use.blocked_apps",
    "COMPUTER_USE_TERMINAL_CONTROL": "computer_use.terminal_control",
    "COMPUTER_USE_SENSITIVE_SURFACE_POLICY": "computer_use.sensitive_surface_policy",
    "COMPUTER_USE_PLATFORM_QUALIFICATION_REQUIRED": (
        "computer_use.platform_qualification_required"
    ),
}


def resolve_runtime_config(
    *,
    profile: str = "default",
    root_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
) -> tuple[RuntimeConfig, dict[str, str]]:
    base = RuntimeConfig().model_dump(mode="python")
    source_map = _build_default_source_map(base)

    profile_payload = _load_profile_payload(profile=profile, root_dir=root_dir, env=env)
    _deep_merge(base, profile_payload, source="profile", source_map=source_map)

    env_payload = _build_env_payload(env=env, env_prefix=PRODUCT_IDENTITY.env_prefix)
    _deep_merge(base, env_payload, source="env", source_map=source_map)

    cli_payload = _build_cli_payload(cli_overrides or {})
    _deep_merge(base, cli_payload, source="cli", source_map=source_map)

    config = RuntimeConfig.model_validate(base)
    return config, source_map


def redact_config_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    redacted = _deep_copy_dict(payload)
    sensitive_markers = ("token", "secret", "password", "key")
    for path in _iter_leaf_paths(redacted):
        key = path.split(".")[-1].lower()
        if any(marker in key for marker in sensitive_markers):
            _set_in_dict(redacted, path, "***REDACTED***")
    return redacted


def _load_profile_payload(
    *,
    profile: str,
    root_dir: Path | None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    values = env or os.environ
    config_root_key = f"{PRODUCT_IDENTITY.env_prefix}_CONFIG_ROOT"
    config_root = str(values.get(config_root_key) or "").strip()
    if root_dir is not None:
        config_dir = root_dir / "config"
    elif config_root:
        configured = Path(config_root)
        config_dir = (
            configured if (configured / f"{profile}.toml").exists() else configured / "config"
        )
    else:
        config_dir = Path(__file__).resolve().parents[2] / "config"
    config_path = config_dir / f"{profile}.toml"
    with config_path.open("rb") as file_obj:
        data = tomllib.load(file_obj)

    app_data = dict(data.get("app", {}))
    app_data["profile_name"] = profile
    payload: dict[str, Any] = {
        **app_data,
        "limits": dict(data.get("limits", {})),
        "sltc": dict(data.get("sltc", {})),
        "memory": dict(data.get("memory", {})),
        "planner_tuning": dict(data.get("planner", {})),
        "code_verify": dict(data.get("code_verify", {})),
        "governance": dict(data.get("governance", {})),
        "team": dict(data.get("team", {})),
        "security": dict(data.get("security", {})),
        "identity": dict(data.get("identity", {})),
        "keys": dict(data.get("keys", {})),
        "observability": dict(data.get("observability", {})),
        "maintenance": dict(data.get("maintenance", {})),
        "computer_use": dict(data.get("computer_use", {})),
    }
    return payload


def _build_env_payload(*, env: Mapping[str, str] | None, env_prefix: str) -> dict[str, Any]:
    values = env or os.environ
    payload: dict[str, Any] = {}
    defaults = RuntimeConfig().model_dump(mode="python")
    prefix = f"{env_prefix}_"
    for env_key, path in ENV_PATHS.items():
        full_key = f"{prefix}{env_key}"
        if full_key not in values:
            continue
        raw_value = values[full_key]
        current = _get_from_dict(defaults, path)
        coerced = _coerce_value(raw_value, current)
        _set_in_dict(payload, path, coerced)
    return payload


def _build_cli_payload(cli_overrides: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in cli_overrides.items():
        if value is None:
            continue
        if key in {"source_map", "json"}:
            continue
        _set_in_dict(payload, key, value)
    return payload


def _build_default_source_map(payload: Mapping[str, Any]) -> dict[str, str]:
    return {path: "defaults" for path in _iter_leaf_paths(payload)}


def _iter_leaf_paths(payload: Mapping[str, Any], prefix: str = "") -> list[str]:
    result: list[str] = []
    for key in sorted(payload.keys()):
        path = f"{prefix}.{key}" if prefix else str(key)
        value = payload[key]
        if isinstance(value, Mapping):
            result.extend(_iter_leaf_paths(value, path))
        else:
            result.append(path)
    return result


def _deep_merge(
    target: dict[str, Any],
    update: Mapping[str, Any],
    *,
    source: str,
    source_map: dict[str, str],
    prefix: str = "",
) -> None:
    for key, value in update.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            existing = target.get(key)
            if not isinstance(existing, dict):
                existing = {}
                target[key] = existing
            _deep_merge(existing, value, source=source, source_map=source_map, prefix=path)
            continue
        target[key] = value
        source_map[path] = source


def _get_from_dict(data: Mapping[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _set_in_dict(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        nxt = current.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            current[part] = nxt
        current = nxt
    current[parts[-1]] = value


def _coerce_value(raw: str, template: Any) -> Any:
    if isinstance(template, bool):
        lowered = raw.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
        raise ValueError(f"invalid bool env value: {raw}")
    if isinstance(template, int) and not isinstance(template, bool):
        return int(raw.strip())
    if isinstance(template, float):
        return float(raw.strip())
    if isinstance(template, list):
        try:
            parsed = tomllib.loads(f"value = {raw}")["value"]
            if isinstance(parsed, list):
                return parsed
        except Exception:  # noqa: BLE001
            return [item.strip() for item in raw.split(",") if item.strip()]
        return template
    return raw


def _deep_copy_dict(data: Mapping[str, Any]) -> dict[str, Any]:
    copied: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, Mapping):
            copied[str(key)] = _deep_copy_dict(value)
        else:
            copied[str(key)] = value
    return copied
