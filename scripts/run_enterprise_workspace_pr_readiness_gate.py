from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLOSURE_ROOT = REPO_ROOT / "artifacts" / "enterprise-workspace-release-closure"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "enterprise-workspace-pr-readiness"
DEFAULT_EXPECTED_BRANCH = "codex/enterprise-workspace-onboarding-agent-enrollment-v1"
DEFAULT_BASE_REF = "origin/main"

REQUIRED_WORKFLOW_MARKERS = (
    "scripts/run_enterprise_workspace_release_closure_gate.py",
    "actions/upload-artifact",
    "target-codex-test",
)

ALLOWED_READINESS_ONLY_PATHS = (
    "scripts/run_enterprise_workspace_pr_readiness_gate.py",
    "scripts/run_enterprise_workspace_remote_pr_ci_gate.py",
    "tests/test_enterprise_workspace_pr_readiness_gate.py",
    "tests/test_enterprise_workspace_remote_pr_ci_gate.py",
    "docs/ENTERPRISE_WORKSPACE_PR_READINESS.md",
    "docs/ENTERPRISE_WORKSPACE_REMOTE_PR_CI_CLOSURE.md",
    ".github/workflows/enterprise-workspace-release-closure.yml",
    "Makefile",
)

RAW_MARKERS = (
    "rawToken",
    "enrollmentToken",
    "shown-once-token-test-value",
    "api_key",
    "private_key",
    "BEGIN PRIVATE KEY",
    "password=",
    "secret=",
    "Authorization: Bearer",
)

REMOTE_COMMAND_FORBIDDEN = (
    "--force",
    "push -f",
    "reset --hard",
    "branch -D",
    "gh pr merge",
    "git clean -fd",
)

STATUS_PASS = "pass"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"
STATUS_BLOCKED = "blocked"


class GateCheckResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    status: Literal["pass", "warn", "fail", "blocked", "skipped"]
    required: bool = True
    reason_code: str = Field(alias="reasonCode")
    command: list[str] | None = None
    duration_ms: int | None = Field(default=None, alias="durationMs")
    tail: list[str] = Field(default_factory=list)


class WorkflowCoverage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: Literal["pass", "warn", "fail"]
    matched_workflows: list[str] = Field(alias="matchedWorkflows")
    missing_commands: list[str] = Field(alias="missingCommands")
    recommended_action: str | None = Field(default=None, alias="recommendedAction")
    artifact_upload_configured: bool = Field(alias="artifactUploadConfigured")


class MainlineRehearsal(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: Literal["pass", "warn", "fail", "skipped"]
    base_ref: str = Field(alias="baseRef")
    head_sha: str = Field(alias="headSha")
    ahead_commits: int = Field(alias="aheadCommits")
    changed_files: list[str] = Field(alias="changedFiles")
    risk_areas: list[str] = Field(alias="riskAreas")
    conflict_diagnostic: str | None = Field(default=None, alias="conflictDiagnostic")
    warnings: list[str] = Field(default_factory=list)


class EnterpriseWorkspacePrReadinessReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: Literal["enterprise-workspace.pr-readiness/v1"] = Field(
        alias="schemaVersion"
    )
    status: Literal["pass", "warn", "blocked", "fail"]
    profile: str
    branch: str
    base_ref: str = Field(alias="baseRef")
    head_sha: str = Field(alias="headSha")
    git_status_short: str = Field(alias="gitStatusShort")
    closure_report_path: str = Field(alias="closureReportPath")
    closure_report_hash: str = Field(alias="closureReportHash")
    closure_status: str = Field(alias="closureStatus")
    check_results: list[GateCheckResult] = Field(alias="checkResults")
    workflow_coverage: WorkflowCoverage = Field(alias="workflowCoverage")
    mainline_rehearsal: MainlineRehearsal = Field(alias="mainlineRehearsal")
    raw_leak_scan: dict[str, Any] = Field(alias="rawLeakScan")
    no_ship_blockers: list[str] = Field(alias="noShipBlockers")
    warnings: list[str]
    push_performed: Literal[False] = Field(alias="pushPerformed")
    pr_created: Literal[False] = Field(alias="prCreated")
    generated_at_utc: str = Field(alias="generatedAtUtc")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _relative(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)


def _redact(value: str, repo_root: Path = REPO_ROOT) -> str:
    redacted = value.replace(str(repo_root), "<repo>").replace(str(Path.home()), "<home>")
    redacted = re.sub(
        r"(?i)(api[_-]?key|private[_-]?key|password|secret|token)\s*[:=]\s*\S+",
        r"\1=<redacted>",
        redacted,
    )
    redacted = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-<redacted>", redacted)
    return redacted


def _resolve(command: list[str]) -> list[str]:
    executable = command[0]
    candidates = [executable]
    if os.name == "nt" and Path(executable).suffix == "":
        candidates = [f"{executable}.cmd", f"{executable}.exe", executable]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return [resolved, *command[1:]]
    return command


def _run_git(
    args: list[str],
    *,
    repo_root: Path = REPO_ROOT,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _git_text(args: list[str], *, repo_root: Path = REPO_ROOT) -> str:
    result = _run_git(args, repo_root=repo_root)
    return result.stdout.strip() if result.returncode == 0 else ""


def _command_check(
    name: str,
    command: list[str],
    *,
    repo_root: Path = REPO_ROOT,
    required: bool = True,
) -> GateCheckResult:
    started = time.monotonic()
    try:
        result = subprocess.run(
            _resolve(command),
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        return GateCheckResult(
            name=name,
            status="blocked",
            required=required,
            reasonCode="EXECUTABLE_MISSING",
            command=command,
            durationMs=int((time.monotonic() - started) * 1000),
            tail=[_redact(str(exc), repo_root)],
        )
    status = "pass" if result.returncode == 0 else "fail"
    return GateCheckResult(
        name=name,
        status=status,
        required=required,
        reasonCode="OK" if result.returncode == 0 else "COMMAND_FAILED",
        command=command,
        durationMs=int((time.monotonic() - started) * 1000),
        tail=[_redact(line, repo_root) for line in result.stdout.splitlines()[-25:]],
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_result_by_name(report: dict[str, Any], name: str) -> dict[str, Any] | None:
    for result in report.get("commandResults", []):
        if result.get("name") == name:
            return result
    return None


def _closure_changed_files(
    closure_head: str,
    current_head: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    if not closure_head or not current_head or closure_head == current_head:
        return []
    result = _run_git(
        ["diff", "--name-only", f"{closure_head}...{current_head}"],
        repo_root=repo_root,
    )
    if result.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _is_readiness_only_change(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(normalized == allowed for allowed in ALLOWED_READINESS_ONLY_PATHS)


def verify_closure_report(
    closure_path: Path,
    *,
    current_head: str,
    repo_root: Path = REPO_ROOT,
) -> tuple[dict[str, Any] | None, list[GateCheckResult], list[str], list[str], str]:
    checks: list[GateCheckResult] = []
    blockers: list[str] = []
    warnings: list[str] = []

    if not closure_path.exists():
        checks.append(
            GateCheckResult(
                name="closure_report_present",
                status="blocked",
                reasonCode="CLOSURE_REPORT_MISSING",
                tail=[_relative(closure_path, repo_root)],
            )
        )
        blockers.append("CLOSURE_REPORT_MISSING")
        return None, checks, blockers, warnings, ""

    closure_hash = _sha256(closure_path)
    try:
        report = _load_json(closure_path)
    except (OSError, json.JSONDecodeError) as exc:
        checks.append(
            GateCheckResult(
                name="closure_report_parse",
                status="blocked",
                reasonCode="CLOSURE_REPORT_INVALID",
                tail=[_redact(str(exc), repo_root)],
            )
        )
        blockers.append("CLOSURE_REPORT_INVALID")
        return None, checks, blockers, warnings, closure_hash

    checks.append(
        GateCheckResult(
            name="closure_report_present",
            status="pass",
            reasonCode="OK",
            tail=[_relative(closure_path, repo_root)],
        )
    )

    closure_status = str(report.get("status", ""))
    if closure_status == "pass":
        checks.append(
            GateCheckResult(name="closure_status", status="pass", reasonCode="OK")
        )
    else:
        checks.append(
            GateCheckResult(
                name="closure_status",
                status="blocked",
                reasonCode="CLOSURE_STATUS_NOT_PASS",
                tail=[closure_status],
            )
        )
        blockers.append("CLOSURE_STATUS_NOT_PASS")

    raw_status = report.get("rawLeakScan", {}).get("status")
    if raw_status == "pass":
        checks.append(GateCheckResult(name="closure_raw_leak_scan", status="pass", reasonCode="OK"))
    else:
        checks.append(
            GateCheckResult(
                name="closure_raw_leak_scan",
                status="fail",
                reasonCode="CLOSURE_RAW_SCAN_FAIL",
                tail=[str(raw_status)],
            )
        )
        blockers.append("CLOSURE_RAW_SCAN_FAIL")

    stable_tauri = _check_result_by_name(report, "tauri_cargo_test_stable_target")
    stable_tauri_passed = bool(stable_tauri and stable_tauri.get("status") == "pass")
    if report.get("tauri", {}).get("status") == "pass" and stable_tauri_passed:
        checks.append(
            GateCheckResult(name="closure_tauri_stable_target", status="pass", reasonCode="OK")
        )
    else:
        checks.append(
            GateCheckResult(
                name="closure_tauri_stable_target",
                status="blocked",
                reasonCode="CLOSURE_TAURI_STABLE_TARGET_NOT_PASS",
            )
        )
        blockers.append("CLOSURE_TAURI_STABLE_TARGET_NOT_PASS")

    required_names = (
        "pytest_full",
        "operator_panel_test",
        "operator_panel_lint",
        "operator_panel_build",
        "enterprise_workspace_e2e",
    )
    for name in required_names:
        result = _check_result_by_name(report, name)
        if result and result.get("status") == "pass":
            checks.append(GateCheckResult(name=f"closure_{name}", status="pass", reasonCode="OK"))
        else:
            checks.append(
                GateCheckResult(
                    name=f"closure_{name}",
                    status="blocked",
                    reasonCode="CLOSURE_REQUIRED_CHECK_MISSING_OR_FAILED",
                )
            )
            blockers.append(f"CLOSURE_REQUIRED_CHECK_MISSING_OR_FAILED:{name}")

    closure_head = str(report.get("headSha", ""))
    if closure_head == current_head:
        checks.append(GateCheckResult(name="closure_head_sha", status="pass", reasonCode="OK"))
    else:
        changed_files = _closure_changed_files(closure_head, current_head, repo_root=repo_root)
        if changed_files and all(_is_readiness_only_change(path) for path in changed_files):
            warnings.append(
                "closure report head is older than current HEAD, but the delta is "
                "limited to PR readiness tooling"
            )
            checks.append(
                GateCheckResult(
                    name="closure_head_sha",
                    status="warn",
                    reasonCode="CLOSURE_HEAD_NEWER_READINESS_ONLY",
                    tail=changed_files,
                )
            )
        else:
            checks.append(
                GateCheckResult(
                    name="closure_head_sha",
                    status="blocked",
                    reasonCode="CLOSURE_HEAD_MISMATCH",
                    tail=changed_files or [f"closure={closure_head}", f"current={current_head}"],
                )
            )
            blockers.append("CLOSURE_HEAD_MISMATCH")

    return report, checks, blockers, warnings, closure_hash


def inspect_workflow_coverage(
    workflow_root: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> WorkflowCoverage:
    matched: list[str] = []
    present_markers: set[str] = set()
    if not workflow_root.exists():
        return WorkflowCoverage(
            status="fail",
            matchedWorkflows=[],
            missingCommands=list(REQUIRED_WORKFLOW_MARKERS),
            recommendedAction="Add .github/workflows/enterprise-workspace-release-closure.yml",
            artifactUploadConfigured=False,
        )

    for path in sorted(workflow_root.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if REQUIRED_WORKFLOW_MARKERS[0] in text:
            matched.append(_relative(path, repo_root))
            workflow_markers = {marker for marker in REQUIRED_WORKFLOW_MARKERS if marker in text}
            present_markers.update(workflow_markers)
    missing = [marker for marker in REQUIRED_WORKFLOW_MARKERS if marker not in present_markers]
    return WorkflowCoverage(
        status="pass" if not missing else "fail",
        matchedWorkflows=matched,
        missingCommands=missing,
        recommendedAction=None
        if not missing
        else "Ensure remote CI runs the enterprise workspace closure gate and uploads artifacts",
        artifactUploadConfigured="actions/upload-artifact" in present_markers,
    )


def _risk_area(path: str) -> str:
    if path.startswith(".github/workflows/"):
        return "workflows"
    if path.startswith("contracts/"):
        return "contracts"
    if path.startswith("apps/operator-panel/"):
        return "ui"
    if path.startswith("imperaos/"):
        return "backend"
    if path.startswith("docs/"):
        return "docs"
    if path.startswith("scripts/"):
        return "scripts"
    if path.startswith("tests/"):
        return "tests"
    return "other"


def run_mainline_rehearsal(
    *,
    base_ref: str,
    head_ref: str,
    repo_root: Path = REPO_ROOT,
    fetch: bool = True,
) -> MainlineRehearsal:
    warnings: list[str] = []
    if fetch:
        fetch_result = _run_git(
            ["fetch", "origin", "main", "--prune"],
            repo_root=repo_root,
            timeout=120,
        )
        if fetch_result.returncode != 0:
            warnings.append(
                "git fetch origin main --prune failed; using local base ref if available"
            )

    base_check = _run_git(["rev-parse", "--verify", base_ref], repo_root=repo_root)
    if base_check.returncode != 0:
        return MainlineRehearsal(
            status="warn",
            baseRef=base_ref,
            headSha=head_ref,
            aheadCommits=0,
            changedFiles=[],
            riskAreas=[],
            conflictDiagnostic="base ref unavailable",
            warnings=[*warnings, f"{base_ref} is unavailable"],
        )

    count_text = _git_text(["rev-list", "--count", f"{base_ref}..{head_ref}"], repo_root=repo_root)
    try:
        ahead = int(count_text)
    except ValueError:
        ahead = 0
    diff_result = _run_git(["diff", "--name-only", f"{base_ref}...{head_ref}"], repo_root=repo_root)
    changed_files = []
    if diff_result.returncode == 0:
        changed_files = [
            line.strip().replace("\\", "/")
            for line in diff_result.stdout.splitlines()
            if line.strip()
        ]
    if diff_result.returncode != 0:
        warnings.append("git diff against base failed")

    merge_result = _run_git(["merge-tree", base_ref, head_ref], repo_root=repo_root, timeout=120)
    conflict_diagnostic = "no conflict markers detected"
    status: Literal["pass", "warn"] = "pass"
    if merge_result.returncode != 0:
        conflict_diagnostic = "merge-tree unavailable or failed"
        warnings.append("merge-tree diagnostic failed")
        status = "warn"
    elif "<<<<<<<" in merge_result.stdout or "CONFLICT" in merge_result.stdout:
        conflict_diagnostic = "merge-tree reported conflict markers"
        status = "warn"

    if warnings:
        status = "warn"
    return MainlineRehearsal(
        status=status,
        baseRef=base_ref,
        headSha=head_ref,
        aheadCommits=ahead,
        changedFiles=changed_files,
        riskAreas=sorted({_risk_area(path) for path in changed_files}),
        conflictDiagnostic=conflict_diagnostic,
        warnings=warnings,
    )


def scan_output_markers(paths: list[Path], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in RAW_MARKERS:
            if marker in text:
                findings.append({"path": _relative(path, repo_root), "marker": marker})
    return {"status": "pass" if not findings else "fail", "findings": findings}


def build_pr_body_final(
    *,
    base_pr_body_path: Path,
    readiness_report: EnterpriseWorkspacePrReadinessReport,
    output_path: Path,
) -> str:
    base = ""
    if base_pr_body_path.exists():
        base = base_pr_body_path.read_text(encoding="utf-8")
    if not base.strip():
        base = (
            "## Summary\n"
            "- Enterprise Workspace Onboarding and Agent Enrollment v1.\n\n"
            "## Validation\n"
            "- Release closure evidence is provided by local artifacts.\n"
        )
    workflow = readiness_report.workflow_coverage
    rehearsal = readiness_report.mainline_rehearsal
    body = (
        base.rstrip()
        + "\n\n"
        "## PR Readiness Evidence\n"
        f"- Readiness gate: `{readiness_report.status}`\n"
        f"- Branch: `{readiness_report.branch}`\n"
        f"- Head SHA: `{readiness_report.head_sha}`\n"
        f"- Closure report hash: `{readiness_report.closure_report_hash}`\n"
        f"- Closure status: `{readiness_report.closure_status}`\n"
        f"- Raw leak scan: `{readiness_report.raw_leak_scan.get('status')}`\n"
        f"- Workflow coverage: `{workflow.status}` "
        f"({len(workflow.matched_workflows)} matched workflow(s))\n"
        f"- Mainline rehearsal: `{rehearsal.status}` ({rehearsal.ahead_commits} commit(s) ahead)\n"
        f"- Push performed by readiness gate: `{readiness_report.push_performed}`\n"
        f"- PR created by readiness gate: `{readiness_report.pr_created}`\n"
        "\n"
        "## No-Ship Boundary\n"
    )
    if readiness_report.no_ship_blockers:
        body += "\n".join(f"- `{blocker}`" for blocker in readiness_report.no_ship_blockers) + "\n"
    else:
        body += "- No local no-ship blockers remain in the readiness report.\n"
    body += (
        "\n"
        "## Optional Environment Diagnostic\n"
        "- Windows/OneDrive default Tauri target-dir failures are treated as diagnostic only.\n"
        "- Required Tauri validation uses "
        "`--target-dir apps/operator-panel/src-tauri/target-codex-test`.\n"
        "\n"
        "## Remote CI Expectation\n"
        "- Remote CI must run the enterprise workspace release closure workflow before "
        "review-ready or merge actions.\n"
    )
    output_path.write_text(body, encoding="utf-8")
    return body


def build_remote_commands(
    *,
    branch: str,
    base_branch: str,
    pr_body_path: Path,
    output_path: Path,
) -> str:
    pr_url = f"https://github.com/bakiacikgoz/ImperaOS/pull/new/{branch}"
    text = (
        "# Enterprise Workspace Remote Commands\n\n"
        "These commands are prepared for an explicit approval step. They were not "
        "executed by the readiness gate.\n\n"
        "## Pre-Push Checks\n\n"
        "```bash\n"
        "git status --short\n"
        "git rev-parse --abbrev-ref HEAD\n"
        "uv run python scripts/run_enterprise_workspace_pr_readiness_gate.py "
        "--profile enterprise --json\n"
        "```\n\n"
        "## Push Command\n\n"
        "```bash\n"
        f"git push -u origin {branch}\n"
        "```\n\n"
        "## Draft PR Command\n\n"
        "```bash\n"
        "gh pr create \\\n"
        "  --draft \\\n"
        f"  --base {base_branch} \\\n"
        f"  --head {branch} \\\n"
        "  --title \"Enterprise Workspace Onboarding and Agent Enrollment\" \\\n"
        f"  --body-file {_relative(pr_body_path, REPO_ROOT)}\n"
        "```\n\n"
        "Manual PR URL when GitHub CLI is unavailable:\n\n"
        f"{pr_url}\n\n"
        "## CI Inspect Commands\n\n"
        "```bash\n"
        "gh pr checks --watch\n"
        f"gh run list --branch {branch} --limit 10\n"
        "gh pr view --json "
        "number,url,headRefName,headRefOid,baseRefName,mergeStateStatus,statusCheckRollup\n"
        "```\n\n"
        "## Approval Boundary\n\n"
        "- Push and draft PR creation require: `ONAY: Branch'i remote'a push et ve draft PR aç.`\n"
        "- Ready-for-review and merge require separate explicit approval.\n"
        "- This command pack intentionally omits destructive git and PR merge commands.\n"
    )
    output_path.write_text(text, encoding="utf-8")
    return text


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_markdown(report: EnterpriseWorkspacePrReadinessReport) -> str:
    lines = [
        "# Enterprise Workspace PR Readiness",
        "",
        f"- Status: `{report.status}`",
        f"- Branch: `{report.branch}`",
        f"- Head: `{report.head_sha}`",
        f"- Base: `{report.base_ref}`",
        f"- Closure status: `{report.closure_status}`",
        f"- Closure hash: `{report.closure_report_hash}`",
        f"- Workflow coverage: `{report.workflow_coverage.status}`",
        f"- Mainline rehearsal: `{report.mainline_rehearsal.status}`",
        f"- Raw leak scan: `{report.raw_leak_scan.get('status')}`",
        f"- Git status: `{'clean' if not report.git_status_short else 'dirty'}`",
        f"- Push performed: `{report.push_performed}`",
        f"- PR created: `{report.pr_created}`",
        "",
        "## Checks",
    ]
    for result in report.check_results:
        lines.append(f"- `{result.status}` `{result.name}` `{result.reason_code}`")
    if report.no_ship_blockers:
        lines.extend(["", "## No-Ship Blockers"])
        lines.extend(f"- `{blocker}`" for blocker in report.no_ship_blockers)
    if report.warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in report.warnings)
    return "\n".join(lines) + "\n"


def run_enterprise_workspace_pr_readiness_gate(
    *,
    profile: str,
    closure_root: Path,
    output_root: Path,
    expected_branch: str | None,
    base_ref: str,
    repo_root: Path = REPO_ROOT,
    fetch_main: bool = True,
) -> EnterpriseWorkspacePrReadinessReport:
    output_root.mkdir(parents=True, exist_ok=True)
    closure_path = closure_root / "closure_report.json"
    base_pr_body_path = closure_root / "pr_body.md"
    branch = _git_text(["branch", "--show-current"], repo_root=repo_root)
    head = _git_text(["rev-parse", "HEAD"], repo_root=repo_root)
    git_status = _git_text(["status", "--short", "--untracked-files=no"], repo_root=repo_root)

    check_results: list[GateCheckResult] = []
    blockers: list[str] = []
    warnings: list[str] = []

    if expected_branch and branch != expected_branch:
        blockers.append("BRANCH_MISMATCH")
        check_results.append(
            GateCheckResult(
                name="branch",
                status="blocked",
                reasonCode="BRANCH_MISMATCH",
                tail=[f"expected={expected_branch}", f"actual={branch}"],
            )
        )
    else:
        check_results.append(GateCheckResult(name="branch", status="pass", reasonCode="OK"))

    if git_status:
        blockers.append("DIRTY_WORKTREE")
        check_results.append(
            GateCheckResult(
                name="git_status",
                status="blocked",
                reasonCode="DIRTY_WORKTREE",
                tail=[_redact(line, repo_root) for line in git_status.splitlines()],
            )
        )
    else:
        check_results.append(GateCheckResult(name="git_status", status="pass", reasonCode="OK"))

    (
        closure,
        closure_checks,
        closure_blockers,
        closure_warnings,
        closure_hash,
    ) = verify_closure_report(
        closure_path,
        current_head=head,
        repo_root=repo_root,
    )
    check_results.extend(closure_checks)
    blockers.extend(closure_blockers)
    warnings.extend(closure_warnings)
    closure_status = str(closure.get("status", "missing")) if closure else "missing"

    workflow = inspect_workflow_coverage(repo_root / ".github" / "workflows", repo_root=repo_root)
    if workflow.status == "pass":
        check_results.append(
            GateCheckResult(name="workflow_coverage", status="pass", reasonCode="OK")
        )
    else:
        blockers.append("WORKFLOW_COVERAGE_MISSING")
        check_results.append(
            GateCheckResult(
                name="workflow_coverage",
                status="blocked",
                reasonCode="WORKFLOW_COVERAGE_MISSING",
                tail=workflow.missing_commands,
            )
        )

    mainline = run_mainline_rehearsal(
        base_ref=base_ref,
        head_ref=head,
        repo_root=repo_root,
        fetch=fetch_main,
    )
    if mainline.status == "fail":
        blockers.append("MAINLINE_REHEARSAL_FAILED")
    if mainline.warnings:
        warnings.extend(mainline.warnings)
    check_results.append(
        GateCheckResult(
            name="mainline_rehearsal",
            status=mainline.status if mainline.status != "skipped" else "skipped",
            reasonCode="OK" if mainline.status in {"pass", "warn"} else "MAINLINE_REHEARSAL_FAILED",
            tail=[mainline.conflict_diagnostic or ""],
        )
    )

    raw_leak_scan = (
        closure.get("rawLeakScan", {"status": "missing", "findings": []})
        if closure
        else {
            "status": "missing",
            "findings": [],
        }
    )

    preliminary_status: Literal["pass", "blocked"] = "pass" if not blockers else "blocked"
    report = EnterpriseWorkspacePrReadinessReport(
        schemaVersion="enterprise-workspace.pr-readiness/v1",
        status=preliminary_status,
        profile=profile,
        branch=branch,
        baseRef=base_ref,
        headSha=head,
        gitStatusShort=git_status,
        closureReportPath=_relative(closure_path, repo_root),
        closureReportHash=closure_hash,
        closureStatus=closure_status,
        checkResults=check_results,
        workflowCoverage=workflow,
        mainlineRehearsal=mainline,
        rawLeakScan=raw_leak_scan,
        noShipBlockers=sorted(set(blockers)),
        warnings=warnings,
        pushPerformed=False,
        prCreated=False,
        generatedAtUtc=_now(),
    )

    report_json = output_root / "pr_readiness_report.json"
    report_md = output_root / "pr_readiness_report.md"
    pr_body_final = output_root / "pr_body_final.md"
    remote_commands = output_root / "remote_commands.md"
    workflow_json = output_root / "workflow_coverage.json"
    mainline_json = output_root / "mainline_rehearsal.json"

    _write_json(report_json, report.model_dump(by_alias=True))
    report_md.write_text(render_markdown(report), encoding="utf-8")
    build_pr_body_final(
        base_pr_body_path=base_pr_body_path,
        readiness_report=report,
        output_path=pr_body_final,
    )
    command_text = build_remote_commands(
        branch=branch,
        base_branch=base_ref.removeprefix("origin/"),
        pr_body_path=pr_body_final,
        output_path=remote_commands,
    )
    _write_json(workflow_json, workflow.model_dump(by_alias=True))
    _write_json(mainline_json, mainline.model_dump(by_alias=True))

    forbidden = [marker for marker in REMOTE_COMMAND_FORBIDDEN if marker in command_text]
    output_scan = scan_output_markers(
        [report_md, pr_body_final, remote_commands],
        repo_root=repo_root,
    )
    if forbidden or output_scan["status"] != "pass":
        blockers = [*report.no_ship_blockers]
        if forbidden:
            blockers.append("REMOTE_COMMAND_PACK_FORBIDDEN_COMMAND")
        if output_scan["status"] != "pass":
            blockers.append("PR_READINESS_OUTPUT_RAW_MARKER")
        report = report.model_copy(
            update={
                "status": "blocked",
                "no_ship_blockers": sorted(set(blockers)),
                "check_results": [
                    *report.check_results,
                    GateCheckResult(
                        name="artifact_safety_scan",
                        status="blocked",
                        reasonCode="ARTIFACT_SAFETY_SCAN_FAILED",
                        tail=forbidden + [str(output_scan["findings"])],
                    ),
                ],
            }
        )
        _write_json(report_json, report.model_dump(by_alias=True))
        report_md.write_text(render_markdown(report), encoding="utf-8")
    else:
        report = report.model_copy(
            update={
                "check_results": [
                    *report.check_results,
                    GateCheckResult(name="artifact_safety_scan", status="pass", reasonCode="OK"),
                ]
            }
        )
        _write_json(report_json, report.model_dump(by_alias=True))
        report_md.write_text(render_markdown(report), encoding="utf-8")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run enterprise workspace PR readiness gate.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--closure-root", type=Path, default=DEFAULT_CLOSURE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--expected-branch", default=DEFAULT_EXPECTED_BRANCH)
    parser.add_argument("--base-ref", default=DEFAULT_BASE_REF)
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    report = run_enterprise_workspace_pr_readiness_gate(
        profile=args.profile,
        closure_root=args.closure_root,
        output_root=args.output_root,
        expected_branch=args.expected_branch,
        base_ref=args.base_ref,
        fetch_main=not args.skip_fetch,
    )
    payload = report.model_dump(by_alias=True)
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"status={report.status} output={args.output_root}")
    return 0 if report.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
