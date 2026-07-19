from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from imperaos.artifacts.cli import _resolve_license_capabilities
from imperaos.artifacts.commands import (
    CreateArtifactCommand,
    DuplicateArtifactCommand,
    GetArtifactQuery,
    MutateArtifactCommand,
    PatchSpreadsheetCellsCommand,
    RestoreArtifactCommand,
)
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.licenses import ArtifactLicenseCapability, evaluate_artifact_license
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    ArtifactMutationType,
    OperationContext,
    PrincipalType,
)
from imperaos.artifacts.service import ArtifactService


def _signed_evidence(secret: str, **updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schemaVersion": "artifact-license-entitlement/v1",
        "evidenceId": "license-proof-1",
        "product": "handsontable",
        "licenseMode": "commercial-production",
        "packageVersions": {
            "handsontable": "18.0.0",
            "@handsontable/react-wrapper": "18.0.0",
        },
        "buildTargets": ["windows-x86_64"],
        "offlinePermitted": True,
        "notBeforeUtc": "2026-01-01T00:00:00Z",
        "expiresAtUtc": "2027-01-01T00:00:00Z",
        "activationMechanism": "offline-secret-reference",
        "activationVerified": True,
        "secretRef": "IMPERAOS_LICENSE_TEST_KEY",
        "approvedBy": "security-owner",
    }
    payload.update(updates)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["signature"] = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
    return payload


def _enabled(kind: str = "spreadsheet") -> ArtifactLicenseCapability:
    return ArtifactLicenseCapability(
        kind=kind, enabled=True, reason_code="ARTIFACT_LICENSE_ENABLED"
    )


def test_license_doctor_is_redacted_and_forced_off_without_evidence(tmp_path: Path) -> None:
    report = evaluate_artifact_license(
        "spreadsheet", repo_root=tmp_path, evidence_path=None,
        build_target="windows-x86_64", environment={},
    )
    dumped = report.model_dump(mode="json", by_alias=True)
    assert dumped["capability"] == {
        "contractVersion": "artifact-license-capability/v1",
        "kind": "spreadsheet",
        "enabled": False,
        "reasonCode": "ARTIFACT_LICENSE_EVIDENCE_MISSING",
    }
    serialized = json.dumps(dumped)
    assert "secretRef" not in serialized
    assert "signature" not in serialized
    with pytest.raises(ValueError):
        ArtifactLicenseCapability(
            kind="spreadsheet", enabled=True,
            reason_code="ARTIFACT_LICENSE_EVIDENCE_MISSING",
        )


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"offlinePermitted": False}, "ARTIFACT_LICENSE_OFFLINE_UNVERIFIED"),
        ({"buildTargets": ["macos-aarch64"]}, "ARTIFACT_LICENSE_TARGET_MISMATCH"),
        ({"packageVersions": {"handsontable": "17.0.0"}}, "ARTIFACT_LICENSE_VERSION_MISMATCH"),
        ({"expiresAtUtc": "2026-02-01T00:00:00Z"}, "ARTIFACT_LICENSE_EXPIRED"),
    ],
)
def test_license_doctor_rejects_unqualified_evidence(
    tmp_path: Path, updates: dict[str, object], reason: str
) -> None:
    secret = "test-secret-not-a-license"
    evidence = tmp_path / "entitlement.json"
    evidence.write_text(json.dumps(_signed_evidence(secret, **updates)), encoding="utf-8")
    report = evaluate_artifact_license(
        "spreadsheet", repo_root=tmp_path, evidence_path=evidence,
        build_target="windows-x86_64", environment={"IMPERAOS_LICENSE_TEST_KEY": secret},
        now=datetime(2026, 7, 16, tzinfo=UTC),
    )
    assert report.capability.enabled is False
    assert report.capability.reason_code == reason


def test_valid_signed_evidence_still_fails_closed_when_exact_packages_are_absent(
    tmp_path: Path,
) -> None:
    secret = "test-secret-not-a-license"
    evidence = tmp_path / "entitlement.json"
    evidence.write_text(json.dumps(_signed_evidence(secret)), encoding="utf-8")
    report = evaluate_artifact_license(
        "spreadsheet", repo_root=tmp_path, evidence_path=evidence,
        build_target="windows-x86_64", environment={"IMPERAOS_LICENSE_TEST_KEY": secret},
        now=datetime(2026, 7, 16, tzinfo=UTC),
    )
    assert report.capability.enabled is False
    assert report.capability.reason_code == "ARTIFACT_LICENSE_PACKAGE_MISSING"


def test_license_doctor_rejects_naive_timestamps_and_does_not_fall_back_from_empty_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "process-secret-must-not-be-used"
    monkeypatch.setenv("IMPERAOS_LICENSE_TEST_KEY", secret)
    evidence = tmp_path / "entitlement.json"
    evidence.write_text(
        json.dumps(_signed_evidence(secret, notBeforeUtc="2026-01-01T00:00:00")),
        encoding="utf-8",
    )
    naive = evaluate_artifact_license(
        "spreadsheet", repo_root=tmp_path, evidence_path=evidence,
        build_target="windows-x86_64", environment={},
    )
    assert naive.capability.reason_code == "ARTIFACT_LICENSE_EVIDENCE_INVALID"

    evidence.write_text(json.dumps(_signed_evidence(secret)), encoding="utf-8")
    empty_environment = evaluate_artifact_license(
        "spreadsheet", repo_root=tmp_path, evidence_path=evidence,
        build_target="windows-x86_64", environment={},
        now=datetime(2026, 7, 16, tzinfo=UTC),
    )
    assert empty_environment.capability.reason_code == "ARTIFACT_LICENSE_EVIDENCE_INVALID"


def test_workspace_rpc_capabilities_are_derived_from_the_same_doctor_contract(
    tmp_path: Path,
) -> None:
    secret = "test-secret-not-a-license"
    package_root = tmp_path / "apps" / "operator-panel"
    package_root.mkdir(parents=True)
    (package_root / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {
                    "handsontable": "18.0.0",
                    "@handsontable/react-wrapper": "18.0.0",
                }
            }
        ),
        encoding="utf-8",
    )
    evidence = tmp_path / "entitlement.json"
    evidence.write_text(json.dumps(_signed_evidence(secret)), encoding="utf-8")

    capabilities = _resolve_license_capabilities(
        repo_root=tmp_path,
        build_target="windows-x86_64",
        spreadsheet_evidence=evidence,
        canvas_evidence=None,
        environment={"IMPERAOS_LICENSE_TEST_KEY": secret},
    )

    assert capabilities[ArtifactKind.SPREADSHEET] == _enabled()
    assert capabilities[ArtifactKind.CANVAS].enabled is False
    service = ArtifactService(tmp_path / "artifacts", license_capabilities=capabilities)
    assert service.license_capabilities() == tuple(capabilities.values())


def test_forced_off_capability_denies_spreadsheet_mutation_without_a_revision(
    tmp_path: Path,
) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    context = OperationContext(
        workspace_id="workspace-1", principal_type=PrincipalType.USER,
        principal_id="user-1", roles=("artifact_admin",), request_id="request-license",
    )
    content = {
        "kind": "spreadsheet", "schemaVersion": 1, "calculationMode": "disabled",
        "sheets": [{"id": "sheet-1", "name": "Sheet 1", "cells": {}, "columns": []}],
    }
    created = service.create(
        CreateArtifactCommand(
            artifact_id="sheet-artifact", kind=ArtifactKind.SPREADSHEET, title="Budget",
            data_class=ArtifactDataClass.INTERNAL, content=content,
            idempotency_key="create-sheet",
        ),
        context,
    )
    with pytest.raises(ArtifactDomainError) as denied:
        service.mutate(
            MutateArtifactCommand(
                artifact_id=created.artifact.artifact_id,
                expected_revision_number=1,
                mutation_type=ArtifactMutationType.REPLACE_CONTENT,
                content=content,
                idempotency_key="mutate-sheet",
                change_summary="Denied edit",
            ),
            context,
        )
    assert denied.value.code is ArtifactErrorCode.ARTIFACT_LICENSE_UNAVAILABLE
    assert len(service.store.list_revisions("workspace-1", "sheet-artifact")) == 1


def test_bundled_fallback_capability_allows_spreadsheet_mutation_without_license(
    tmp_path: Path,
) -> None:
    service = ArtifactService(
        tmp_path / "artifacts",
        fallback_editor_capabilities={ArtifactKind.SPREADSHEET: True},
    )
    context = OperationContext(
        workspace_id="workspace-1", principal_type=PrincipalType.USER,
        principal_id="user-1", roles=("artifact_admin",), request_id="request-fallback",
    )
    content = {
        "kind": "spreadsheet", "schemaVersion": 2, "calculationMode": "disabled",
        "sheets": [{"id": "sheet-1", "name": "Sheet 1", "cells": {}, "columns": []}],
    }
    created = service.create(
        CreateArtifactCommand(
            artifact_id="sheet-fallback", kind=ArtifactKind.SPREADSHEET, title="Budget",
            data_class=ArtifactDataClass.INTERNAL, content=content,
            idempotency_key="create-fallback",
        ),
        context,
    )
    updated = service.mutate(
        MutateArtifactCommand(
            artifact_id=created.artifact.artifact_id,
            expected_revision_number=1,
            mutation_type=ArtifactMutationType.REPLACE_CONTENT,
            content={
                **content,
                "sheets": [{
                    "id": "sheet-1", "name": "Sheet 1",
                    "cells": {"A1": {"value": "fallback"}}, "columns": [],
                }],
            },
            idempotency_key="mutate-fallback",
            change_summary="Fallback edit",
        ),
        context,
    )
    assert updated.revision.revision_number == 2


def test_enabled_cell_patch_is_atomic_bounded_and_preserves_other_cells(tmp_path: Path) -> None:
    service = ArtifactService(
        tmp_path / "artifacts",
        license_capabilities={ArtifactKind.SPREADSHEET: _enabled()},
    )
    context = OperationContext(
        workspace_id="workspace-1", principal_type=PrincipalType.USER,
        principal_id="user-1", roles=("artifact_admin",), request_id="request-patch",
    )
    created = service.create(
        CreateArtifactCommand(
            artifact_id="sheet-v2", kind=ArtifactKind.SPREADSHEET, title="Budget",
            data_class=ArtifactDataClass.INTERNAL,
            content={
                "kind": "spreadsheet", "schemaVersion": 2, "calculationMode": "disabled",
                "sheets": [{
                    "id": "sheet-1", "name": "Sheet 1",
                    "cells": {"A1": {"value": "keep"}, "B1": {"value": 10}}, "columns": [],
                }],
            },
            idempotency_key="create-sheet-v2",
        ),
        context,
    )
    patched = service.patch_spreadsheet_cells(
        PatchSpreadsheetCellsCommand(
            artifact_id=created.artifact.artifact_id, expected_revision_number=1,
            sheet_id="sheet-1",
            operations=[
                {"op": "set", "address": "C1", "value": True},
                {"op": "clear", "address": "B1"},
            ],
            idempotency_key="patch-sheet-v2", change_summary="Patch cells",
        ),
        context,
    )
    mutation_series = [
        item
        for item in service.operations.series_snapshot()
        if item["name"] == "imperaos_artifact_mutation_total"
        and item["labels"]
        == {"kind": "spreadsheet", "actor": "user", "result": "success"}
    ]
    assert mutation_series == [
        {
            "name": "imperaos_artifact_mutation_total",
            "labels": {"kind": "spreadsheet", "actor": "user", "result": "success"},
            "value": 1,
        }
    ]
    loaded = service.get(
        GetArtifactQuery(artifact_id=created.artifact.artifact_id), context
    )
    cells = loaded.content.model_dump(mode="json", by_alias=True)["sheets"][0]["cells"]
    assert cells == {"A1": {"value": "keep"}, "C1": {"value": True}}
    assert patched.revision.mutation_type is ArtifactMutationType.CELL_PATCH
    assert patched.revision.revision_number == 2

    second = service.patch_spreadsheet_cells(
        PatchSpreadsheetCellsCommand(
            artifact_id=created.artifact.artifact_id, expected_revision_number=2,
            sheet_id="sheet-1", operations=[{"op": "set", "address": "D1", "value": 2}],
            idempotency_key="patch-sheet-v2-second", change_summary="Second patch",
        ),
        context,
    )
    replay = service.patch_spreadsheet_cells(
        PatchSpreadsheetCellsCommand(
            artifact_id=created.artifact.artifact_id, expected_revision_number=1,
            sheet_id="sheet-1",
            operations=[
                {"op": "set", "address": "C1", "value": True},
                {"op": "clear", "address": "B1"},
            ],
            idempotency_key="patch-sheet-v2", change_summary="Patch cells",
        ),
        context,
    )
    assert second.revision.revision_number == 3
    assert replay.revision.revision_id == patched.revision.revision_id
    assert replay.disposition == "idempotent_replay"
    assert len(service.store.list_revisions("workspace-1", "sheet-v2")) == 3


def test_forced_off_capability_blocks_restore_and_duplicate_without_writes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    context = OperationContext(
        workspace_id="workspace-1", principal_type=PrincipalType.USER,
        principal_id="user-1", roles=("artifact_admin",), request_id="request-bypasses",
    )
    enabled = ArtifactService(
        root, license_capabilities={ArtifactKind.SPREADSHEET: _enabled()}
    )
    created = enabled.create(
        CreateArtifactCommand(
            artifact_id="sheet-guarded", kind=ArtifactKind.SPREADSHEET, title="Guarded",
            data_class=ArtifactDataClass.INTERNAL,
            content={
                "kind": "spreadsheet", "schemaVersion": 2,
                "calculationMode": "disabled",
                "sheets": [{
                    "id": "sheet-1", "name": "Sheet 1",
                    "cells": {"A1": {"value": 1}}, "columns": [],
                }],
            },
            idempotency_key="create-guarded",
        ),
        context,
    )
    changed = enabled.patch_spreadsheet_cells(
        PatchSpreadsheetCellsCommand(
            artifact_id=created.artifact.artifact_id, expected_revision_number=1,
            sheet_id="sheet-1", operations=[{"op": "set", "address": "A1", "value": 2}],
            idempotency_key="patch-guarded", change_summary="Changed",
        ),
        context,
    )
    forced_off = ArtifactService(root)

    with pytest.raises(ArtifactDomainError) as restore_denied:
        forced_off.restore(
            RestoreArtifactCommand(
                artifact_id="sheet-guarded", source_revision_id=created.revision.revision_id,
                expected_revision_number=2, idempotency_key="restore-denied",
                change_summary="Must not restore",
            ),
            context,
        )
    with pytest.raises(ArtifactDomainError) as duplicate_denied:
        forced_off.duplicate(
            DuplicateArtifactCommand(
                source_artifact_id="sheet-guarded",
                source_revision_id=changed.revision.revision_id,
                artifact_id="sheet-copy-denied", title="Denied copy",
                idempotency_key="duplicate-denied",
            ),
            context,
        )

    assert restore_denied.value.code is ArtifactErrorCode.ARTIFACT_LICENSE_UNAVAILABLE
    assert duplicate_denied.value.code is ArtifactErrorCode.ARTIFACT_LICENSE_UNAVAILABLE
    assert len(forced_off.store.list_revisions("workspace-1", "sheet-guarded")) == 2
    with pytest.raises(ArtifactDomainError) as missing_copy:
        forced_off.store.get_artifact("workspace-1", "sheet-copy-denied")
    assert missing_copy.value.code is ArtifactErrorCode.ARTIFACT_NOT_FOUND
