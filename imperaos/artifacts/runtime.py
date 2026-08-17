from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal

from imperaos.artifacts.feature_flags import (
    ARTIFACT_FEATURE_FLAG_NAMES,
    resolve_artifact_feature_flags,
)
from imperaos.artifacts.models import ArtifactKind, ArtifactModel
from imperaos.artifacts.rollout import resolve_artifact_rollout_profile
from imperaos.governance.approval_store import ApprovalStore
from imperaos.runtime.config import resolve_runtime_config

ARTIFACT_FEATURE_FLAG_ENV = {
    "artifact_workspace.enabled": "IMPERAOS_ARTIFACT_WORKSPACE_ENABLED",
    "artifact_workspace.document.enabled": "IMPERAOS_ARTIFACT_DOCUMENT_EDITOR_ENABLED",
    "artifact_workspace.form.enabled": "IMPERAOS_ARTIFACT_FORM_EDITOR_ENABLED",
    "artifact_workspace.code.enabled": "IMPERAOS_ARTIFACT_CODE_EDITOR_ENABLED",
    "artifact_workspace.flow.enabled": "IMPERAOS_ARTIFACT_FLOW_EDITOR_ENABLED",
    "artifact_workspace.spreadsheet.enabled": "IMPERAOS_ARTIFACT_SPREADSHEET_EDITOR_ENABLED",
    "artifact_workspace.canvas.enabled": "IMPERAOS_ARTIFACT_CANVAS_EDITOR_ENABLED",
    "artifact_workspace.slides.enabled": "IMPERAOS_ARTIFACT_SLIDES_EDITOR_ENABLED",
    "artifact_workspace.export.enabled": "IMPERAOS_ARTIFACT_EXPORT_ENABLED",
    "assistant_ui_runtime.enabled": "IMPERAOS_ASSISTANT_UI_RUNTIME_ENABLED",
    "ai_sdk_tauri_transport.enabled": "IMPERAOS_ASSISTANT_AI_SDK_RUNTIME_ENABLED",
}
ARTIFACT_ROLLOUT_PROFILE_ENV = "IMPERAOS_ARTIFACT_WORKSPACE_PROFILE"

ARTIFACT_RUNTIME_CAPABILITY_SNAPSHOT_VERSION = (
    "artifact-runtime-capability-snapshot/v1"
)
_ARTIFACT_KIND_FEATURE_FLAGS = {
    ArtifactKind.DOCUMENT: "artifact_workspace.document.enabled",
    ArtifactKind.FORM: "artifact_workspace.form.enabled",
    ArtifactKind.CODE: "artifact_workspace.code.enabled",
    ArtifactKind.FLOW: "artifact_workspace.flow.enabled",
    ArtifactKind.SPREADSHEET: "artifact_workspace.spreadsheet.enabled",
    ArtifactKind.CANVAS: "artifact_workspace.canvas.enabled",
    ArtifactKind.SLIDES: "artifact_workspace.slides.enabled",
}


class ArtifactKindRuntimeCapability(ArtifactModel):
    """Effective per-kind capability state safe to expose to the renderer."""

    enabled: bool
    editable: bool
    exportable: bool
    reason_code: str | None = None
    requires_license: bool
    adapter: Literal["built_in", "bundled_fallback", "commercial", "unavailable"]


class ArtifactRuntimeCapabilitySnapshot(ArtifactModel):
    """Redacted, effective rollout state safe to expose through the RPC handshake."""

    contract_version: Literal["artifact-runtime-capability-snapshot/v1"] = (
        ARTIFACT_RUNTIME_CAPABILITY_SNAPSHOT_VERSION
    )
    rollout_stage: Literal[
        "disabled",
        "workspace_only",
        "document",
        "form_code",
        "flow_slides",
        "all_noncommercial",
    ]
    global_enabled: bool
    enabled_artifact_kinds: list[ArtifactKind]
    features: dict[str, bool]
    licenses: dict[Literal["spreadsheet", "canvas"], bool]
    kind_capabilities: dict[str, ArtifactKindRuntimeCapability]

if tuple(ARTIFACT_FEATURE_FLAG_ENV) != ARTIFACT_FEATURE_FLAG_NAMES:
    raise RuntimeError("artifact feature flag environment mapping drifted")


def resolve_artifact_approval_store(
    profile: str,
    *,
    env: Mapping[str, str] | None = None,
) -> ApprovalStore:
    """Resolve the single governance approval authority used by artifact runtimes."""

    config, _ = resolve_runtime_config(profile=profile, env=env)
    return ApprovalStore(config.governance.approval_store_path)


def resolve_runtime_artifact_feature_flags(
    *,
    env: Mapping[str, str] | None = None,
    license_capabilities: Mapping[str, bool] | None = None,
) -> dict[str, bool]:
    """Resolve backend-owned rollout authority from trusted process configuration."""

    environment = os.environ if env is None else env
    fallback_capabilities = {"spreadsheet": True, "canvas": True}
    effective_editor_capabilities = {
        kind: (license_capabilities or {}).get(kind) is True
        or fallback_capabilities[kind]
        for kind in fallback_capabilities
    }
    profile = environment.get(ARTIFACT_ROLLOUT_PROFILE_ENV)
    requested = (
        resolve_artifact_rollout_profile(
            profile,
            editor_capabilities=effective_editor_capabilities,
        )
        if profile is not None
        else {name: False for name in ARTIFACT_FEATURE_FLAG_NAMES}
    )
    for name, env_name in ARTIFACT_FEATURE_FLAG_ENV.items():
        if env_name in environment:
            requested[name] = _enabled(environment[env_name])
    return resolve_artifact_feature_flags(
        requested,
        license_capabilities=license_capabilities,
        fallback_capabilities=fallback_capabilities,
    )


def build_runtime_artifact_capability_snapshot(
    feature_flags: Mapping[str, bool] | None,
    *,
    license_capabilities: Mapping[str, bool] | None = None,
) -> dict[str, object]:
    """Build the effective, fail-closed rollout snapshot for untrusted consumers.

    The snapshot deliberately omits process environment values, paths, and
    license evidence. It reports only backend-resolved boolean capability state.
    """

    licenses: dict[Literal["spreadsheet", "canvas"], bool] = {
        "spreadsheet": (license_capabilities or {}).get("spreadsheet") is True,
        "canvas": (license_capabilities or {}).get("canvas") is True,
    }
    requested = {
        name: (feature_flags or {}).get(name) is True
        for name in ARTIFACT_FEATURE_FLAG_NAMES
    }
    # ArtifactService supplies already-resolved backend authority. Do not let a
    # renderer-facing snapshot re-apply commercial-license gating over the
    # supported open-source fallback adapters.
    resolved = requested
    enabled_kinds = tuple(
        kind
        for kind, flag_name in _ARTIFACT_KIND_FEATURE_FLAGS.items()
        if resolved[flag_name]
    )
    kind_capabilities = {
        kind.value: _kind_capability(kind, resolved, licenses)
        for kind in _ARTIFACT_KIND_FEATURE_FLAGS
    }
    snapshot = ArtifactRuntimeCapabilitySnapshot(
        rollout_stage=_rollout_stage(resolved),
        global_enabled=resolved["artifact_workspace.enabled"],
        enabled_artifact_kinds=list(enabled_kinds),
        features=resolved,
        licenses=licenses,
        kind_capabilities=kind_capabilities,
    )
    return snapshot.model_dump(mode="json", by_alias=True)


def _kind_capability(
    kind: ArtifactKind,
    feature_flags: Mapping[str, bool],
    licenses: Mapping[str, bool],
) -> ArtifactKindRuntimeCapability:
    enabled = feature_flags[_ARTIFACT_KIND_FEATURE_FLAGS[kind]]
    global_enabled = feature_flags["artifact_workspace.enabled"]
    exportable = enabled and feature_flags["artifact_workspace.export.enabled"]
    if not global_enabled:
        reason_code = "ARTIFACT_WORKSPACE_FEATURE_DISABLED"
    elif not enabled:
        reason_code = "ARTIFACT_KIND_FEATURE_DISABLED"
    elif not exportable:
        reason_code = "ARTIFACT_EXPORT_FEATURE_DISABLED"
    else:
        reason_code = None

    if kind in {ArtifactKind.SPREADSHEET, ArtifactKind.CANVAS}:
        adapter = "commercial" if licenses[kind.value] else "bundled_fallback"
    else:
        adapter = "built_in"
    return ArtifactKindRuntimeCapability(
        enabled=enabled,
        editable=enabled,
        exportable=exportable,
        reason_code=reason_code,
        requires_license=False,
        adapter=adapter,
    )


def _rollout_stage(feature_flags: Mapping[str, bool]) -> str:
    if feature_flags.get("artifact_workspace.enabled") is not True:
        return "disabled"
    if all(
        feature_flags.get(flag_name) is not True
        for flag_name in _ARTIFACT_KIND_FEATURE_FLAGS.values()
    ):
        return "workspace_only"
    if all(
        feature_flags.get(flag_name) is True
        for flag_name in (
            "artifact_workspace.document.enabled",
            "artifact_workspace.form.enabled",
            "artifact_workspace.code.enabled",
            "artifact_workspace.flow.enabled",
            "artifact_workspace.slides.enabled",
        )
    ):
        return "all_noncommercial"
    if feature_flags.get("artifact_workspace.flow.enabled") is True or feature_flags.get(
        "artifact_workspace.slides.enabled"
    ) is True:
        return "flow_slides"
    if feature_flags.get("artifact_workspace.form.enabled") is True or feature_flags.get(
        "artifact_workspace.code.enabled"
    ) is True:
        return "form_code"
    return "document"


def _enabled(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}
