from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.artifacts.diagnostics import build_artifact_support_snapshot
from imperaos.artifacts.service import ArtifactService
from imperaos.enterprise.baseline import security_posture
from imperaos.enterprise.observability import collect_metrics_snapshot
from imperaos.enterprise.qualification import (
    MIN_GREEN_SOAK_SECONDS,
    evaluate_qualification_evidence,
)
from imperaos.enterprise.signing import load_signed_artifact, write_signed_json
from imperaos.governance.approval_store import ApprovalStore
from imperaos.memory.persistent_store import PersistentMemoryStore
from imperaos.runtime.config import RuntimeConfig, redact_config_payload
from imperaos.runtime.paths import state_path
from imperaos.team.checkpoint_store import TeamCheckpointStore


def migration_plan(config: RuntimeConfig) -> dict[str, Any]:
    stores = _store_versions(config, initialize=False)
    return {
        "generated_at": _now_iso(),
        "profile": config.profile_name,
        "compatible_upgrade_path": "N->N+1 only",
        "reverse_migration_supported": False,
        "stores": stores,
        "actions": [
            "validate profile and manifests",
            "enter maintenance mode",
            "backup create and verify",
            "initialize or migrate sqlite stores",
            "verify replay/config/key manifests",
        ],
    }


def migration_apply(config: RuntimeConfig, *, dry_run: bool = True) -> dict[str, Any]:
    plan = migration_plan(config)
    if dry_run:
        plan["status"] = "dry_run"
        return plan
    _store_versions(config, initialize=True)
    manifest_dir = Path(config.maintenance.migration_dir)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        **plan,
        "status": "applied",
        "applied_at": _now_iso(),
    }
    target = manifest_dir / f"migration-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.json"
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest["manifest_path"] = str(target)
    return manifest


def create_backup(config: RuntimeConfig, *, output_dir: str | Path | None = None) -> dict[str, Any]:
    destination = Path(
        output_dir
        or Path(config.maintenance.backup_dir)
        / datetime.now(UTC).strftime("backup-%Y%m%d%H%M%S")
    )
    destination.mkdir(parents=True, exist_ok=True)

    files = _backup_targets(config)
    copied: list[dict[str, Any]] = []
    for label, source in files.items():
        src = Path(source)
        if not src.exists():
            continue
        target = destination / label
        if src.is_dir():
            shutil.copytree(src, target, dirs_exist_ok=True)
            digest = _dir_hash(target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            digest = _file_hash(target)
        copied.append({"label": label, "source": str(src), "target": str(target), "sha256": digest})

    verification = restore_verify(config, backup_dir=destination)
    manifest = {
        "generated_at": _now_iso(),
        "profile": config.profile_name,
        "backup_dir": str(destination),
        "items": copied,
        "verified": verification["verified"],
        "verification": verification,
    }
    manifest_path = destination / "manifest.json"
    write_signed_json(
        path=manifest_path,
        artifact="backup_manifest",
        data=manifest,
        config=config,
        purpose="backup-manifest",
    )
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def restore_verify(config: RuntimeConfig, *, backup_dir: str | Path) -> dict[str, Any]:
    root = Path(backup_dir)
    checks: dict[str, Any] = {}
    errors: list[str] = []
    for name in ("memory_db", "approval_store", "checkpoint_store"):
        db_path = root / name
        if not db_path.exists():
            checks[name] = {"status": "missing"}
            continue
        try:
            with sqlite3.connect(db_path) as conn:
                result = conn.execute("PRAGMA integrity_check").fetchone()
            ok = bool(result and str(result[0]).lower() == "ok")
            checks[name] = {
                "status": "pass" if ok else "fail",
                "detail": result[0] if result else None,
            }
            if not ok:
                errors.append(f"{name} integrity_check failed")
        except Exception as exc:  # noqa: BLE001
            checks[name] = {"status": "fail", "detail": str(exc)}
            errors.append(f"{name}: {exc}")
    return {
        "backup_dir": str(root),
        "verified": not errors,
        "checks": checks,
        "errors": errors,
    }


def export_support_bundle(
    config: RuntimeConfig,
    *,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(config.maintenance.support_bundle_dir)
    bundle_dir = root / datetime.now(UTC).strftime("support-%Y%m%d%H%M%S")
    bundle_dir.mkdir(parents=True, exist_ok=True)

    bundle_files: list[str] = []
    metrics = collect_metrics_snapshot(config)
    metrics_path = bundle_dir / "metrics_snapshot.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    bundle_files.append(str(metrics_path))

    config_payload = {
        "resolved": redact_config_payload(config.model_dump(mode="python")),
    }
    config_path = bundle_dir / "config_resolved.json"
    config_path.write_text(
        json.dumps(config_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    bundle_files.append(str(config_path))

    artifact_root = Path(state_path("artifacts"))
    artifact_snapshot = build_artifact_support_snapshot(ArtifactService(artifact_root))
    artifact_snapshot_path = bundle_dir / "artifact_workspace_snapshot.json"
    artifact_snapshot_path.write_text(
        json.dumps(artifact_snapshot, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    bundle_files.append(str(artifact_snapshot_path))

    for src in [
        Path("artifacts") / "status.json",
        Path("artifacts") / "team_pilot_report.json",
        Path("artifacts") / "qualification_report.json",
        Path("artifacts") / "ga_readiness_report.json",
    ]:
        if src.exists():
            target = bundle_dir / src.name
            shutil.copy2(src, target)
            bundle_files.append(str(target))

    posture = security_posture(config)
    posture_path = bundle_dir / "security_posture.json"
    posture_path.write_text(json.dumps(posture, indent=2, ensure_ascii=False), encoding="utf-8")
    bundle_files.append(str(posture_path))

    manifest = {
        "generated_at": _now_iso(),
        "profile": config.profile_name,
        "bundle_dir": str(bundle_dir),
        "files": [
            {"path": item, "sha256": _file_hash(Path(item))}
            for item in bundle_files
            if Path(item).is_file()
        ],
    }
    manifest_path = bundle_dir / "support_bundle_manifest.json"
    write_signed_json(
        path=manifest_path,
        artifact="support_bundle_manifest",
        data=manifest,
        config=config,
        purpose="support-bundle",
    )
    archive_path = Path(output_path) if output_path else bundle_dir.with_suffix(".zip")
    shutil.make_archive(str(archive_path.with_suffix("")), "zip", root_dir=bundle_dir)
    return {
        "bundle_dir": str(bundle_dir),
        "archive_path": str(archive_path),
        "manifest_path": str(manifest_path),
        "file_count": len(bundle_files),
    }


def ga_readiness_report(
    config: RuntimeConfig,
    *,
    qualification_report_path: str | Path = "artifacts/qualification_report.json",
) -> dict[str, Any]:
    posture = security_posture(config)
    metrics = collect_metrics_snapshot(config)
    migration = migration_plan(config)
    qualification_artifact = Path(qualification_report_path)
    qualification_bundle = load_signed_artifact(path=qualification_artifact, config=config)
    qualification_payload = qualification_bundle.get("data")
    qualification_evaluation: dict[str, Any] | None = None
    qualification_status = None
    qualification_recommended = None
    if qualification_bundle.get("present") and qualification_bundle.get("verified"):
        if isinstance(qualification_payload, dict):
            qualification_evaluation = evaluate_qualification_evidence(
                qualification_payload=qualification_payload
            )
            qualification_status = str(
                qualification_payload.get("qualification_status")
                or qualification_evaluation.get("qualification_status")
                or "unknown"
            )
            qualification_recommended = str(
                qualification_payload.get("recommended_status")
                or qualification_evaluation.get("recommended_status")
                or "unknown"
            )
        else:
            qualification_status = "invalid"
            qualification_recommended = "red"
    elif qualification_bundle.get("present"):
        qualification_status = "invalid"
        qualification_recommended = "red"
    docs = {
        "SECURITY_BASELINE.md": Path("SECURITY_BASELINE.md").exists(),
        "KEY_MANAGEMENT.md": Path("KEY_MANAGEMENT.md").exists(),
        "UPGRADE_AND_RECOVERY.md": Path("UPGRADE_AND_RECOVERY.md").exists(),
        "OBSERVABILITY_AND_SLO.md": Path("OBSERVABILITY_AND_SLO.md").exists(),
        "QUALIFICATION_MATRIX.md": Path("QUALIFICATION_MATRIX.md").exists(),
        "INSTALL.md": Path("INSTALL.md").exists(),
        "DEPLOYMENT_GUIDE.md": Path("DEPLOYMENT_GUIDE.md").exists(),
        "SUPPORT_BUNDLE.md": Path("SUPPORT_BUNDLE.md").exists(),
    }
    sections = {
        "security_baseline": _section_status(
            posture["overall_status"] == "pass" and docs["SECURITY_BASELINE.md"]
        ),
        "identity_rbac": _section_status(
            config.identity.enabled
            and config.identity.required_for_mutations
            and bool(config.identity.permission_model_version),
        ),
        "key_signing": _section_status(
            config.keys.provider in {"local_file", "managed_kms"}
            and metrics["audit"]["audit_file_count"] >= 0
            and docs["KEY_MANAGEMENT.md"]
        ),
        "upgrade_backup_rollback": _section_status(
            docs["UPGRADE_AND_RECOVERY.md"]
            and bool(config.maintenance.backup_dir)
            and bool(migration.get("stores")),
        ),
        "observability_slo": _section_status(
            docs["OBSERVABILITY_AND_SLO.md"] and bool(config.observability.file_snapshot_enabled),
        ),
        "qualification_soak": _section_status(
            docs["QUALIFICATION_MATRIX.md"] and qualification_recommended == "green",
            fallback="yellow",
        ),
        "packaging_installability": _section_status(
            docs["INSTALL.md"] and docs["DEPLOYMENT_GUIDE.md"] and docs["SUPPORT_BUNDLE.md"],
            fallback="yellow",
        ),
    }
    residual_risks = [
        "multi-tenant control plane deferred",
        "richer admin UI deferred",
        "full PKCS#11/HSM breadth deferred",
        "broad cloud-native integrations deferred",
    ]
    blocking_findings = []
    pending_evidence = []
    if posture["overall_status"] != "pass":
        blocking_findings.extend(posture.get("errors", []))
    if sections["identity_rbac"] == "red":
        blocking_findings.append("identity/RBAC enforcement is not active")
    if sections["key_signing"] == "red":
        blocking_findings.append("enterprise asymmetric signing is not active")
    if sections["upgrade_backup_rollback"] == "red":
        blocking_findings.append("upgrade/backup/rollback contract is incomplete")
    if sections["observability_slo"] == "red":
        blocking_findings.append("observability/SLO baseline is incomplete")
    if qualification_bundle.get("present") and not qualification_bundle.get("verified"):
        blocking_findings.append(
            f"qualification report signature invalid: {qualification_bundle.get('error_code')}"
        )
    if qualification_status == "invalid":
        blocking_findings.append("qualification report payload is invalid")
    if qualification_evaluation and qualification_evaluation.get("recommended_status") == "red":
        blocking_findings.extend(
            str(item) for item in qualification_evaluation.get("blocking_findings", [])
        )
    if sections["qualification_soak"] != "green":
        pending_evidence.append("qualification/soak evidence is not yet published")
    if sections["packaging_installability"] != "green":
        pending_evidence.append("install/deployment/support bundle docs are incomplete")
    if (
        qualification_bundle.get("present")
        and qualification_evaluation is None
        and qualification_status != "invalid"
    ):
        pending_evidence.append("qualification evidence could not be evaluated")

    overall = "green" if all(value == "green" for value in sections.values()) else "yellow"
    if blocking_findings:
        overall = "red"
    return {
        "generated_at": _now_iso(),
        "profile": config.profile_name,
        "overall_status": overall,
        "sections": sections,
        "security_posture": posture,
        "migration": migration,
        "metrics": metrics,
        "docs": docs,
        "qualification_report": {
            "path": str(qualification_artifact),
            "present": bool(qualification_bundle.get("present")),
            "verified": bool(qualification_bundle.get("verified")),
            "status": qualification_status,
            "recommended_status": qualification_recommended,
            "minimum_green_soak_seconds": MIN_GREEN_SOAK_SECONDS,
            "error_code": qualification_bundle.get("error_code"),
            "supported_profiles": (
                qualification_evaluation.get("supported_profiles", [])
                if qualification_evaluation is not None
                else []
            ),
            "conditional_profiles": (
                qualification_evaluation.get("conditional_profiles", [])
                if qualification_evaluation is not None
                else []
            ),
            "unsupported_profiles": (
                qualification_evaluation.get("unsupported_profiles", [])
                if qualification_evaluation is not None
                else []
            ),
        },
        "blocking_findings": blocking_findings,
        "pending_evidence": pending_evidence,
        "residual_risks": residual_risks,
        "deferred_scope": residual_risks,
        "go_no_go": (
            "go"
            if overall == "green"
            else ("conditional" if overall == "yellow" else "no-go")
        ),
    }


def render_ga_readiness_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# GA Readiness Report",
        "",
        f"- Generated at: `{payload.get('generated_at')}`",
        f"- Profile: `{payload.get('profile')}`",
        f"- Overall status: `{payload.get('overall_status')}`",
        f"- Recommendation: `{payload.get('go_no_go')}`",
        "",
        "## Sections",
        "",
    ]
    for name, status in (payload.get("sections") or {}).items():
        lines.append(f"- `{name}`: `{status}`")
    lines.extend(["", "## Blocking Findings", ""])
    blocking = payload.get("blocking_findings") or []
    if blocking:
        lines.extend(f"- {item}" for item in blocking)
    else:
        lines.append("- none")
    lines.extend(["", "## Pending Evidence", ""])
    pending = payload.get("pending_evidence") or []
    if pending:
        lines.extend(f"- {item}" for item in pending)
    else:
        lines.append("- none")
    lines.extend(["", "## Qualification Evidence", ""])
    qualification = payload.get("qualification_report") or {}
    lines.append(f"- Path: `{qualification.get('path')}`")
    lines.append(f"- Present: `{qualification.get('present')}`")
    lines.append(f"- Verified: `{qualification.get('verified')}`")
    lines.append(f"- Qualification status: `{qualification.get('status')}`")
    lines.append(f"- Recommended status: `{qualification.get('recommended_status')}`")
    lines.append(
        f"- Minimum green soak seconds: `{qualification.get('minimum_green_soak_seconds')}`"
    )
    if qualification.get("error_code"):
        lines.append(f"- Error code: `{qualification.get('error_code')}`")
    supported = qualification.get("supported_profiles") or []
    conditional = qualification.get("conditional_profiles") or []
    unsupported = qualification.get("unsupported_profiles") or []
    if supported or conditional or unsupported:
        lines.extend(["", "| Support Boundary | Status | Notes |", "| --- | --- | --- |"])
        for group in (supported, conditional, unsupported):
            for item in group:
                lines.append(
                    f"| {item.get('scenario')} | {item.get('status')} | {item.get('notes')} |"
                )
    lines.extend(["", "## Residual Risks", ""])
    lines.extend(f"- {item}" for item in (payload.get("residual_risks") or []))
    return "\n".join(lines) + "\n"


def _store_versions(config: RuntimeConfig, *, initialize: bool) -> dict[str, Any]:
    versions: dict[str, Any] = {}
    descriptors = [
        ("memory", Path(config.memory.db_path), PersistentMemoryStore),
        ("approval", Path(config.governance.approval_store_path), ApprovalStore),
        ("checkpoint", Path(config.team.checkpoint_db_path), TeamCheckpointStore),
    ]
    stores = []
    for name, path, factory in descriptors:
        if not initialize and not path.exists():
            versions[name] = {
                "path": str(path),
                "schema_version": getattr(factory, "SCHEMA_VERSION", "unknown"),
                "exists": False,
            }
            continue
        stores.append((name, factory(path)))
    for name, store in stores:
        version_fn = getattr(store, "schema_version", None)
        versions[name] = {
            "path": _store_path(store),
            "schema_version": version_fn() if callable(version_fn) else "unknown",
            "exists": True,
        }
        close_fn = getattr(store, "close", None)
        if callable(close_fn):
            close_fn()
    return versions


def _backup_targets(config: RuntimeConfig) -> dict[str, str]:
    return {
        "memory_db": config.memory.db_path,
        "approval_store": config.governance.approval_store_path,
        "checkpoint_store": config.team.checkpoint_db_path,
        "audit_dir": config.governance.audit_dir,
        "team_artifacts": config.team.artifact_dir,
        "policy_bundle": config.governance.policy_path,
        "key_manifest": config.keys.key_manifest_path,
    }


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dir_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(str(item.relative_to(path)).encode("utf-8"))
        digest.update(item.read_bytes())
    return digest.hexdigest()


def _store_path(store: object) -> str:
    path = getattr(store, "path", None) or getattr(store, "db_path", None)
    return str(path)


def _section_status(ok: bool, *, fallback: str = "red") -> str:
    return "green" if ok else fallback


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
