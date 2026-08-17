from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

import typer

from imperaos.artifacts.commands import (
    ArtifactHistoryQuery,
    GetArtifactQuery,
    ListArtifactsQuery,
)
from imperaos.artifacts.diagnostics import (
    build_artifact_doctor_report,
    verify_artifact_integrity,
)
from imperaos.artifacts.evidence_import import FileArtifactEvidenceResolver
from imperaos.artifacts.licenses import ArtifactLicenseCapability, evaluate_artifact_license
from imperaos.artifacts.migrations import ArtifactMigrationReport, migrate_artifact_metadata
from imperaos.artifacts.models import ArtifactKind, OperationContext, PrincipalType
from imperaos.artifacts.rpc_protocol import (
    ARTIFACT_RPC_CONTRACT_VERSION,
    ARTIFACT_RPC_MAX_FRAME_BYTES,
)
from imperaos.artifacts.rpc_server import ArtifactRpcServer
from imperaos.artifacts.runtime import (
    resolve_artifact_approval_store,
    resolve_runtime_artifact_feature_flags,
)
from imperaos.artifacts.service import ArtifactService
from imperaos.runtime.paths import state_path

DEFAULT_ARTIFACT_ROOT = Path(state_path("artifacts"))
ARTIFACT_ROOT_OPTION = typer.Option(
    DEFAULT_ARTIFACT_ROOT,
    "--root",
    help="Artifact data root",
)
REPO_ROOT_OPTION = typer.Option(Path.cwd(), "--repo-root")
LICENSE_EVIDENCE_OPTION = typer.Option(None, "--evidence")
SPREADSHEET_LICENSE_EVIDENCE_OPTION = typer.Option(
    None, "--spreadsheet-license-evidence"
)
CANVAS_LICENSE_EVIDENCE_OPTION = typer.Option(None, "--canvas-license-evidence")
ARTIFACT_EVIDENCE_ROOT_OPTION = typer.Option(
    None,
    "--artifact-evidence-root",
    help="Workspace-scoped immutable evidence manifest root",
)

artifact_app = typer.Typer(help="Artifact workspace diagnostics")
artifact_integrity_app = typer.Typer(help="Artifact integrity diagnostics")
artifact_migration_app = typer.Typer(help="Artifact metadata migration commands")
artifact_license_app = typer.Typer(help="Licensed artifact editor diagnostics")
artifact_app.add_typer(artifact_integrity_app, name="integrity")
artifact_app.add_typer(artifact_migration_app, name="migration")
artifact_app.add_typer(artifact_license_app, name="license")


@artifact_license_app.command("doctor")
def artifact_license_doctor(
    kind: str = typer.Option(..., "--kind", help="spreadsheet or canvas"),
    profile: str = typer.Option("production", "--profile"),
    build_target: str = typer.Option("windows-x86_64", "--build-target"),
    evidence: Path | None = LICENSE_EVIDENCE_OPTION,
    repo_root: Path = REPO_ROOT_OPTION,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    del json_output
    if kind not in {"spreadsheet", "canvas"}:
        raise typer.BadParameter("--kind must be spreadsheet or canvas")
    if profile != "production":
        raise typer.BadParameter("only the production profile is supported")
    report = evaluate_artifact_license(
        kind,  # type: ignore[arg-type]
        repo_root=repo_root.resolve(),
        evidence_path=evidence.resolve() if evidence is not None else None,
        build_target=build_target,
    )
    _emit(report.model_dump(mode="json", by_alias=True))
    if not report.capability.enabled:
        raise typer.Exit(3)


def register_artifact_cli(root_app: typer.Typer) -> None:
    root_app.add_typer(artifact_app, name="artifact")
    root_app.command("workspace-rpc")(workspace_rpc)


@artifact_app.command("doctor")
def artifact_doctor(
    root: Path = ARTIFACT_ROOT_OPTION,
) -> None:
    service = ArtifactService(root)
    report = build_artifact_doctor_report(service)
    report.update(
        {
            "protocolVersion": ARTIFACT_RPC_CONTRACT_VERSION,
            "maxFrameBytes": ARTIFACT_RPC_MAX_FRAME_BYTES,
            "networkListener": False,
            "evidenceChainTable": True,
        }
    )
    _emit(report)
    if report["status"] != "ready":
        raise typer.Exit(1)


@artifact_app.command("list")
def artifact_list(
    workspace: str = typer.Option(..., "--workspace", help="Workspace identity"),
    root: Path = ARTIFACT_ROOT_OPTION,
    limit: int = typer.Option(50, "--limit", min=1, max=200),
) -> None:
    result = ArtifactService(root).list(
        ListArtifactsQuery(limit=limit),
        _diagnostic_context(workspace, "artifact-cli-list"),
    )
    _emit(
        {
            "count": len(result.items),
            "items": [item.model_dump(mode="json", by_alias=True) for item in result.items],
            "nextCursor": result.next_cursor,
        }
    )


@artifact_app.command("get")
def artifact_get(
    artifact_id: str = typer.Argument(..., help="Artifact identity"),
    workspace: str = typer.Option(..., "--workspace", help="Workspace identity"),
    root: Path = ARTIFACT_ROOT_OPTION,
    revision_id: str | None = typer.Option(None, "--revision", help="Optional revision identity"),
) -> None:
    result = ArtifactService(root).get(
        GetArtifactQuery(artifact_id=artifact_id, revision_id=revision_id),
        _diagnostic_context(workspace, "artifact-cli-get"),
    )
    _emit(
        {
            "artifact": result.artifact.model_dump(mode="json", by_alias=True),
            "revision": result.revision.model_dump(mode="json", by_alias=True),
            "content": result.content.model_dump(mode="json", by_alias=True),
        }
    )


@artifact_app.command("history")
def artifact_history(
    artifact_id: str = typer.Argument(..., help="Artifact identity"),
    workspace: str = typer.Option(..., "--workspace", help="Workspace identity"),
    root: Path = ARTIFACT_ROOT_OPTION,
    limit: int = typer.Option(100, "--limit", min=1, max=500),
) -> None:
    result = ArtifactService(root).history(
        ArtifactHistoryQuery(artifact_id=artifact_id, limit=limit),
        _diagnostic_context(workspace, "artifact-cli-history"),
    )
    _emit(
        {
            "items": [item.model_dump(mode="json", by_alias=True) for item in result.items],
            "nextCursor": result.next_cursor,
        }
    )


@artifact_integrity_app.command("verify")
def artifact_integrity_verify(
    workspace: str = typer.Option(..., "--workspace", help="Workspace identity"),
    root: Path = ARTIFACT_ROOT_OPTION,
) -> None:
    service = ArtifactService(root)
    report = verify_artifact_integrity(service, workspace_id=workspace)
    _emit(report)
    if report["status"] != "pass":
        raise typer.Exit(1)


@artifact_migration_app.command("plan")
def artifact_migration_plan(
    root: Path = ARTIFACT_ROOT_OPTION,
) -> None:
    report = migrate_artifact_metadata(
        root / "metadata" / "artifacts.sqlite3",
        dry_run=True,
    )
    _emit_migration(report)


@artifact_migration_app.command("apply")
def artifact_migration_apply(
    root: Path = ARTIFACT_ROOT_OPTION,
    dry_run: bool = typer.Option(False, "--dry-run", help="Report without writing"),
) -> None:
    report = migrate_artifact_metadata(
        root / "metadata" / "artifacts.sqlite3",
        dry_run=dry_run,
    )
    _emit_migration(report)


def workspace_rpc(
    stdio_json: bool = typer.Option(
        False,
        "--stdio-json",
        help="Serve length-prefixed JSON frames over stdin/stdout",
    ),
    root: Path = ARTIFACT_ROOT_OPTION,
    repo_root: Path = REPO_ROOT_OPTION,
    build_target: str = typer.Option("windows-x86_64", "--build-target"),
    spreadsheet_license_evidence: Path | None = SPREADSHEET_LICENSE_EVIDENCE_OPTION,
    canvas_license_evidence: Path | None = CANVAS_LICENSE_EVIDENCE_OPTION,
    artifact_evidence_root: Path | None = ARTIFACT_EVIDENCE_ROOT_OPTION,
    profile: str = typer.Option("enterprise", "--profile"),
) -> None:
    if not stdio_json:
        raise typer.BadParameter("--stdio-json is required")
    capabilities = _resolve_license_capabilities(
        repo_root=repo_root.resolve(),
        build_target=build_target,
        spreadsheet_evidence=spreadsheet_license_evidence,
        canvas_evidence=canvas_license_evidence,
    )
    feature_flags = resolve_runtime_artifact_feature_flags(
        license_capabilities={
            "spreadsheet": capabilities[ArtifactKind.SPREADSHEET].enabled,
            "canvas": capabilities[ArtifactKind.CANVAS].enabled,
        }
    )
    server = ArtifactRpcServer(
        ArtifactService(
            root,
            approval_store=resolve_artifact_approval_store(profile),
            license_capabilities=capabilities,
            fallback_editor_capabilities={
                ArtifactKind.SPREADSHEET: True,
                ArtifactKind.CANVAS: True,
            },
            feature_flags=feature_flags,
            evidence_resolver=FileArtifactEvidenceResolver(
                artifact_evidence_root or root / "evidence"
            ),
        )
    )
    exit_code = server.serve(sys.stdin.buffer, sys.stdout.buffer, sys.stderr.buffer)
    raise typer.Exit(exit_code)


def _resolve_license_capabilities(
    *,
    repo_root: Path,
    build_target: str,
    spreadsheet_evidence: Path | None,
    canvas_evidence: Path | None,
    environment: Mapping[str, str] | None = None,
) -> dict[ArtifactKind, ArtifactLicenseCapability]:
    resolved_environment = os.environ if environment is None else environment
    evidence_by_kind = {
        ArtifactKind.SPREADSHEET: spreadsheet_evidence,
        ArtifactKind.CANVAS: canvas_evidence,
    }
    return {
        kind: evaluate_artifact_license(
            kind.value,  # type: ignore[arg-type]
            repo_root=repo_root,
            evidence_path=evidence.resolve() if evidence is not None else None,
            build_target=build_target,
            environment=resolved_environment,
        ).capability
        for kind, evidence in evidence_by_kind.items()
    }


def _diagnostic_context(workspace: str, request_id: str) -> OperationContext:
    return OperationContext(
        workspace_id=workspace,
        principal_type=PrincipalType.SYSTEM,
        principal_id="artifact-cli",
        roles=("artifact_admin",),
        request_id=request_id,
    )


def _emit_migration(report: ArtifactMigrationReport) -> None:
    _emit(
        {
            "currentVersion": report.current_version,
            "targetVersion": report.target_version,
            "pendingVersions": list(report.pending_versions),
            "appliedVersions": list(report.applied_versions),
            "databaseExists": report.database_exists,
            "databaseSizeBytes": report.database_size_bytes,
            "freeSpaceBytes": report.free_space_bytes,
            "storageFileCount": report.storage_file_count,
            "tableRowCounts": report.table_row_counts,
        }
    )


def _emit(payload: dict[str, object]) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
