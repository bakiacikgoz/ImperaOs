from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from imperaos.artifacts.commands import (
    ArchiveArtifactCommand,
    ArtifactHistoryQuery,
    BeginArtifactExportCommand,
    CreateArtifactCommand,
    GetArtifactQuery,
    ListArtifactsQuery,
)
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.feature_flags import (
    ARTIFACT_FEATURE_FLAG_NAMES,
    resolve_artifact_feature_flags,
)
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    OperationContext,
    PrincipalType,
)
from imperaos.artifacts.runtime import (
    build_runtime_artifact_capability_snapshot,
    resolve_runtime_artifact_feature_flags,
)
from imperaos.artifacts.service import ArtifactService


def test_feature_flag_contract_has_the_exact_phase_24_names() -> None:
    root = Path(__file__).resolve().parents[1]
    contract = json.loads(
        (root / "contracts/artifact_workspace/feature_flags.json").read_text(
            encoding="utf-8"
        )
    )
    assert tuple(contract["flags"]) == ARTIFACT_FEATURE_FLAG_NAMES
    assert all(value is False for value in contract["defaults"].values())
    assert set(contract["profiles"]) == {
        "artifact_workspace_off",
        "artifact_workspace_core",
        "artifact_workspace_full",
    }
    assert all(
        value is False
        for value in contract["profiles"]["artifact_workspace_off"]["features"].values()
    )
    assert all(
        value is True
        for value in contract["profiles"]["artifact_workspace_core"]["features"].values()
    )
    assert set(
        contract["profiles"]["artifact_workspace_full"]["features"]
    ) == set(ARTIFACT_FEATURE_FLAG_NAMES)


def test_named_rollout_profiles_are_exact_and_capability_aware() -> None:
    resolve_artifact_rollout_profile = importlib.import_module(
        "imperaos.artifacts.rollout"
    ).resolve_artifact_rollout_profile
    off = resolve_artifact_rollout_profile("artifact_workspace_off")
    assert all(value is False for value in off.values())

    core = resolve_artifact_rollout_profile(
        "artifact_workspace_core",
        editor_capabilities={"spreadsheet": True, "canvas": False},
    )
    assert core["artifact_workspace.enabled"] is True
    assert core["artifact_workspace.document.enabled"] is True
    assert core["artifact_workspace.form.enabled"] is True
    assert core["artifact_workspace.code.enabled"] is True
    assert core["artifact_workspace.flow.enabled"] is True
    assert core["artifact_workspace.slides.enabled"] is True
    assert core["artifact_workspace.export.enabled"] is True
    assert core["assistant_ui_runtime.enabled"] is True
    assert core["ai_sdk_tauri_transport.enabled"] is True
    assert core["artifact_workspace.spreadsheet.enabled"] is True
    assert core["artifact_workspace.canvas.enabled"] is False

    full = resolve_artifact_rollout_profile(
        "artifact_workspace_full",
        editor_capabilities={"spreadsheet": True, "canvas": True},
    )
    assert all(value is True for value in full.values())

    with pytest.raises(ValueError, match="unknown artifact workspace rollout profile"):
        resolve_artifact_rollout_profile("untrusted_profile")


def test_runtime_profile_can_be_narrowed_by_explicit_environment_flags() -> None:
    resolved = resolve_runtime_artifact_feature_flags(
        env={
            "IMPERAOS_ARTIFACT_WORKSPACE_PROFILE": "artifact_workspace_core",
            "IMPERAOS_ARTIFACT_FLOW_EDITOR_ENABLED": "false",
        },
    )
    assert resolved["artifact_workspace.enabled"] is True
    assert resolved["artifact_workspace.document.enabled"] is True
    assert resolved["artifact_workspace.flow.enabled"] is False
    assert resolved["artifact_workspace.spreadsheet.enabled"] is True
    assert resolved["artifact_workspace.canvas.enabled"] is True


def test_global_off_and_license_capabilities_are_authoritative() -> None:
    requested = {name: True for name in ARTIFACT_FEATURE_FLAG_NAMES}
    requested["artifact_workspace.enabled"] = False
    global_off = resolve_artifact_feature_flags(
        requested,
        license_capabilities={"spreadsheet": True, "canvas": True},
    )
    assert all(value is False for value in global_off.values())

    requested["artifact_workspace.enabled"] = True
    resolved = resolve_artifact_feature_flags(
        requested,
        license_capabilities={"spreadsheet": False, "canvas": False},
    )
    assert resolved["artifact_workspace.document.enabled"] is True
    assert resolved["artifact_workspace.spreadsheet.enabled"] is False
    assert resolved["artifact_workspace.canvas.enabled"] is False


def test_runtime_flags_default_off_and_service_revalidates_authority(
    tmp_path: Path,
) -> None:
    disabled = resolve_runtime_artifact_feature_flags(env={})
    assert all(value is False for value in disabled.values())

    service = ArtifactService(tmp_path / "artifacts", feature_flags=disabled)
    command = CreateArtifactCommand(
        artifact_id="artifact-disabled",
        kind=ArtifactKind.DOCUMENT,
        title="Disabled",
        data_class=ArtifactDataClass.INTERNAL,
        content={
            "kind": "document",
            "schemaVersion": 1,
            "language": "tr",
            "pageMode": "document",
            "blocks": [],
        },
        idempotency_key="disabled-create",
    )
    context = OperationContext(
        workspace_id="workspace-1",
        principal_type=PrincipalType.USER,
        principal_id="user-1",
        roles=("artifact_editor",),
        request_id="request-disabled",
    )
    with pytest.raises(ArtifactDomainError) as caught:
        service.create(command, context)
    assert caught.value.code is ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE
    assert caught.value.details["reasonCode"] == "ARTIFACT_FEATURE_DISABLED"

    enabled = resolve_runtime_artifact_feature_flags(
        env={
            "IMPERAOS_ARTIFACT_WORKSPACE_ENABLED": "true",
            "IMPERAOS_ARTIFACT_DOCUMENT_EDITOR_ENABLED": "1",
        }
    )
    assert enabled["artifact_workspace.enabled"] is True
    assert enabled["artifact_workspace.document.enabled"] is True
    assert enabled["artifact_workspace.form.enabled"] is False


def test_runtime_capability_snapshot_reports_effective_rollout_without_environment() -> None:
    disabled = build_runtime_artifact_capability_snapshot(
        resolve_runtime_artifact_feature_flags(env={}),
        license_capabilities={"spreadsheet": False, "canvas": False},
    )
    assert disabled["contractVersion"] == "artifact-runtime-capability-snapshot/v1"
    assert disabled["rolloutStage"] == "disabled"
    assert disabled["globalEnabled"] is False
    assert disabled["enabledArtifactKinds"] == []
    assert set(disabled["features"]) == set(ARTIFACT_FEATURE_FLAG_NAMES)
    assert "environment" not in disabled
    assert "path" not in disabled

    enabled = build_runtime_artifact_capability_snapshot(
        resolve_runtime_artifact_feature_flags(
            env={
                "IMPERAOS_ARTIFACT_WORKSPACE_ENABLED": "true",
                "IMPERAOS_ARTIFACT_DOCUMENT_EDITOR_ENABLED": "true",
                "IMPERAOS_ARTIFACT_SPREADSHEET_EDITOR_ENABLED": "true",
            },
            license_capabilities={"spreadsheet": True, "canvas": False},
        ),
        license_capabilities={"spreadsheet": True, "canvas": False},
    )
    assert enabled["rolloutStage"] == "document"
    assert enabled["globalEnabled"] is True
    assert enabled["enabledArtifactKinds"] == ["document", "spreadsheet"]
    assert enabled["features"]["artifact_workspace.spreadsheet.enabled"] is True
    assert enabled["licenses"] == {"spreadsheet": True, "canvas": False}
    assert enabled["kindCapabilities"]["document"] == {
        "enabled": True,
        "editable": True,
        "exportable": False,
        "reasonCode": "ARTIFACT_EXPORT_FEATURE_DISABLED",
        "requiresLicense": False,
        "adapter": "built_in",
    }
    assert enabled["kindCapabilities"]["spreadsheet"] == {
        "enabled": True,
        "editable": True,
        "exportable": False,
        "reasonCode": "ARTIFACT_EXPORT_FEATURE_DISABLED",
        "requiresLicense": False,
        "adapter": "commercial",
    }
    assert enabled["kindCapabilities"]["canvas"] == {
        "enabled": False,
        "editable": False,
        "exportable": False,
        "reasonCode": "ARTIFACT_KIND_FEATURE_DISABLED",
        "requiresLicense": False,
        "adapter": "bundled_fallback",
    }


def test_forced_off_editor_flag_preserves_read_archive_and_safe_export_fallback(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    context = OperationContext(
        workspace_id="workspace-1",
        principal_type=PrincipalType.USER,
        principal_id="user-1",
        roles=("artifact_admin",),
        request_id="request-fallback",
    )
    created = ArtifactService(root).create(
        CreateArtifactCommand(
            artifact_id="spreadsheet-fallback",
            kind=ArtifactKind.SPREADSHEET,
            title="Fallback sheet",
            data_class=ArtifactDataClass.INTERNAL,
            content={
                "kind": "spreadsheet",
                "schemaVersion": 1,
                "calculationMode": "disabled",
                "sheets": [
                    {"id": "sheet-1", "name": "Sheet 1", "cells": {}, "columns": []}
                ],
            },
            idempotency_key="create-fallback",
        ),
        context,
    )
    ArtifactService(root).create(
        CreateArtifactCommand(
            artifact_id="canvas-fallback",
            kind=ArtifactKind.CANVAS,
            title="Fallback canvas",
            data_class=ArtifactDataClass.INTERNAL,
            content={
                "kind": "canvas",
                "schemaVersion": 1,
                "snapshot": {"store": {}},
                "assetIds": [],
                "embeds": "deny",
                "remoteAssets": "deny",
            },
            idempotency_key="create-canvas-fallback",
        ),
        context,
    )
    flags = {name: True for name in ARTIFACT_FEATURE_FLAG_NAMES}
    flags["artifact_workspace.spreadsheet.enabled"] = False
    flags["artifact_workspace.canvas.enabled"] = False
    fallback = ArtifactService(root, feature_flags=flags)

    assert fallback.get(GetArtifactQuery(artifact_id="spreadsheet-fallback"), context).artifact
    assert fallback.history(
        ArtifactHistoryQuery(artifact_id="spreadsheet-fallback"), context
    ).items
    assert [
        item.artifact_id
        for item in fallback.list(
            ListArtifactsQuery(kind=ArtifactKind.SPREADSHEET), context
        ).items
    ] == ["spreadsheet-fallback"]
    assert [
        item.artifact_id
        for item in fallback.list(
            ListArtifactsQuery(kind=ArtifactKind.CANVAS), context
        ).items
    ] == ["canvas-fallback"]
    export = fallback.begin_export(
        BeginArtifactExportCommand(
            artifact_id="spreadsheet-fallback",
            revision_id=created.revision.revision_id,
            format="xlsx",
            idempotency_key="export-fallback",
        ),
        context,
    )
    assert export.disposition == "created"
    archived = fallback.archive(
        ArchiveArtifactCommand(
            artifact_id="spreadsheet-fallback",
            expected_revision_number=1,
        ),
        context,
    )
    assert archived.artifact.status.value == "archived"
