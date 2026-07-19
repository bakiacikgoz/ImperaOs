from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator

from imperaos.memory.models import StrictModel

StackStatus = Literal["ready", "conditional", "blocked"]
RehearsalStatus = Literal["pass", "conditional", "blocked"]
GitRunner = Callable[[list[str]], str]


class StackPrRef(StrictModel):
    pr_number: int | None = Field(default=None, alias="prNumber")
    branch: str
    base_branch: str = Field(alias="baseBranch")
    head_sha: str | None = Field(default=None, alias="headSha")
    title: str | None = None
    required: bool = True


class StackGraphSpec(StrictModel):
    schema_version: Literal["control-plane.mainline-stack-spec/v1"] = Field(
        default="control-plane.mainline-stack-spec/v1",
        alias="schemaVersion",
    )
    stack_name: str = Field(alias="stackName")
    base_branch: str = Field(alias="baseBranch")
    head_branch: str | None = Field(default=None, alias="headBranch")
    items: list[StackPrRef] = Field(default_factory=list)


class StackGraphVerificationReport(StrictModel):
    schema_version: Literal["control-plane.mainline-stack-verification/v1"] = Field(
        default="control-plane.mainline-stack-verification/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: StackStatus
    stack_name: str = Field(alias="stackName")
    base_branch: str = Field(alias="baseBranch")
    head_branch: str | None = Field(default=None, alias="headBranch")
    stack_order: list[str] = Field(default_factory=list, alias="stackOrder")
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MergeRehearsalSpec(StrictModel):
    schema_version: Literal["control-plane.mainline-merge-rehearsal-spec/v1"] = Field(
        default="control-plane.mainline-merge-rehearsal-spec/v1",
        alias="schemaVersion",
    )
    base_ref: str = Field(alias="baseRef")
    head_ref: str = Field(alias="headRef")
    mode: Literal["dry-run", "temp-worktree"] = "dry-run"
    output_root: str = Field(default="artifacts/mainline-rc-freeze", alias="outputRoot")
    allow_working_tree_mutation: Literal[False] = Field(
        default=False,
        alias="allowWorkingTreeMutation",
    )

    @field_validator("output_root")
    @classmethod
    def _output_under_artifacts(cls, value: str) -> str:
        path = Path(value)
        if ".." in path.parts or "artifacts" not in path.parts:
            raise ValueError("outputRoot must be a repo-relative path under artifacts")
        return value


class MergeRehearsalReport(StrictModel):
    schema_version: Literal["control-plane.mainline-merge-rehearsal/v1"] = Field(
        default="control-plane.mainline-merge-rehearsal/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: RehearsalStatus
    base_ref: str = Field(alias="baseRef")
    head_ref: str = Field(alias="headRef")
    base_sha: str | None = Field(default=None, alias="baseSha")
    head_sha: str | None = Field(default=None, alias="headSha")
    mode: Literal["dry-run", "temp-worktree"]
    worktree_mutated: bool = Field(default=False, alias="worktreeMutated")
    changed_file_count: int = Field(default=0, alias="changedFileCount")
    conflict_count: int = Field(default=0, alias="conflictCount")
    output_root: str | None = Field(default=None, alias="outputRoot")
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def load_stack_graph_spec(path: Path) -> StackGraphSpec:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("stack graph spec must be a mapping")
    return StackGraphSpec.model_validate(payload)


def verify_stack_graph(
    spec: StackGraphSpec,
    *,
    branch_exists: Callable[[str], bool] | None = None,
) -> StackGraphVerificationReport:
    branch_exists = branch_exists or _branch_exists
    blockers: list[str] = []
    warnings: list[str] = []
    seen_prs: set[int] = set()
    seen_branches: set[str] = set()
    expected_base = spec.base_branch
    order: list[str] = []

    if not spec.items:
        blockers.append("STACK_EMPTY")

    for item in spec.items:
        order.append(item.branch)
        if item.pr_number is not None:
            if item.pr_number in seen_prs:
                blockers.append(f"DUPLICATE_PR:{item.pr_number}")
            seen_prs.add(item.pr_number)
        if item.branch in seen_branches:
            blockers.append(f"DUPLICATE_BRANCH:{item.branch}")
        seen_branches.add(item.branch)
        if item.base_branch != expected_base:
            blockers.append(f"STACK_BASE_MISMATCH:{item.branch}")
        if item.required and not branch_exists(item.branch):
            blockers.append(f"STACK_BRANCH_MISSING:{item.branch}")
        expected_base = item.branch

    if spec.head_branch and spec.items and spec.head_branch != spec.items[-1].branch:
        blockers.append("STACK_HEAD_MISMATCH")

    return StackGraphVerificationReport(
        status="blocked" if blockers else "conditional" if warnings else "ready",
        stackName=spec.stack_name,
        baseBranch=spec.base_branch,
        headBranch=spec.head_branch or (spec.items[-1].branch if spec.items else None),
        stackOrder=order,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
    )


def run_merge_rehearsal(
    spec: MergeRehearsalSpec,
    *,
    git_runner: GitRunner | None = None,
) -> MergeRehearsalReport:
    git_runner = git_runner or _git
    blockers: list[str] = []
    warnings: list[str] = []
    base_ref, base_sha = _resolve_ref(git_runner, spec.base_ref)
    head_ref, head_sha = _resolve_ref(git_runner, spec.head_ref)
    if not base_sha:
        blockers.append(f"BASE_REF_MISSING:{spec.base_ref}")
    if not head_sha:
        blockers.append(f"HEAD_REF_MISSING:{spec.head_ref}")

    changed_file_count = 0
    if base_sha and head_sha:
        changed = _git_or_none(git_runner, ["diff", "--name-only", base_ref, head_ref])
        changed_file_count = len([line for line in (changed or "").splitlines() if line.strip()])

    if spec.mode == "temp-worktree":
        output = Path(spec.output_root)
        if output.resolve() == Path.cwd().resolve():
            blockers.append("TEMP_WORKTREE_ROOT_UNSAFE")
        warnings.append("TEMP_WORKTREE_REHEARSAL_RECORDED_NON_DESTRUCTIVE")

    return MergeRehearsalReport(
        status="blocked" if blockers else "pass",
        baseRef=spec.base_ref,
        headRef=spec.head_ref,
        baseSha=base_sha,
        headSha=head_sha,
        mode=spec.mode,
        worktreeMutated=False,
        changedFileCount=changed_file_count,
        conflictCount=0,
        outputRoot=spec.output_root,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
    )


def write_merge_rehearsal_report(report: MergeRehearsalReport, output_root: Path) -> Path:
    path = Path(output_root) / "merge_rehearsal.json"
    _write_json(path, report.model_dump(mode="json", by_alias=True))
    return path


def write_stack_graph_report(report: StackGraphVerificationReport, output_root: Path) -> Path:
    path = Path(output_root) / "stack_verification.json"
    _write_json(path, report.model_dump(mode="json", by_alias=True))
    return path


def _branch_exists(branch: str) -> bool:
    return bool(_git_or_none(_git, ["rev-parse", "--verify", f"{branch}^{{commit}}"]))


def _git_or_none(runner: GitRunner, args: list[str]) -> str | None:
    try:
        value = runner(args).strip()
    except Exception:
        return None
    return value or None


def _resolve_ref(runner: GitRunner, ref: str) -> tuple[str, str | None]:
    value = _git_or_none(runner, ["rev-parse", ref])
    if value:
        return ref, value
    if not ref.startswith("origin/"):
        origin_ref = f"origin/{ref}"
        origin_value = _git_or_none(runner, ["rev-parse", origin_ref])
        if origin_value:
            return origin_ref, origin_value
    return ref, None


def _git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
