from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_brand_consistency_gate.py"
SCHEMA = REPO_ROOT / "contracts" / "rebrand" / "brand_audit_report.schema.json"
GIT = shutil.which("git")
REVIEW_MANIFEST = "branding/reviewed_binary_assets.json"


def _legacy(*parts: str) -> str:
    return "".join(parts)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    assert GIT is not None, "git is required for the brand consistency gate tests"
    return subprocess.run(
        [GIT, "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _tracked_repo(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.email", "brand-gate@example.invalid")
    _git(repo, "config", "user.name", "Brand Gate Test")
    for relative_path, content in files.items():
        path = repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "--quiet", "-m", "fixture")
    return repo


def _binary_review_manifest(entries: list[tuple[str, str]]) -> str:
    return json.dumps(
        {
            "schemaVersion": "imperaos.reviewed-binary-assets/v1",
            "assets": [{"path": path, "sha256": sha256} for path, sha256 in entries],
        }
    )


def _artifact_review_manifest(entries: list[tuple[str, str]]) -> str:
    return json.dumps(
        {
            "schemaVersion": "imperaos.reviewed-built-artifacts/v1",
            "artifacts": [{"path": path, "sha256": sha256} for path, sha256 in entries],
        }
    )


def _run_gate(
    repo: Path,
    output_root: Path,
    *,
    mode: str,
    artifact_roots: tuple[Path, ...] = (),
    reviewed_artifact_manifest: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    assert GIT is not None, "git is required for the brand consistency gate tests"
    env["GIT_EXECUTABLE"] = GIT
    command = [
        sys.executable,
        str(SCRIPT),
        "--mode",
        mode,
        "--repo-root",
        str(repo),
        "--output-root",
        str(output_root),
        "--json",
    ]
    for artifact_root in artifact_roots:
        command.extend(("--artifact-root", str(artifact_root)))
    if reviewed_artifact_manifest is not None:
        command.extend(("--reviewed-artifact-manifest", str(reviewed_artifact_manifest)))
    return subprocess.run(command, capture_output=True, text=True, env=env)


def _report(output_root: Path) -> dict[str, object]:
    return json.loads((output_root / "brand_audit_report.json").read_text(encoding="utf-8"))


def test_inventory_normalizes_and_scans_tracked_paths_text_and_binary(tmp_path: Path) -> None:
    first_brand = _legacy("bin", "liquid")
    second_brand = _legacy("aeg", "is", "os")
    repo = _tracked_repo(
        tmp_path,
        {
            f"docs/{first_brand[:3].upper()}-{first_brand[3:].upper()}-notes.txt": (
                f"safe first line\n{first_brand.swapcase()} runtime\n"
                "\uff21\uff25\uff27\uff29\uff33\uff2f\uff33 provider\n"
            ),
            "assets/logo.bin": b"\x89PNG\x00\x01brand-metadata",
            "ignored.txt": second_brand,
        },
    )
    _git(repo, "update-index", "--assume-unchanged", "ignored.txt")
    output_root = tmp_path / "inventory"

    result = _run_gate(repo, output_root, mode="inventory")

    assert result.returncode == 0, result.stderr
    report = _report(output_root)
    assert report["status"] == "fail"
    assert report["canonicalBrand"] == "ImperaOS"
    assert report["scannedFileCount"] == 3
    assert report["gitCommit"] == _git(repo, "rev-parse", "HEAD").stdout.strip()
    findings = report["findings"]
    assert isinstance(findings, list)
    assert any(item["kind"] == "path" and item["classification"] == "blocking" for item in findings)
    assert any(
        item["kind"] == "content"
        and item["line"] == 2
        and item["classification"] == "blocking"
        for item in findings
    )
    assert any(
        item["kind"] == "content" and item["line"] == 3 and item["token"] == second_brand
        for item in findings
    )
    binary = next(item for item in findings if item["kind"] == "binary_metadata")
    assert binary["classification"] == "manual_review"
    assert binary["line"] is None
    assert len(binary["sha256"]) == 64
    assert report["legacyContentMatchCount"] > 0
    assert report["legacyPathMatchCount"] > 0
    assert report["binaryMetadataMatchCount"] == 1
    assert report["builtArtifactMatchCount"] == 0
    assert (output_root / "BRAND_AUDIT_REPORT.md").is_file()
    assert json.loads(result.stdout) == report


def test_enforce_returns_one_for_blocking_or_manual_review_findings(tmp_path: Path) -> None:
    forbidden = _legacy("bin", "_", "liquid")
    blocking_repo = _tracked_repo(tmp_path / "blocking", {"settings.txt": forbidden})
    blocking = _run_gate(blocking_repo, tmp_path / "blocking-report", mode="enforce")
    assert blocking.returncode == 1
    assert _report(tmp_path / "blocking-report")["status"] == "fail"

    binary_repo = _tracked_repo(tmp_path / "binary", {"image.bin": b"\x00\x01\x02"})
    manual_only = _run_gate(binary_repo, tmp_path / "binary-report", mode="enforce")
    assert manual_only.returncode == 1, manual_only.stderr
    manual_report = _report(tmp_path / "binary-report")
    assert manual_report["status"] == "pass"
    assert manual_report["binaryMetadataMatchCount"] == 1


def test_enforce_accepts_hash_pinned_reviewed_binary(tmp_path: Path) -> None:
    binary = b"\x00\x01\x02"
    digest = hashlib.sha256(binary).hexdigest()
    repo = _tracked_repo(
        tmp_path,
        {
            "image.bin": binary,
            REVIEW_MANIFEST: _binary_review_manifest([("image.bin", digest)]),
        },
    )

    result = _run_gate(repo, tmp_path / "report", mode="enforce")

    assert result.returncode == 0, result.stderr
    report = _report(tmp_path / "report")
    assert report["status"] == "pass"
    assert report["binaryMetadataMatchCount"] == 0
    assert report["findings"] == []


def test_enforce_blocks_reviewed_binary_hash_drift(tmp_path: Path) -> None:
    expected = hashlib.sha256(b"\x00\x01\x02").hexdigest()
    repo = _tracked_repo(
        tmp_path,
        {
            "image.bin": b"\x00\x01\x03",
            REVIEW_MANIFEST: _binary_review_manifest([("image.bin", expected)]),
        },
    )

    result = _run_gate(repo, tmp_path / "report", mode="enforce")

    assert result.returncode == 1
    report = _report(tmp_path / "report")
    assert report["status"] == "fail"
    assert {item["classification"] for item in report["findings"]} == {
        "blocking",
        "manual_review",
    }
    assert any(item["token"] == "<binary-review-mismatch>" for item in report["findings"])


def test_enforce_blocks_stale_reviewed_binary_entry(tmp_path: Path) -> None:
    digest = hashlib.sha256(b"missing").hexdigest()
    repo = _tracked_repo(
        tmp_path,
        {REVIEW_MANIFEST: _binary_review_manifest([("missing.bin", digest)])},
    )

    result = _run_gate(repo, tmp_path / "report", mode="enforce")

    assert result.returncode == 1
    report = _report(tmp_path / "report")
    assert report["status"] == "fail"
    assert report["binaryMetadataMatchCount"] == 1
    assert report["findings"][0]["token"] == "<stale-binary-review>"


def test_enforce_blocks_invalid_review_manifest(tmp_path: Path) -> None:
    repo = _tracked_repo(
        tmp_path,
        {REVIEW_MANIFEST: '{"schemaVersion":"invalid","assets":[]}'},
    )

    result = _run_gate(repo, tmp_path / "report", mode="enforce")

    assert result.returncode == 1
    report = _report(tmp_path / "report")
    assert report["status"] == "fail"
    assert report["findings"][0]["token"] == "<invalid-binary-review-manifest>"


def test_artifact_mode_scans_untracked_build_outputs(tmp_path: Path) -> None:
    repo = _tracked_repo(tmp_path, {"README.md": "ImperaOS"})
    artifact_root = tmp_path / "dist"
    artifact_root.mkdir()
    (artifact_root / "metadata.txt").write_text(
        f"Name: {_legacy('Bin', 'Liquid', 'AI')}",
        encoding="utf-8",
    )
    (artifact_root / "application.bin").write_bytes(b"\x00\x01\x02")
    (artifact_root / f"{_legacy('aeg', 'is')}-launcher.txt").write_text(
        "ImperaOS",
        encoding="utf-8",
    )
    output_root = tmp_path / "artifact-report"

    result = _run_gate(
        repo,
        output_root,
        mode="artifacts",
        artifact_roots=(artifact_root,),
    )

    assert result.returncode == 1
    report = _report(output_root)
    assert report["status"] == "fail"
    assert report["builtArtifactMatchCount"] == 3
    assert all(item["kind"] == "built_artifact" for item in report["findings"])
    assert {item["classification"] for item in report["findings"]} == {"blocking"}


def test_artifact_mode_fails_closed_until_binary_hash_is_reviewed(tmp_path: Path) -> None:
    repo = _tracked_repo(tmp_path, {"README.md": "ImperaOS"})
    artifact_root = tmp_path / "dist"
    artifact_root.mkdir()
    binary = b"\x00\x01\x02"
    (artifact_root / "application.bin").write_bytes(binary)

    unknown_output = tmp_path / "unknown-report"
    unknown = _run_gate(
        repo,
        unknown_output,
        mode="artifacts",
        artifact_roots=(artifact_root,),
    )

    assert unknown.returncode == 1
    unknown_report = _report(unknown_output)
    assert unknown_report["status"] == "fail"
    assert unknown_report["findings"][0]["token"] == "<unreviewed-built-artifact>"

    manifest = tmp_path / "reviewed-artifacts.json"
    manifest.write_text(
        _artifact_review_manifest(
            [("dist/application.bin", hashlib.sha256(binary).hexdigest())]
        ),
        encoding="utf-8",
    )
    reviewed_output = tmp_path / "reviewed-report"
    reviewed = _run_gate(
        repo,
        reviewed_output,
        mode="artifacts",
        artifact_roots=(artifact_root,),
        reviewed_artifact_manifest=manifest,
    )

    assert reviewed.returncode == 0, reviewed.stderr
    reviewed_report = _report(reviewed_output)
    assert reviewed_report["status"] == "pass"
    assert reviewed_report["findings"] == []


def test_artifact_mode_blocks_drift_stale_and_invalid_review_entries(tmp_path: Path) -> None:
    repo = _tracked_repo(tmp_path, {"README.md": "ImperaOS"})
    artifact_root = tmp_path / "dist"
    artifact_root.mkdir()
    (artifact_root / "application.bin").write_bytes(b"\x00\x01\x02")

    cases = (
        (
            "drift",
            _artifact_review_manifest(
                [("dist/application.bin", hashlib.sha256(b"different").hexdigest())]
            ),
            "<reviewed-built-artifact-mismatch>",
        ),
        (
            "stale",
            _artifact_review_manifest(
                [("dist/missing.bin", hashlib.sha256(b"missing").hexdigest())]
            ),
            "<stale-reviewed-built-artifact>",
        ),
        (
            "invalid",
            json.dumps({"schemaVersion": "invalid", "artifacts": []}),
            "<invalid-reviewed-artifact-manifest>",
        ),
    )

    for name, manifest_content, expected_token in cases:
        manifest = tmp_path / f"{name}.json"
        manifest.write_text(manifest_content, encoding="utf-8")
        output_root = tmp_path / f"{name}-report"
        result = _run_gate(
            repo,
            output_root,
            mode="artifacts",
            artifact_roots=(artifact_root,),
            reviewed_artifact_manifest=manifest,
        )

        assert result.returncode == 1
        report = _report(output_root)
        assert report["status"] == "fail"
        assert any(item["token"] == expected_token for item in report["findings"])


def test_report_schema_is_strict_and_accepts_generated_report(tmp_path: Path) -> None:
    repo = _tracked_repo(tmp_path, {"README.md": "ImperaOS"})
    output_root = tmp_path / "report"
    result = _run_gate(repo, output_root, mode="inventory")
    assert result.returncode == 0, result.stderr

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["finding"]["additionalProperties"] is False
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(
        _report(output_root)
    )


def test_scanner_source_does_not_embed_forbidden_tokens() -> None:
    forbidden_tokens = (
        _legacy("bin", "liquid"),
        _legacy("bin", " ", "liquid"),
        _legacy("bin", "-", "liquid"),
        _legacy("bin", "_", "liquid"),
        _legacy("bin", "liquid", "ai"),
        _legacy("aeg", "is"),
        _legacy("aeg", "is", "os"),
    )
    for source_path in (SCRIPT, Path(__file__)):
        source = source_path.read_text(encoding="utf-8").casefold()
        assert all(token not in source for token in forbidden_tokens), source_path
