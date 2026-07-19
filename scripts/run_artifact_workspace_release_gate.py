from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from imperaos.artifacts.feature_flags import ARTIFACT_FEATURE_FLAG_NAMES
from scripts.check_artifact_workspace_compatibility import evaluate_dependency_matrix

GATE_REPORTS = {
    "contract": "contract-report.json",
    "storage": "storage-integrity-report.json",
    "rpc": "rpc-performance-report.json",
    "security": "security-report.json",
    "ui": "ui-report.json",
    "e2e": "e2e-report.json",
    "export": "export-report.json",
    "license": "license-report.json",
}
REQUIRED_RELEASE_ARTIFACTS = (
    "contract-report.json",
    "storage-integrity-report.json",
    "rpc-performance-report.json",
    "security-report.json",
    "UI_TEST_REPORT.md",
    "export-report.json",
    "license-report.json",
    "release-readiness.json",
    "RELEASE_READINESS.md",
    "NO_SHIP_REGISTER.md",
)
TEST_GATES = frozenset(GATE_REPORTS)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_PERFORMANCE_MARKER = "ARTIFACT_PERFORMANCE_JSON="


def _python_tests(*paths: str) -> list[str]:
    return [sys.executable, "-m", "pytest", "-vv", "--tb=short", *paths]


def _panel(*args: str) -> list[str]:
    return ["corepack", "pnpm@10.29.2", "--dir", "apps/operator-panel", *args]


def _cargo() -> str:
    suffix = ".exe" if os.name == "nt" else ""
    candidate = Path.home() / ".cargo" / "bin" / f"cargo{suffix}"
    return str(candidate) if candidate.exists() else "cargo"


def gate_commands(gate: str) -> list[list[str]]:
    commands = {
        "contract": [_python_tests(
            "tests/test_artifact_contracts.py",
            "tests/test_artifact_content_schemas.py",
            "tests/test_operator_contracts.py",
            "tests/test_artifact_feature_flags.py",
            "tests/test_artifact_release_docs.py",
        )],
        "storage": [_python_tests(
            "tests/test_artifact_store.py",
            "tests/test_artifact_storage_integrity.py",
            "tests/test_artifact_migrations.py",
            "tests/test_artifact_assets.py",
        )],
        "rpc": [
            _python_tests(
                "tests/test_artifact_rpc_protocol.py",
                "tests/test_artifact_rpc_server.py",
                "tests/test_artifact_tauri_bridge.py",
            ),
            _python_tests("-s", "tests/test_artifact_rpc_performance.py"),
            [_cargo(), "test", "-q", "--manifest-path", "apps/operator-panel/src-tauri/Cargo.toml"],
        ],
        "security": [_python_tests(
            "tests/test_artifact_security_matrix.py",
            "tests/test_artifact_privacy.py",
            "tests/test_artifact_policy.py",
            "tests/test_artifact_proposal_approval.py",
            "tests/test_artifact_assistant_integration.py",
            "tests/test_artifact_form_submission.py",
        )],
        "ui": [
            _panel("test"),
            _panel("lint"),
            _panel("build"),
            _panel("run", "artifact-code:bundle"),
            _panel("run", "artifact-flow:bundle"),
            _panel("run", "i18n:coverage"),
            _panel("run", "bridge:parity"),
        ],
        "e2e": [_panel(
            "exec", "playwright", "test",
            *[f"e2e/{name}" for name in (
                "artifact-document.spec.ts",
                "artifact-form.spec.ts",
                "artifact-code.spec.ts",
                "artifact-flow.spec.ts",
                "artifact-spreadsheet.spec.ts",
                "artifact-canvas.spec.ts",
                "artifact-slides.spec.ts",
                "artifact-conflict.spec.ts",
                "artifact-recovery.spec.ts",
                "artifact-revision-compare.spec.ts",
                "artifact-security.spec.ts",
                "artifact-accessibility.spec.ts",
                "artifact-responsive.spec.ts",
                "assistant-artifact-integration.spec.ts",
            )],
        )],
        "export": [
            _python_tests(
                "tests/test_artifact_exports.py",
                "tests/test_artifact_export_boundary.py",
            ),
            _panel(
                "exec", "vitest", "run",
                "src/artifact-workspace/artifactDocumentExport.test.ts",
                "src/artifact-workspace/artifactCodeExport.test.ts",
                "src/artifact-workspace/artifactFlowExport.test.ts",
                "src/artifact-workspace/artifactSpreadsheetExport.test.ts",
                "src/artifact-workspace/artifactCanvasExport.test.ts",
                "src/artifact-workspace/artifactSlidesExport.test.ts",
                "src/artifact-workspace/artifactStructuredExport.test.ts",
                "src/artifact-workspace/artifactExportFormats.test.ts",
            ),
        ],
        "license": [_python_tests(
            "tests/test_artifact_license_doctor.py",
            "tests/test_artifact_dependency_matrix.py",
        )],
    }
    return commands[gate]


def _test_count(output: str) -> int:
    clean = _ANSI.sub("", output)
    count = 0
    for line in clean.splitlines():
        if re.search(r"\bPASSED\b", line):
            count += 1
            continue
        match = re.search(r"test result: ok\. (\d+) passed", line, flags=re.IGNORECASE)
        if match is None:
            match = re.search(r"Tests\s+(\d+) passed", line, flags=re.IGNORECASE)
        if match is None:
            match = re.search(r"(?:^|\s)(\d+) passed(?:\s|$)", line, flags=re.IGNORECASE)
        if match is not None:
            count += int(match.group(1))
    return count


def _extract_performance_evidence(output: str) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    for line in _ANSI.sub("", output).splitlines():
        marker_index = line.find(_PERFORMANCE_MARKER)
        if marker_index < 0:
            continue
        encoded = line[marker_index + len(_PERFORMANCE_MARKER):].strip()
        try:
            payload = json.loads(encoded)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            evidence.append(payload)
    return evidence


def _run_command(command: list[str], repo_root: Path) -> dict[str, object]:
    started = perf_counter()
    executable = command[0]
    if not Path(executable).is_absolute():
        executable = shutil.which(executable) or executable
    try:
        completed = subprocess.run(  # noqa: S603
            [executable, *command[1:]],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        completed = subprocess.CompletedProcess(
            command,
            127,
            stdout="",
            stderr=f"executable unavailable: {type(exc).__name__}",
        )
    output = completed.stdout + "\n" + completed.stderr
    performance_evidence = _extract_performance_evidence(output)
    return {
        "name": Path(command[0]).name + " " + " ".join(command[1:3]),
        "exitCode": completed.returncode,
        "durationMs": round((perf_counter() - started) * 1_000, 3),
        "testCount": _test_count(output),
        "stdoutSha256": hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest(),
        "stderrSha256": hashlib.sha256(completed.stderr.encode("utf-8")).hexdigest(),
        "performanceEvidence": performance_evidence,
    }


def evaluate_editor_adapter_gate(
    compatibility: dict[str, Any],
    *,
    license_capabilities: dict[str, bool],
    fallback_capabilities: dict[str, bool],
) -> dict[str, object]:
    if not compatibility.get("matrixValid"):
        raise ValueError("artifact dependency matrix is invalid")
    allowed_subjects = {"handsontable", "@handsontable/react-wrapper", "tldraw"}
    for blocker in compatibility.get("blockers", []):
        if (
            blocker.get("code") != "LICENSE_GATE_BLOCKED"
            or blocker.get("subject") not in allowed_subjects
        ):
            raise ValueError("unexpected license blocker")
    if set(license_capabilities) != {"spreadsheet", "canvas"} or set(
        fallback_capabilities
    ) != {"spreadsheet", "canvas"}:
        raise ValueError("editor capability set is incomplete")
    if any(
        not license_capabilities[kind] and not fallback_capabilities[kind]
        for kind in ("spreadsheet", "canvas")
    ):
        raise ValueError("an enabled editor requires a trusted adapter")
    adapters = {
        kind: "commercial" if license_capabilities[kind] else "bundled_fallback"
        for kind in ("spreadsheet", "canvas")
    }
    return {
        "status": "pass",
        "mode": "adapter_resolved",
        "commercialCapabilities": license_capabilities,
        "fallbackCapabilities": fallback_capabilities,
        "effectiveCapabilities": {kind: True for kind in adapters},
        "adapters": adapters,
        "reasonCodes": {
            kind: (
                None
                if license_capabilities[kind]
                else "ARTIFACT_BUNDLED_FALLBACK_ACTIVE"
            )
            for kind in adapters
        },
    }


def run_leaf_gate(
    gate: str,
    *,
    repo_root: Path,
    output_root: Path,
    candidate_sha: str,
    profile: str,
    command_runner: Callable[[list[str], Path], dict[str, object]] = _run_command,
) -> dict[str, object]:
    results = [command_runner(command, repo_root) for command in gate_commands(gate)]
    test_count = sum(int(result["testCount"]) for result in results)
    performance_evidence = [
        evidence
        for result in results
        for evidence in result.get("performanceEvidence", [])
        if isinstance(evidence, dict)
    ]
    blocking = [
        f"COMMAND_FAILED:{result['name']}"
        for result in results
        if int(result["exitCode"]) != 0
    ]
    if gate in TEST_GATES and test_count == 0:
        blocking.append(f"ZERO_TESTS:{gate}")
    if gate in {"rpc", "ui"} and not performance_evidence:
        blocking.append(f"PERFORMANCE_EVIDENCE_MISSING:{gate}")
    extra: dict[str, object] = {}
    if gate == "license" and not blocking:
        try:
            extra["licenseDecision"] = evaluate_editor_adapter_gate(
                evaluate_dependency_matrix(repo_root),
                license_capabilities={"spreadsheet": False, "canvas": False},
                fallback_capabilities={"spreadsheet": True, "canvas": True},
            )
        except ValueError as exc:
            blocking.append(f"LICENSE_POLICY_INVALID:{exc}")
    report: dict[str, object] = {
        "schemaVersion": "artifact-workspace-gate/v1",
        "gate": gate,
        "profile": profile,
        "candidateSha": candidate_sha,
        "generatedAtUtc": _now(),
        "status": "pass" if not blocking else "fail",
        "testCount": test_count,
        "durationMs": round(sum(float(item["durationMs"]) for item in results), 3),
        "commands": results,
        "performanceEvidence": performance_evidence,
        "blockingReasons": blocking,
        **extra,
    }
    _write_json(output_root / GATE_REPORTS[gate], report)
    if gate in {"ui", "e2e"}:
        _write_ui_report(output_root)
    return report


def build_release_readiness(
    candidate_sha: str,
    reports: dict[str, dict[str, object]],
    *,
    dirty_paths: list[str],
    final_candidate_sha: str | None = None,
    final_dirty_paths: list[str] | None = None,
) -> dict[str, object]:
    blocking = [f"DIRTY_WORKTREE:{path}" for path in dirty_paths]
    if final_candidate_sha is not None and final_candidate_sha != candidate_sha:
        blocking.append("CANDIDATE_CHANGED")
    blocking.extend(
        f"FINAL_DIRTY_WORKTREE:{path}" for path in (final_dirty_paths or [])
    )
    for gate in GATE_REPORTS:
        report = reports.get(gate)
        if report is None:
            blocking.append(f"REPORT_MISSING:{gate}")
            continue
        if report.get("candidateSha") != candidate_sha:
            blocking.append(f"CANDIDATE_MISMATCH:{gate}")
        if report.get("status") != "pass":
            blocking.append(f"GATE_FAILED:{gate}")
        if gate in TEST_GATES and int(report.get("testCount") or 0) < 1:
            blocking.append(f"ZERO_TESTS:{gate}")
    return {
        "schemaVersion": "artifact-workspace-release-readiness/v1",
        "candidateSha": candidate_sha,
        "generatedAtUtc": _now(),
        "status": "pass" if not blocking else "fail",
        "shipReady": not blocking,
        "editorAdapters": {
            "spreadsheet": "bundled_fallback",
            "canvas": "bundled_fallback",
        },
        "featureFlagDefaults": {
            name: False for name in ARTIFACT_FEATURE_FLAG_NAMES
        },
        "gateStatuses": {
            gate: reports.get(gate, {}).get("status", "missing") for gate in GATE_REPORTS
        },
        "blockingReasons": blocking,
    }


def run_workspace_release(
    *,
    repo_root: Path,
    output_root: Path,
    profile: str,
) -> dict[str, object]:
    candidate = _git(repo_root, "rev-parse", "HEAD").strip()
    dirty = [line for line in _git(repo_root, "status", "--porcelain=v1").splitlines() if line]
    reports = {
        gate: run_leaf_gate(
            gate,
            repo_root=repo_root,
            output_root=output_root,
            candidate_sha=candidate,
            profile=profile,
        )
        for gate in GATE_REPORTS
    }
    final_candidate = _git(repo_root, "rev-parse", "HEAD").strip()
    final_dirty = [
        line
        for line in _git(repo_root, "status", "--porcelain=v1").splitlines()
        if line
    ]
    readiness = build_release_readiness(
        candidate,
        reports,
        dirty_paths=dirty,
        final_candidate_sha=final_candidate,
        final_dirty_paths=final_dirty,
    )
    _write_json(output_root / "release-readiness.json", readiness)
    (output_root / "RELEASE_READINESS.md").write_text(
        _render_readiness(readiness), encoding="utf-8"
    )
    (output_root / "NO_SHIP_REGISTER.md").write_text(
        _render_no_ship(readiness), encoding="utf-8"
    )
    _write_ui_report(output_root)
    return readiness


def _write_ui_report(output_root: Path) -> None:
    rows = []
    for gate in ("ui", "e2e"):
        path = output_root / GATE_REPORTS[gate]
        report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        rows.append(
            f"| {gate} | {report.get('status', 'missing')} | {report.get('testCount', 0)} |"
        )
    (output_root / "UI_TEST_REPORT.md").write_text(
        "# Artifact Workspace UI Test Report\n\n"
        "| Gate | Status | Tests |\n| --- | --- | ---: |\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )


def _render_readiness(report: dict[str, object]) -> str:
    lines = [
        "# Artifact Workspace Release Readiness",
        "",
        f"- Candidate: `{report['candidateSha']}`",
        f"- Status: `{report['status']}`",
        f"- Ship ready: `{str(report['shipReady']).lower()}`",
        "- Optional editors: `spreadsheet, canvas` use trusted bundled fallback "
        "adapters when commercial entitlement is absent",
        "",
        "## Gate statuses",
        "",
    ]
    lines.extend(
        f"- `{gate}`: `{status}`" for gate, status in report["gateStatuses"].items()
    )
    return "\n".join(lines) + "\n"


def _render_no_ship(report: dict[str, object]) -> str:
    reasons = list(report["blockingReasons"])
    lines = ["# No-Ship Register", ""]
    lines.extend(["- none"] if not reasons else [f"- {reason}" for reason in reasons])
    return "\n".join(lines) + "\n"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError("git candidate inspection failed")
    return completed.stdout


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run artifact workspace release gates")
    parser.add_argument("--gate", choices=(*GATE_REPORTS, "workspace-release"), required=True)
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/artifact-workspace-release"),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    output_root = (
        args.output_root if args.output_root.is_absolute() else repo_root / args.output_root
    )
    if args.gate == "workspace-release":
        report = run_workspace_release(
            repo_root=repo_root, output_root=output_root, profile=args.profile
        )
    else:
        candidate = _git(repo_root, "rev-parse", "HEAD").strip()
        report = run_leaf_gate(
            args.gate,
            repo_root=repo_root,
            output_root=output_root,
            candidate_sha=candidate,
            profile=args.profile,
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
