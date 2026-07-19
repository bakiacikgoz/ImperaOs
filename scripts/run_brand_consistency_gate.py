from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal

FindingKind = Literal["content", "path", "binary_metadata", "built_artifact"]
FindingClassification = Literal["blocking", "manual_review"]


def _joined(*parts: str) -> str:
    return "".join(parts)


_FIRST_LEGACY_BRAND = _joined("bin", "liquid")
_SECOND_LEGACY_BRAND = _joined("aeg", "is")
FORBIDDEN_TOKENS = tuple(
    sorted(
        {
            _FIRST_LEGACY_BRAND,
            _joined("bin", " ", "liquid"),
            _joined("bin", "-", "liquid"),
            _joined("bin", "_", "liquid"),
            _joined(_FIRST_LEGACY_BRAND, "ai"),
            _SECOND_LEGACY_BRAND,
            _joined(_SECOND_LEGACY_BRAND, "os"),
            _joined(".", _FIRST_LEGACY_BRAND),
            _joined(_FIRST_LEGACY_BRAND, "_"),
            _joined(_SECOND_LEGACY_BRAND, "os", "_"),
            _joined("com.", _FIRST_LEGACY_BRAND),
            _joined("com.", _SECOND_LEGACY_BRAND, "os"),
        },
        key=lambda value: (-len(value), value),
    )
)
REVIEWED_BINARY_ASSETS_PATH = "branding/reviewed_binary_assets.json"
REVIEWED_BINARY_ASSETS_SCHEMA_VERSION = "imperaos.reviewed-binary-assets/v1"
REVIEWED_BUILT_ARTIFACTS_SCHEMA_VERSION = "imperaos.reviewed-built-artifacts/v1"


@dataclass(frozen=True, slots=True)
class BrandAuditFinding:
    path: str
    kind: FindingKind
    token: str
    line: int | None
    classification: FindingClassification
    sha256: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "kind": self.kind,
            "token": self.token,
            "line": self.line,
            "classification": self.classification,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class BrandAuditReport:
    status: Literal["pass", "fail"]
    canonical_brand: str
    legacy_content_match_count: int
    legacy_path_match_count: int
    binary_metadata_match_count: int
    built_artifact_match_count: int
    findings: tuple[BrandAuditFinding, ...]
    scanned_file_count: int
    git_commit: str
    generated_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "canonicalBrand": self.canonical_brand,
            "legacyContentMatchCount": self.legacy_content_match_count,
            "legacyPathMatchCount": self.legacy_path_match_count,
            "binaryMetadataMatchCount": self.binary_metadata_match_count,
            "builtArtifactMatchCount": self.built_artifact_match_count,
            "findings": [finding.as_dict() for finding in self.findings],
            "scannedFileCount": self.scanned_file_count,
            "gitCommit": self.git_commit,
            "generatedAt": self.generated_at,
        }


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _normalized_tokens(forbidden_tokens: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    unique = {(_normalized(token), token) for token in forbidden_tokens}
    return tuple(sorted(unique, key=lambda item: (-len(item[0]), item[0])))


def _first_match(value: str, tokens: tuple[tuple[str, str], ...]) -> str | None:
    normalized = _normalized(value)
    for normalized_token, report_token in tokens:
        if normalized_token in normalized:
            return report_token
    return None


def _git(repo_root: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess:
    executable = os.environ.get("GIT_EXECUTABLE", "git")
    return subprocess.run(
        [executable, "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=text,
    )


def _tracked_paths(repo_root: Path) -> tuple[str, ...]:
    result = _git(repo_root, "ls-files", "-z", text=False)
    return tuple(
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    )


def _git_commit(repo_root: Path) -> str:
    return _git(repo_root, "rev-parse", "HEAD").stdout.strip()


def _is_binary(data: bytes) -> bool:
    if b"\0" in data[:8192]:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _binary_review_finding(
    *,
    path: str,
    token: str,
    sha256: str | None,
) -> BrandAuditFinding:
    return BrandAuditFinding(
        path=path,
        kind="binary_metadata",
        token=token,
        line=None,
        classification="blocking",
        sha256=sha256,
    )


def _artifact_review_finding(
    *,
    path: str,
    token: str,
    sha256: str | None,
) -> BrandAuditFinding:
    return BrandAuditFinding(
        path=path,
        kind="built_artifact",
        token=token,
        line=None,
        classification="blocking",
        sha256=sha256,
    )


def _valid_review_entry(
    *,
    relative_path: object,
    sha256: object,
    reviewed: dict[str, str],
    reserved_path: str | None = None,
) -> bool:
    return bool(
        isinstance(relative_path, str)
        and relative_path
        and "\\" not in relative_path
        and not PurePosixPath(relative_path).is_absolute()
        and not any(part in {"", ".", ".."} for part in relative_path.split("/"))
        and relative_path != reserved_path
        and relative_path not in reviewed
        and isinstance(sha256, str)
        and len(sha256) == 64
        and sha256 == sha256.lower()
        and all(character in "0123456789abcdef" for character in sha256)
    )


def _load_reviewed_binary_assets(
    root: Path,
    tracked_paths: tuple[str, ...],
) -> tuple[dict[str, str], list[BrandAuditFinding]]:
    if REVIEWED_BINARY_ASSETS_PATH not in tracked_paths:
        return {}, []

    manifest_path = root / REVIEWED_BINARY_ASSETS_PATH
    data = manifest_path.read_bytes()
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}, [
            _binary_review_finding(
                path=REVIEWED_BINARY_ASSETS_PATH,
                token="<invalid-binary-review-manifest>",
                sha256=_sha256(data),
            )
        ]

    if (
        not isinstance(payload, dict)
        or set(payload) != {"schemaVersion", "assets"}
        or payload.get("schemaVersion") != REVIEWED_BINARY_ASSETS_SCHEMA_VERSION
        or not isinstance(payload.get("assets"), list)
    ):
        return {}, [
            _binary_review_finding(
                path=REVIEWED_BINARY_ASSETS_PATH,
                token="<invalid-binary-review-manifest>",
                sha256=_sha256(data),
            )
        ]

    reviewed: dict[str, str] = {}
    for entry in payload["assets"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            reviewed = {}
            break
        relative_path = entry.get("path")
        sha256 = entry.get("sha256")
        if not _valid_review_entry(
            relative_path=relative_path,
            sha256=sha256,
            reviewed=reviewed,
            reserved_path=REVIEWED_BINARY_ASSETS_PATH,
        ):
            reviewed = {}
            break
        assert isinstance(relative_path, str)
        assert isinstance(sha256, str)
        reviewed[relative_path] = sha256

    if not reviewed and payload["assets"]:
        return {}, [
            _binary_review_finding(
                path=REVIEWED_BINARY_ASSETS_PATH,
                token="<invalid-binary-review-manifest>",
                sha256=_sha256(data),
            )
        ]
    return reviewed, []


def _load_reviewed_built_artifacts(
    manifest_path: Path | None,
) -> tuple[dict[str, str], list[BrandAuditFinding]]:
    if manifest_path is None:
        return {}, []

    manifest_path = manifest_path.resolve()
    try:
        data = manifest_path.read_bytes()
    except OSError:
        return {}, [
            _artifact_review_finding(
                path=manifest_path.name,
                token="<invalid-reviewed-artifact-manifest>",
                sha256=None,
            )
        ]
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None

    if (
        not isinstance(payload, dict)
        or set(payload) != {"schemaVersion", "artifacts"}
        or payload.get("schemaVersion") != REVIEWED_BUILT_ARTIFACTS_SCHEMA_VERSION
        or not isinstance(payload.get("artifacts"), list)
    ):
        return {}, [
            _artifact_review_finding(
                path=manifest_path.name,
                token="<invalid-reviewed-artifact-manifest>",
                sha256=_sha256(data),
            )
        ]

    reviewed: dict[str, str] = {}
    for entry in payload["artifacts"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            reviewed = {}
            break
        relative_path = entry.get("path")
        sha256 = entry.get("sha256")
        if not _valid_review_entry(
            relative_path=relative_path,
            sha256=sha256,
            reviewed=reviewed,
        ):
            reviewed = {}
            break
        assert isinstance(relative_path, str)
        assert isinstance(sha256, str)
        reviewed[relative_path] = sha256

    if not reviewed and payload["artifacts"]:
        return {}, [
            _artifact_review_finding(
                path=manifest_path.name,
                token="<invalid-reviewed-artifact-manifest>",
                sha256=_sha256(data),
            )
        ]
    return reviewed, []


def _make_report(
    findings: Sequence[BrandAuditFinding],
    *,
    scanned_file_count: int,
    git_commit: str,
) -> BrandAuditReport:
    ordered = tuple(
        sorted(
            findings,
            key=lambda item: (
                item.path,
                item.kind,
                item.line if item.line is not None else 0,
                item.token,
            ),
        )
    )
    return BrandAuditReport(
        status="fail" if any(item.classification == "blocking" for item in ordered) else "pass",
        canonical_brand="ImperaOS",
        legacy_content_match_count=sum(item.kind == "content" for item in ordered),
        legacy_path_match_count=sum(item.kind == "path" for item in ordered),
        binary_metadata_match_count=sum(item.kind == "binary_metadata" for item in ordered),
        built_artifact_match_count=sum(item.kind == "built_artifact" for item in ordered),
        findings=ordered,
        scanned_file_count=scanned_file_count,
        git_commit=git_commit,
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )


def audit_tracked_brand_usage(
    repo_root: Path,
    *,
    forbidden_tokens: tuple[str, ...] = FORBIDDEN_TOKENS,
) -> BrandAuditReport:
    root = Path(repo_root).resolve()
    tokens = _normalized_tokens(forbidden_tokens)
    findings: list[BrandAuditFinding] = []
    tracked_paths = _tracked_paths(root)
    reviewed_binary_assets, review_findings = _load_reviewed_binary_assets(
        root, tracked_paths
    )
    findings.extend(review_findings)
    for relative_path in tracked_paths:
        path_token = _first_match(relative_path, tokens)
        if path_token is not None:
            findings.append(
                BrandAuditFinding(
                    path=relative_path,
                    kind="path",
                    token=path_token,
                    line=None,
                    classification="blocking",
                )
            )

        data = (root / relative_path).read_bytes()
        if _is_binary(data):
            digest = _sha256(data)
            if reviewed_binary_assets.get(relative_path) == digest:
                continue
            findings.append(
                BrandAuditFinding(
                    path=relative_path,
                    kind="binary_metadata",
                    token="<binary>",
                    line=None,
                    classification="manual_review",
                    sha256=digest,
                )
            )
            continue

        for line_number, line in enumerate(data.decode("utf-8").splitlines(), start=1):
            content_token = _first_match(line, tokens)
            if content_token is not None:
                findings.append(
                    BrandAuditFinding(
                        path=relative_path,
                        kind="content",
                        token=content_token,
                        line=line_number,
                        classification="blocking",
                    )
                )

    tracked_path_set = set(tracked_paths)
    for relative_path, expected_sha256 in reviewed_binary_assets.items():
        if relative_path not in tracked_path_set:
            findings.append(
                _binary_review_finding(
                    path=relative_path,
                    token="<stale-binary-review>",
                    sha256=expected_sha256,
                )
            )
            continue
        data = (root / relative_path).read_bytes()
        actual_sha256 = _sha256(data)
        if not _is_binary(data) or actual_sha256 != expected_sha256:
            findings.append(
                _binary_review_finding(
                    path=relative_path,
                    token="<binary-review-mismatch>",
                    sha256=actual_sha256,
                )
            )

    return _make_report(
        findings,
        scanned_file_count=len(tracked_paths),
        git_commit=_git_commit(root),
    )


def audit_built_artifacts(
    roots: Sequence[Path],
    *,
    forbidden_tokens: tuple[str, ...] = FORBIDDEN_TOKENS,
    repo_root: Path | None = None,
    reviewed_artifact_manifest: Path | None = None,
) -> BrandAuditReport:
    tokens = _normalized_tokens(forbidden_tokens)
    reviewed_artifacts, findings = _load_reviewed_built_artifacts(reviewed_artifact_manifest)
    reviewed_seen: set[str] = set()
    scanned_file_count = 0
    for requested_root in roots:
        root = Path(requested_root).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"artifact root is not a directory: {requested_root}")
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            scanned_file_count += 1
            relative_path = f"{root.name}/{path.relative_to(root).as_posix()}"
            data = path.read_bytes()
            path_token = _first_match(relative_path, tokens)
            if path_token is not None:
                findings.append(
                    BrandAuditFinding(
                        path=relative_path,
                        kind="built_artifact",
                        token=path_token,
                        line=None,
                        classification="blocking",
                        sha256=_sha256(data),
                    )
                )
            if _is_binary(data):
                digest = _sha256(data)
                expected_digest = reviewed_artifacts.get(relative_path)
                if expected_digest == digest:
                    reviewed_seen.add(relative_path)
                    continue
                findings.append(
                    _artifact_review_finding(
                        path=relative_path,
                        token=(
                            "<reviewed-built-artifact-mismatch>"
                            if expected_digest is not None
                            else "<unreviewed-built-artifact>"
                        ),
                        sha256=digest,
                    )
                )
                continue
            for line_number, line in enumerate(data.decode("utf-8").splitlines(), start=1):
                content_token = _first_match(line, tokens)
                if content_token is not None:
                    findings.append(
                        BrandAuditFinding(
                            path=relative_path,
                            kind="built_artifact",
                            token=content_token,
                            line=line_number,
                            classification="blocking",
                            sha256=_sha256(data),
                        )
                    )
    for relative_path, expected_digest in reviewed_artifacts.items():
        if relative_path not in reviewed_seen and not any(
            finding.path == relative_path
            and finding.token == "<reviewed-built-artifact-mismatch>"
            for finding in findings
        ):
            findings.append(
                _artifact_review_finding(
                    path=relative_path,
                    token="<stale-reviewed-built-artifact>",
                    sha256=expected_digest,
                )
            )

    return _make_report(
        findings,
        scanned_file_count=scanned_file_count,
        git_commit=_git_commit(Path(repo_root or Path.cwd()).resolve()),
    )


def _markdown(report: BrandAuditReport) -> str:
    rows = []
    for finding in report.findings:
        path = finding.path.replace("|", "\\|")
        token = finding.token.replace("|", "\\|")
        rows.append(
            f"| {path} | {finding.kind} | {token} | "
            f"{finding.line if finding.line is not None else ''} | "
            f"{finding.classification} | {finding.sha256 or ''} |"
        )
    if not rows:
        rows.append("| _none_ |  |  |  |  |  |")
    return "\n".join(
        [
            "# ImperaOS Brand Audit Report",
            "",
            f"Status: **{report.status}**",
            f"Generated: {report.generated_at}",
            f"Git commit: `{report.git_commit}`",
            f"Scanned files: {report.scanned_file_count}",
            "",
            "| Path | Kind | Token | Line | Classification | SHA-256 |",
            "|---|---|---|---:|---|---|",
            *rows,
            "",
        ]
    )


def write_reports(report: BrandAuditReport, output_root: Path) -> None:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    payload = report.as_dict()
    (root / "brand_audit_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "BRAND_AUDIT_REPORT.md").write_text(_markdown(report), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit ImperaOS brand consistency.")
    parser.add_argument("--mode", choices=("inventory", "enforce", "artifacts"), required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", action="append", default=[], type=Path)
    parser.add_argument("--reviewed-artifact-manifest", type=Path)
    parser.add_argument("--json", action="store_true", dest="print_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.mode == "artifacts":
        if not args.artifact_root:
            parser.error("--artifact-root is required in artifacts mode")
        report = audit_built_artifacts(
            args.artifact_root,
            repo_root=args.repo_root,
            reviewed_artifact_manifest=args.reviewed_artifact_manifest,
        )
    else:
        if args.artifact_root:
            parser.error("--artifact-root is only valid in artifacts mode")
        if args.reviewed_artifact_manifest:
            parser.error("--reviewed-artifact-manifest is only valid in artifacts mode")
        report = audit_tracked_brand_usage(args.repo_root)
    write_reports(report, args.output_root)
    if args.print_json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    if args.mode == "inventory":
        return 0
    if args.mode == "enforce":
        return int(bool(report.findings))
    return int(report.status == "fail")


if __name__ == "__main__":
    raise SystemExit(main())
