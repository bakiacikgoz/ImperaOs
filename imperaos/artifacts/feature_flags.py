from __future__ import annotations

from collections.abc import Mapping

ARTIFACT_FEATURE_FLAG_NAMES = (
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
)


def resolve_artifact_feature_flags(
    requested: Mapping[str, bool],
    *,
    license_capabilities: Mapping[str, bool] | None = None,
    fallback_capabilities: Mapping[str, bool] | None = None,
) -> dict[str, bool]:
    """Resolve the fail-closed enterprise rollout state.

    Unknown keys are ignored. A renderer request can further disable a feature,
    but commercial editor requests cannot manufacture backend entitlement.
    """

    resolved = {name: False for name in ARTIFACT_FEATURE_FLAG_NAMES}
    if requested.get("artifact_workspace.enabled") is not True:
        return resolved

    resolved["artifact_workspace.enabled"] = True
    for name in ARTIFACT_FEATURE_FLAG_NAMES[1:]:
        resolved[name] = requested.get(name) is True

    capabilities = license_capabilities or {}
    fallbacks = fallback_capabilities or {}
    resolved["artifact_workspace.spreadsheet.enabled"] &= (
        capabilities.get("spreadsheet") is True or fallbacks.get("spreadsheet") is True
    )
    resolved["artifact_workspace.canvas.enabled"] &= (
        capabilities.get("canvas") is True or fallbacks.get("canvas") is True
    )
    return resolved
