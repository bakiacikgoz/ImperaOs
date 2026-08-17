from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from imperaos.artifacts.feature_flags import (
    ARTIFACT_FEATURE_FLAG_NAMES,
    resolve_artifact_feature_flags,
)

ArtifactRolloutProfileName = Literal[
    "artifact_workspace_off",
    "artifact_workspace_core",
    "artifact_workspace_full",
]

_ENABLED_PROFILE_FLAGS = frozenset(
    {
        "artifact_workspace.enabled",
        "artifact_workspace.document.enabled",
        "artifact_workspace.form.enabled",
        "artifact_workspace.code.enabled",
        "artifact_workspace.flow.enabled",
        "artifact_workspace.spreadsheet.enabled",
        "artifact_workspace.canvas.enabled",
        "artifact_workspace.slides.enabled",
        "artifact_workspace.export.enabled",
        "assistant_ui_runtime.enabled",
        "ai_sdk_tauri_transport.enabled",
    }
)


def resolve_artifact_rollout_profile(
    profile: str,
    *,
    editor_capabilities: Mapping[str, bool] | None = None,
) -> dict[str, bool]:
    """Resolve a named rollout profile against available editor adapters."""

    if profile not in {
        "artifact_workspace_off",
        "artifact_workspace_core",
        "artifact_workspace_full",
    }:
        raise ValueError(f"unknown artifact workspace rollout profile: {profile}")

    if profile == "artifact_workspace_off":
        return {name: False for name in ARTIFACT_FEATURE_FLAG_NAMES}

    requested = {
        name: name in _ENABLED_PROFILE_FLAGS for name in ARTIFACT_FEATURE_FLAG_NAMES
    }
    return resolve_artifact_feature_flags(
        requested,
        fallback_capabilities=editor_capabilities,
    )
