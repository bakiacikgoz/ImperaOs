from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from imperaos.runtime.config import RuntimeConfig

LEGACY_STATE_ROOT = "." + "bin" + "liquid"


def test_runtime_paths_module_exists() -> None:
    assert importlib.util.find_spec("imperaos.runtime.paths") is not None


def test_state_path_builds_stable_repo_relative_paths() -> None:
    paths = importlib.import_module("imperaos.runtime.paths")

    assert Path(".imperaos") == paths.DEFAULT_STATE_ROOT
    assert paths.state_path() == ".imperaos"
    assert paths.state_path("team", "jobs", "job.json") == ".imperaos/team/jobs/job.json"
    assert paths.state_path("team\\jobs", "job.json") == ".imperaos/team/jobs/job.json"
    assert paths.CONTROL_PLANE_STATE_ROOT == ".imperaos/control-plane"
    assert paths.ENTERPRISE_STATE_ROOT == ".imperaos/enterprise"


def test_enterprise_state_path_builds_beneath_enterprise_root() -> None:
    paths = importlib.import_module("imperaos.runtime.paths")

    assert paths.enterprise_state_path() == ".imperaos/enterprise"
    assert paths.enterprise_state_path("keys", "manifest.json") == (
        ".imperaos/enterprise/keys/manifest.json"
    )


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "/etc/passwd",
        "C:\\Windows\\system32",
        "\\\\server\\share\\secret",
        "//server/share/secret",
        "C:relative\\secret",
        "..",
        "safe/../secret",
        "safe\\..\\secret",
        "\0",
        "safe\0secret",
    ],
)
@pytest.mark.parametrize("helper_name", ["state_path", "enterprise_state_path"])
def test_runtime_path_helpers_reject_unsafe_paths(
    helper_name: str,
    unsafe_path: str,
) -> None:
    paths = importlib.import_module("imperaos.runtime.paths")

    with pytest.raises(ValueError):
        getattr(paths, helper_name)(unsafe_path)


def test_runtime_path_helpers_reject_root_reset_in_later_parts() -> None:
    paths = importlib.import_module("imperaos.runtime.paths")

    with pytest.raises(ValueError):
        paths.state_path("safe", "/etc/passwd")
    with pytest.raises(ValueError):
        paths.enterprise_state_path("safe", "D:\\secret")


def test_runtime_config_defaults_use_imperaos_state_root() -> None:
    payload = RuntimeConfig().model_dump(mode="json")

    assert LEGACY_STATE_ROOT not in json.dumps(payload, sort_keys=True)
    assert payload["trace_dir"] == ".imperaos/traces"
    assert payload["memory"]["db_path"] == ".imperaos/memory.sqlite3"
    assert payload["team"]["artifact_dir"] == ".imperaos/team/jobs"
    assert payload["observability"]["prometheus_textfile_path"] == (
        ".imperaos/metrics/imperaos.prom"
    )


@pytest.mark.parametrize(
    "profile",
    ["balanced", "default", "enterprise", "lite", "research", "restricted"],
)
def test_shipped_profiles_contain_no_legacy_state_paths(profile: str) -> None:
    payload = RuntimeConfig.from_profile(profile).model_dump(mode="json")

    assert LEGACY_STATE_ROOT not in json.dumps(payload, sort_keys=True)


def test_enterprise_profile_keeps_all_state_beneath_enterprise_root() -> None:
    config = RuntimeConfig.from_profile("enterprise")
    state_paths = (
        config.trace_dir,
        config.router_dataset_path,
        config.memory.db_path,
        config.memory.workspace_authority.db_path,
        config.governance.approval_store_path,
        config.governance.audit_dir,
        config.team.checkpoint_db_path,
        config.team.artifact_dir,
        config.identity.assertion_path,
        config.identity.break_glass_assertion_path,
        config.identity.trusted_keys_dir,
        config.keys.private_key_path,
        config.keys.trusted_public_keys_dir,
        config.keys.key_manifest_path,
        config.observability.metrics_dir,
        config.observability.prometheus_textfile_path,
        config.maintenance.maintenance_flag_path,
        config.maintenance.backup_dir,
        config.maintenance.restore_dir,
        config.maintenance.migration_dir,
        config.maintenance.support_bundle_dir,
    )

    assert all(path.startswith(".imperaos/enterprise/") for path in state_paths)
