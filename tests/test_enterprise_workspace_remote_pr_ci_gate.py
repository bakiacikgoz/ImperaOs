from __future__ import annotations

import json
from pathlib import Path

from scripts import run_enterprise_workspace_remote_pr_ci_gate as gate

HEAD = "c" * 40
BASE = "b" * 40


def _write_local_evidence(root: Path, *, status: str = "pass", head: str = HEAD) -> None:
    closure_root = root / "release"
    readiness_root = root / "readiness"
    closure_root.mkdir(parents=True)
    readiness_root.mkdir(parents=True)
    (closure_root / "closure_report.json").write_text(
        json.dumps(
            {
                "schemaVersion": "enterprise-workspace.release-closure/v1",
                "status": status,
                "headSha": head,
            }
        ),
        encoding="utf-8",
    )
    (readiness_root / "pr_readiness_report.json").write_text(
        json.dumps(
            {
                "schemaVersion": "enterprise-workspace.pr-readiness/v1",
                "status": status,
                "headSha": head,
                "rawLeakScan": {"status": "pass", "findings": []},
            }
        ),
        encoding="utf-8",
    )


def _write_pr_fixture(path: Path, *, head: str = HEAD, draft: bool = True) -> None:
    path.write_text(
        json.dumps(
            {
                "number": 42,
                "url": "https://github.com/bakiacikgoz/ImperaOS/pull/42",
                "title": "Enterprise Workspace Onboarding & Agent Enrollment v1",
                "isDraft": draft,
                "baseRefName": "main",
                "headRefName": gate.DEFAULT_BRANCH,
                "headRefOid": head,
                "baseRefOid": BASE,
                "changedFiles": 12,
                "additions": 120,
                "deletions": 4,
            }
        ),
        encoding="utf-8",
    )


def _write_ci_fixture(path: Path, checks: list[dict[str, object]]) -> None:
    path.write_text(json.dumps(checks), encoding="utf-8")


def _patch_clean_git(monkeypatch, *, branch: str = gate.DEFAULT_BRANCH, dirty: str = "") -> None:
    def fake_git(args: list[str], *, repo_root: Path = gate.REPO_ROOT) -> str:
        if args == ["branch", "--show-current"]:
            return branch
        if args == ["rev-parse", "HEAD"]:
            return HEAD
        if args == ["rev-parse", "origin/main"]:
            return BASE
        if args in (
            ["status", "--short"],
            ["status", "--short", "--untracked-files=no"],
        ):
            return dirty
        if args[:2] == ["diff", "--name-only"]:
            return "scripts/run_enterprise_workspace_remote_pr_ci_gate.py"
        if args[:2] == ["rev-list", "--left-right"]:
            return "0\t1"
        if args[:3] == ["ls-remote", "--heads", "origin"]:
            return HEAD
        return ""

    monkeypatch.setattr(gate, "_git_text", fake_git)


def test_remote_gate_blocks_without_approval_and_writes_commands(
    tmp_path: Path, monkeypatch
) -> None:
    _write_local_evidence(tmp_path)
    _patch_clean_git(monkeypatch)

    report = gate.run_remote_pr_ci_gate(
        profile="enterprise",
        branch=gate.DEFAULT_BRANCH,
        base_branch="main",
        output_root=tmp_path / "out",
        release_closure_path=tmp_path / "release" / "closure_report.json",
        pr_readiness_path=tmp_path / "readiness" / "pr_readiness_report.json",
        allow_remote=True,
        approval_text=None,
        skip_gh=True,
    )

    assert report.status == "blocked"
    assert "REMOTE_APPROVAL_MISSING" in report.no_ship_blockers
    assert report.remote_push_performed is False
    assert report.pr_created is False
    assert report.merge_performed is False
    assert (tmp_path / "out" / "post_pr_commands.md").exists()


def test_remote_gate_passes_with_fixture_pr_and_successful_ci(
    tmp_path: Path, monkeypatch
) -> None:
    _write_local_evidence(tmp_path)
    _write_pr_fixture(tmp_path / "pr.json")
    _write_ci_fixture(
        tmp_path / "checks.json",
        [
            {
                "name": "CI",
                "state": "completed",
                "conclusion": "success",
                "required": True,
                "link": "https://github.com/checks/ci",
            },
            {
                "name": "Optional diagnostic",
                "state": "completed",
                "conclusion": "failure",
                "required": False,
            },
        ],
    )
    _patch_clean_git(monkeypatch)

    report = gate.run_remote_pr_ci_gate(
        profile="enterprise",
        branch=gate.DEFAULT_BRANCH,
        base_branch="main",
        output_root=tmp_path / "out",
        release_closure_path=tmp_path / "release" / "closure_report.json",
        pr_readiness_path=tmp_path / "readiness" / "pr_readiness_report.json",
        pr_fixture=tmp_path / "pr.json",
        ci_fixture=tmp_path / "checks.json",
        skip_gh=True,
    )

    assert report.status == "pass"
    assert report.ci.status == "pass"
    assert report.no_ship_blockers == []
    assert report.reconciliation.ready is True
    assert report.warnings
    assert (tmp_path / "out" / "remote_pr_ci_report.json").exists()
    assert (tmp_path / "out" / "merge_readiness.md").exists()


def test_sha_mismatch_blocks(tmp_path: Path, monkeypatch) -> None:
    _write_local_evidence(tmp_path)
    _write_pr_fixture(tmp_path / "pr.json", head="d" * 40)
    _write_ci_fixture(
        tmp_path / "checks.json",
        [{"name": "CI", "state": "completed", "conclusion": "success", "required": True}],
    )
    _patch_clean_git(monkeypatch)

    report = gate.run_remote_pr_ci_gate(
        profile="enterprise",
        branch=gate.DEFAULT_BRANCH,
        base_branch="main",
        output_root=tmp_path / "out",
        release_closure_path=tmp_path / "release" / "closure_report.json",
        pr_readiness_path=tmp_path / "readiness" / "pr_readiness_report.json",
        pr_fixture=tmp_path / "pr.json",
        ci_fixture=tmp_path / "checks.json",
        skip_gh=True,
    )

    assert report.status == "blocked"
    assert "PR_HEAD_SHA_MISMATCH" in report.no_ship_blockers


def test_required_ci_failure_blocks(tmp_path: Path, monkeypatch) -> None:
    _write_local_evidence(tmp_path)
    _write_pr_fixture(tmp_path / "pr.json")
    _write_ci_fixture(
        tmp_path / "checks.json",
        [{"name": "CI", "state": "completed", "conclusion": "failure", "required": True}],
    )
    _patch_clean_git(monkeypatch)

    report = gate.run_remote_pr_ci_gate(
        profile="enterprise",
        branch=gate.DEFAULT_BRANCH,
        base_branch="main",
        output_root=tmp_path / "out",
        release_closure_path=tmp_path / "release" / "closure_report.json",
        pr_readiness_path=tmp_path / "readiness" / "pr_readiness_report.json",
        pr_fixture=tmp_path / "pr.json",
        ci_fixture=tmp_path / "checks.json",
        skip_gh=True,
    )

    assert report.status == "blocked"
    assert "CI_REQUIRED_CHECK_FAILED" in report.no_ship_blockers


def test_ci_collection_filters_checks_to_current_head(tmp_path: Path) -> None:
    _write_ci_fixture(
        tmp_path / "checks.json",
        [
            {
                "name": "old CI",
                "state": "completed",
                "conclusion": "failure",
                "required": True,
                "headSha": "d" * 40,
            },
            {
                "name": "current CI",
                "state": "completed",
                "conclusion": "success",
                "required": True,
                "headSha": HEAD,
            },
        ],
    )

    ci = gate.collect_ci_checks(
        branch=gate.DEFAULT_BRANCH,
        ci_fixture=tmp_path / "checks.json",
        head_sha=HEAD,
        skip_gh=True,
    )

    assert ci.status == "pass"
    assert [check.name for check in ci.checks] == ["current CI"]


def test_required_ci_pending_is_conditional(tmp_path: Path, monkeypatch) -> None:
    _write_local_evidence(tmp_path)
    _write_pr_fixture(tmp_path / "pr.json")
    _write_ci_fixture(
        tmp_path / "checks.json",
        [{"name": "CI", "state": "in_progress", "conclusion": None, "required": True}],
    )
    _patch_clean_git(monkeypatch)

    report = gate.run_remote_pr_ci_gate(
        profile="enterprise",
        branch=gate.DEFAULT_BRANCH,
        base_branch="main",
        output_root=tmp_path / "out",
        release_closure_path=tmp_path / "release" / "closure_report.json",
        pr_readiness_path=tmp_path / "readiness" / "pr_readiness_report.json",
        pr_fixture=tmp_path / "pr.json",
        ci_fixture=tmp_path / "checks.json",
        skip_gh=True,
    )

    assert report.status == "conditional"
    assert "CI_REQUIRED_CHECK_PENDING" in report.no_ship_blockers
    assert report.reconciliation.ready is False


def test_dirty_tree_blocks_remote_gate(tmp_path: Path, monkeypatch) -> None:
    _write_local_evidence(tmp_path)
    _write_pr_fixture(tmp_path / "pr.json")
    _write_ci_fixture(
        tmp_path / "checks.json",
        [{"name": "CI", "state": "completed", "conclusion": "success", "required": True}],
    )
    _patch_clean_git(monkeypatch, dirty=" M scripts/example.py")

    report = gate.run_remote_pr_ci_gate(
        profile="enterprise",
        branch=gate.DEFAULT_BRANCH,
        base_branch="main",
        output_root=tmp_path / "out",
        release_closure_path=tmp_path / "release" / "closure_report.json",
        pr_readiness_path=tmp_path / "readiness" / "pr_readiness_report.json",
        pr_fixture=tmp_path / "pr.json",
        ci_fixture=tmp_path / "checks.json",
        skip_gh=True,
    )

    assert report.status == "blocked"
    assert "DIRTY_WORKTREE" in report.no_ship_blockers


def test_untracked_files_do_not_dirty_remote_gate(tmp_path: Path, monkeypatch) -> None:
    _write_local_evidence(tmp_path)
    _write_pr_fixture(tmp_path / "pr.json")
    _write_ci_fixture(
        tmp_path / "checks.json",
        [{"name": "CI", "state": "completed", "conclusion": "success", "required": True}],
    )

    def fake_git(args: list[str], *, repo_root: Path = gate.REPO_ROOT) -> str:
        if args == ["branch", "--show-current"]:
            return gate.DEFAULT_BRANCH
        if args == ["rev-parse", "HEAD"]:
            return HEAD
        if args == ["rev-parse", "origin/main"]:
            return BASE
        if args == ["status", "--short", "--untracked-files=no"]:
            return ""
        if args == ["status", "--short"]:
            return "?? local-note.txt"
        if args[:2] == ["rev-list", "--left-right"]:
            return "0\t1"
        if args[:3] == ["ls-remote", "--heads", "origin"]:
            return HEAD
        return ""

    monkeypatch.setattr(gate, "_git_text", fake_git)

    report = gate.run_remote_pr_ci_gate(
        profile="enterprise",
        branch=gate.DEFAULT_BRANCH,
        base_branch="main",
        output_root=tmp_path / "out",
        release_closure_path=tmp_path / "release" / "closure_report.json",
        pr_readiness_path=tmp_path / "readiness" / "pr_readiness_report.json",
        pr_fixture=tmp_path / "pr.json",
        ci_fixture=tmp_path / "checks.json",
        skip_gh=True,
    )

    assert report.status == "pass"
    assert "DIRTY_WORKTREE" not in report.no_ship_blockers


def test_exact_approval_allows_remote_decision() -> None:
    blocked = gate.remote_operation_allowed(allow_remote=True, approval_text=None)
    allowed = gate.remote_operation_allowed(
        allow_remote=True,
        approval_text=gate.EXACT_REMOTE_APPROVAL,
    )

    assert blocked.allowed is False
    assert blocked.reason_code == "REMOTE_APPROVAL_MISSING"
    assert allowed.allowed is True
