from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.mainline_stack import (
    MergeRehearsalSpec,
    StackGraphSpec,
    StackPrRef,
    run_merge_rehearsal,
    verify_stack_graph,
)


def test_stack_graph_verifier_accepts_ordered_local_stack() -> None:
    spec = StackGraphSpec(
        stackName="design-partner-rc",
        baseBranch="main",
        items=[
            StackPrRef(
                prNumber=10,
                branch="codex/workspace-memory-authority-v1",
                baseBranch="main",
            ),
            StackPrRef(
                prNumber=11,
                branch="codex/semantic-memory-index-retrieval-quality-v1",
                baseBranch="codex/workspace-memory-authority-v1",
            ),
        ],
    )

    report = verify_stack_graph(spec, branch_exists=lambda branch: True)

    assert report.status == "ready"
    assert report.stack_order == [
        "codex/workspace-memory-authority-v1",
        "codex/semantic-memory-index-retrieval-quality-v1",
    ]
    assert report.blockers == []


def test_stack_graph_verifier_blocks_base_mismatch() -> None:
    spec = StackGraphSpec(
        stackName="design-partner-rc",
        baseBranch="main",
        items=[
            StackPrRef(
                prNumber=10,
                branch="codex/workspace-memory-authority-v1",
                baseBranch="wrong-base",
            )
        ],
    )

    report = verify_stack_graph(spec, branch_exists=lambda branch: True)

    assert report.status == "blocked"
    assert "STACK_BASE_MISMATCH:codex/workspace-memory-authority-v1" in report.blockers


def test_stack_graph_verifier_blocks_duplicate_pr_and_missing_branch() -> None:
    spec = StackGraphSpec(
        stackName="design-partner-rc",
        baseBranch="main",
        items=[
            StackPrRef(prNumber=10, branch="codex/a", baseBranch="main"),
            StackPrRef(prNumber=10, branch="codex/b", baseBranch="codex/a"),
            StackPrRef(prNumber=12, branch="codex/missing", baseBranch="codex/b"),
        ],
    )

    report = verify_stack_graph(spec, branch_exists=lambda branch: branch != "codex/missing")

    assert report.status == "blocked"
    assert "DUPLICATE_PR:10" in report.blockers
    assert "STACK_BRANCH_MISSING:codex/missing" in report.blockers


def test_merge_rehearsal_dry_run_does_not_require_worktree_mutation(tmp_path: Path) -> None:
    spec = MergeRehearsalSpec(
        baseRef="main",
        headRef="codex/design-partner-rc-handoff-ops-readiness-v1",
        mode="dry-run",
        outputRoot=str(tmp_path / "artifacts" / "mainline-rc-freeze"),
    )

    report = run_merge_rehearsal(
        spec,
        git_runner=lambda args: "34f44bf" if args[:1] == ["rev-parse"] else "",
    )

    assert report.status == "pass"
    assert report.base_ref == "main"
    assert report.head_ref == "codex/design-partner-rc-handoff-ops-readiness-v1"
    assert report.worktree_mutated is False
    assert report.mode == "dry-run"


def test_merge_rehearsal_resolves_origin_head_fallback(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def git_runner(args: list[str]) -> str:
        calls.append(args)
        if args == ["rev-parse", "main"]:
            return "base-sha"
        if args == ["rev-parse", "codex/head"]:
            raise RuntimeError("missing local branch")
        if args == ["rev-parse", "origin/codex/head"]:
            return "head-sha"
        if args[:1] == ["diff"]:
            return "file.txt\n"
        return ""

    report = run_merge_rehearsal(
        MergeRehearsalSpec(
            baseRef="main",
            headRef="codex/head",
            outputRoot=str(tmp_path / "artifacts" / "mainline-rc-freeze"),
        ),
        git_runner=git_runner,
    )

    assert report.status == "pass"
    assert report.head_sha == "head-sha"
    assert ["diff", "--name-only", "main", "origin/codex/head"] in calls
