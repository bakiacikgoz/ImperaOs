from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from imperaos.artifacts.migrations import migrate_artifact_metadata
from imperaos.artifacts.service import ArtifactService


def verify_artifact_integrity(
    service: ArtifactService,
    *,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    where = "WHERE a.workspace_id = ?" if workspace_id is not None else ""
    parameters: tuple[str, ...] = (workspace_id,) if workspace_id is not None else ()
    with service.store._connect() as connection:
        sqlite_row = connection.execute("PRAGMA integrity_check").fetchone()
        sqlite_integrity = str(sqlite_row[0]) if sqlite_row else "missing"
        artifacts = connection.execute(
            f"SELECT a.artifact_id FROM artifacts a {where}", parameters
        ).fetchall()
        revisions = connection.execute(
            f"""
            SELECT r.content_relpath, r.content_sha256, r.content_size_bytes
            FROM artifact_revisions r JOIN artifacts a ON a.artifact_id = r.artifact_id
            {where}
            """,
            parameters,
        ).fetchall()
        asset_where = "WHERE workspace_id = ?" if workspace_id is not None else ""
        assets = connection.execute(
            f"SELECT relative_path, sha256, size_bytes FROM artifact_assets {asset_where}",
            parameters,
        ).fetchall()
        workspace_rows = connection.execute(
            f"SELECT DISTINCT a.workspace_id FROM artifacts a {where}", parameters
        ).fetchall()
        pending_journals = int(
            connection.execute(
                "SELECT COUNT(*) FROM artifact_write_journal WHERE state = 'pending'"
            ).fetchone()[0]
        )

    revision_missing, revision_mismatch, verified_revisions = _verify_files(
        service, revisions, "content_relpath", "content_sha256", "content_size_bytes"
    )
    asset_missing, asset_mismatch, verified_assets = _verify_files(
        service, assets, "relative_path", "sha256", "size_bytes"
    )
    known_content = {str(row["content_relpath"]) for row in revisions}
    known_assets = {str(row["relative_path"]) for row in assets}
    orphan_content = _orphan_count(service.store.filesystem.content_root, service, known_content)
    orphan_assets = _orphan_count(service.store.filesystem.assets_root, service, known_assets)
    evidence_failures = sum(
        not service.evidence.verify_chain(str(row["workspace_id"])) for row in workspace_rows
    )
    tmp_count = _file_count(service.store.filesystem.tmp_root)
    quarantine_count = _file_count(service.store.filesystem.quarantine_root)
    failures = sum(
        (
            sqlite_integrity.lower() != "ok",
            revision_missing > 0,
            revision_mismatch > 0,
            asset_missing > 0,
            asset_mismatch > 0,
            orphan_content > 0,
            orphan_assets > 0,
            evidence_failures > 0,
            pending_journals > 0,
            tmp_count > 0,
        )
    )
    if failures:
        service.operations.add("imperaos_artifact_storage_integrity_failure_total")
    return {
        "status": "pass" if failures == 0 else "fail",
        "workspaceRef": _workspace_ref(workspace_id),
        "sqliteIntegrity": sqlite_integrity,
        "artifactCount": len(artifacts),
        "revisionCount": len(revisions),
        "verifiedRevisionCount": verified_revisions,
        "revisionMissingFileCount": revision_missing,
        "revisionHashMismatchCount": revision_mismatch,
        "assetCount": len(assets),
        "verifiedAssetCount": verified_assets,
        "assetMissingFileCount": asset_missing,
        "assetHashMismatchCount": asset_mismatch,
        "orphanContentFileCount": orphan_content,
        "orphanAssetFileCount": orphan_assets,
        "evidenceChainFailureCount": evidence_failures,
        "pendingJournalCount": pending_journals,
        "temporaryFileCount": tmp_count,
        "quarantineFileCount": quarantine_count,
        "databaseSizeBytes": service.store.database_path.stat().st_size,
        "storageSizeBytes": _tree_size(service.store.filesystem.root),
    }


def build_artifact_doctor_report(service: ArtifactService) -> dict[str, Any]:
    migration = migrate_artifact_metadata(service.store.database_path, dry_run=True)
    integrity = verify_artifact_integrity(service)
    licenses = [
        capability.model_dump(mode="json", by_alias=True)
        for capability in service.license_capabilities()
    ]
    ready = not migration.pending_versions and integrity["status"] == "pass"
    return {
        "status": "ready" if ready else "blocked",
        "schemaVersion": migration.current_version,
        "targetSchemaVersion": migration.target_version,
        "pendingMigrations": list(migration.pending_versions),
        "integrity": integrity,
        "licenses": licenses,
        "metrics": service.operations.snapshot(),
        "metricSeries": service.operations.series_snapshot(),
        "recentOperationLogs": list(service.operation_logs),
    }


def build_artifact_support_snapshot(service: ArtifactService) -> dict[str, Any]:
    doctor = build_artifact_doctor_report(service)
    integrity = doctor["integrity"]
    return {
        "schemaVersion": "artifact-support/v1",
        "status": "ready" if doctor["status"] == "ready" else "blocked",
        "database": {
            "schemaVersion": doctor["schemaVersion"],
            "integrity": integrity["sqliteIntegrity"],
            "sizeBytes": integrity["databaseSizeBytes"],
        },
        "counts": {
            key: integrity[key]
            for key in (
                "artifactCount",
                "revisionCount",
                "assetCount",
                "orphanContentFileCount",
                "orphanAssetFileCount",
                "quarantineFileCount",
                "pendingJournalCount",
                "evidenceChainFailureCount",
            )
        },
        "storageSizeBytes": integrity["storageSizeBytes"],
        "integrityStatus": integrity["status"],
        "licenses": doctor["licenses"],
        "metrics": doctor["metrics"],
        "reasonCode": (
            "ARTIFACT_SUPPORT_READY"
            if doctor["status"] == "ready"
            else "ARTIFACT_INTEGRITY_CHECK_FAILED"
        ),
    }


def _verify_files(
    service: ArtifactService,
    rows: list[Any],
    path_key: str,
    hash_key: str,
    size_key: str,
) -> tuple[int, int, int]:
    missing = mismatch = verified = 0
    for row in rows:
        path = service.store.filesystem.resolve_relative(str(row[path_key]))
        if not path.is_file():
            missing += 1
            continue
        payload = path.read_bytes()
        if (
            len(payload) != int(row[size_key])
            or hashlib.sha256(payload).hexdigest() != row[hash_key]
        ):
            mismatch += 1
        else:
            verified += 1
    return missing, mismatch, verified


def _orphan_count(root: Path, service: ArtifactService, known: set[str]) -> int:
    return sum(
        candidate.relative_to(service.store.filesystem.root).as_posix() not in known
        for candidate in root.rglob("*")
        if candidate.is_file()
    )


def _file_count(root: Path) -> int:
    return sum(candidate.is_file() for candidate in root.rglob("*"))


def _tree_size(root: Path) -> int:
    return sum(candidate.stat().st_size for candidate in root.rglob("*") if candidate.is_file())


def _workspace_ref(workspace_id: str | None) -> str:
    if workspace_id is None:
        return "all"
    return hashlib.sha256(workspace_id.encode("utf-8")).hexdigest()
