from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.storage import file_sha256
from imperaos.release.gate_models import GateArtifactRef, GateArtifactRequirement
from imperaos.release.gate_scanner import scan_file_for_raw_or_secret


def resolve_artifact_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def display_path(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def collect_gate_artifacts(
    *,
    requirements: list[GateArtifactRequirement],
    repo_root: Path,
) -> tuple[list[GateArtifactRef], list[str], list[str], list[str]]:
    refs: list[GateArtifactRef] = []
    missing: list[str] = []
    secret_findings: list[str] = []
    raw_findings: list[str] = []
    for requirement in requirements:
        path = resolve_artifact_path(repo_root, requirement.path)
        if not path.exists():
            if requirement.required_for_ready:
                missing.append(requirement.requirement_id)
            continue
        findings = scan_file_for_raw_or_secret(path)
        reason_codes = findings
        if findings:
            if any("RAW" in item for item in findings):
                raw_findings.extend(findings)
            secret_findings.extend(findings)
        refs.append(
            GateArtifactRef(
                path=display_path(repo_root, path),
                sha256=file_sha256(path),
                sizeBytes=path.stat().st_size,
                kind=requirement.kind,
                schemaRef=requirement.schema_ref,
                contentPersisted=False,
                scanStatus="fail" if findings else "pass",
                reasonCodes=reason_codes,
            )
        )
    return refs, missing, sorted(set(secret_findings)), sorted(set(raw_findings))
