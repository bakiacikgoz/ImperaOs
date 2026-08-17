from __future__ import annotations

import hashlib
import json
import re
import tomllib
import unicodedata
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from imperaos.governance.models import GovernanceAction


class TaskRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task_types: list[str] = Field(default_factory=list)
    action: GovernanceAction
    explain: str | None = None


class ToolRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    command_roots: list[str] = Field(default_factory=list)
    action: GovernanceAction
    arg_deny_regex: list[str] = Field(default_factory=list)
    explain: str | None = None


class ApprovalRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task_types: list[str] = Field(default_factory=list)
    command_roots: list[str] = Field(default_factory=list)
    explain: str | None = None


class HandoffRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    from_roles: list[str] = Field(default_factory=list)
    to_roles: list[str] = Field(default_factory=list)
    action: GovernanceAction
    explain: str | None = None


class MemoryScopeRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    scopes: list[str] = Field(default_factory=list)
    producer_roles: list[str] = Field(default_factory=list)
    visibilities: list[str] = Field(default_factory=list)
    action: GovernanceAction
    explain: str | None = None


class PIIRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patterns: list[str] = Field(default_factory=list)


class PolicyFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_schema_version: str
    policy_version: str
    web_egress: GovernanceAction = GovernanceAction.DENY
    task_rules: list[TaskRule] = Field(default_factory=list)
    tool_rules: list[ToolRule] = Field(default_factory=list)
    pii_rules: PIIRule = Field(default_factory=PIIRule)
    approval_rules: list[ApprovalRule] = Field(default_factory=list)
    handoff_rules: list[HandoffRule] = Field(default_factory=list)
    memory_scope_rules: list[MemoryScopeRule] = Field(default_factory=list)


class PolicyMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: GovernanceAction
    matched_rule_path: str | None
    explain: str | None
    reason_code: str


class PolicyBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    policy: PolicyFile
    policy_hash: str


def load_policy(path: str | Path) -> PolicyBundle:
    policy_path = Path(path)
    if not policy_path.exists() and not policy_path.is_absolute():
        policy_path = Path(__file__).resolve().parents[2] / policy_path
    with policy_path.open("rb") as file_obj:
        if policy_path.suffix.lower() == ".json":
            raw_data = json.load(file_obj)
        else:
            raw_data = tomllib.load(file_obj)

    policy = PolicyFile.model_validate(raw_data)
    canonical = canonical_policy_json(policy.model_dump(mode="json"))
    policy_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return PolicyBundle(path=str(policy_path), policy=policy, policy_hash=policy_hash)


def canonical_policy_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def normalize_command(command: list[str], workdir: str | Path = ".") -> tuple[str, list[str]]:
    root = ""
    if command:
        root = unicodedata.normalize("NFKC", command[0]).strip().lower()
    normalized_args: list[str] = []
    root_dir = Path(workdir).resolve()
    for raw in command[1:]:
        arg = unicodedata.normalize("NFKC", str(raw)).strip()
        if _looks_like_path(arg):
            normalized_args.append(_normalize_path_argument(arg, root_dir))
        else:
            normalized_args.append(arg)
    return root, normalized_args


def _looks_like_path(value: str) -> bool:
    return any(ch in value for ch in ("/", "\\", ".", "~"))


def _normalize_path_argument(value: str, root_dir: Path) -> str:
    expanded = Path(value).expanduser()
    resolved = expanded.resolve() if expanded.is_absolute() else (root_dir / expanded).resolve()
    try:
        rel = resolved.relative_to(root_dir)
        return f"./{rel.as_posix()}"
    except ValueError:
        return resolved.as_posix()


def evaluate_task(policy: PolicyFile, *, task_type: str) -> PolicyMatch:
    for idx, rule in enumerate(policy.task_rules):
        if task_type not in rule.task_types:
            continue
        return PolicyMatch(
            action=rule.action,
            matched_rule_path=f"task_rules[{idx}]",
            explain=rule.explain,
            reason_code=_reason_for_action(rule.action),
        )
    return PolicyMatch(
        action=GovernanceAction.ALLOW,
        matched_rule_path=None,
        explain="default allow",
        reason_code=_reason_for_action(GovernanceAction.ALLOW),
    )


def evaluate_tool(policy: PolicyFile, *, command_root: str, args: list[str]) -> PolicyMatch:
    args_blob = " ".join(args)
    for idx, rule in enumerate(policy.tool_rules):
        if command_root not in [item.lower() for item in rule.command_roots]:
            continue
        for pattern in rule.arg_deny_regex:
            if re.search(pattern, args_blob, flags=re.IGNORECASE):
                return PolicyMatch(
                    action=GovernanceAction.DENY,
                    matched_rule_path=f"tool_rules[{idx}].arg_deny_regex",
                    explain=rule.explain or f"arg matched deny regex: {pattern}",
                    reason_code="POLICY_DENY",
                )
        return PolicyMatch(
            action=rule.action,
            matched_rule_path=f"tool_rules[{idx}]",
            explain=rule.explain,
            reason_code=_reason_for_action(rule.action),
        )

    return PolicyMatch(
        action=GovernanceAction.ALLOW,
        matched_rule_path=None,
        explain="default allow",
        reason_code=_reason_for_action(GovernanceAction.ALLOW),
    )


def evaluate_handoff(
    policy: PolicyFile,
    *,
    from_role: str,
    to_role: str,
) -> PolicyMatch:
    from_norm = from_role.strip().lower()
    to_norm = to_role.strip().lower()

    for idx, rule in enumerate(policy.handoff_rules):
        from_candidates = [item.strip().lower() for item in rule.from_roles]
        to_candidates = [item.strip().lower() for item in rule.to_roles]
        if from_candidates and from_norm not in from_candidates:
            continue
        if to_candidates and to_norm not in to_candidates:
            continue
        if rule.action == GovernanceAction.DENY:
            reason_code = "HANDOFF_DENY"
        elif rule.action == GovernanceAction.REQUIRE_APPROVAL:
            reason_code = "POLICY_REQUIRE_APPROVAL"
        else:
            reason_code = "RULE_ROUTE"
        return PolicyMatch(
            action=rule.action,
            matched_rule_path=f"handoff_rules[{idx}]",
            explain=rule.explain,
            reason_code=reason_code,
        )

    return PolicyMatch(
        action=GovernanceAction.DENY,
        matched_rule_path=None,
        explain="default deny for handoff",
        reason_code="HANDOFF_DENY",
    )


def evaluate_memory_scope_write(
    policy: PolicyFile,
    *,
    scope: str,
    producer_role: str,
    visibility: str,
) -> PolicyMatch:
    scope_norm = scope.strip().lower()
    role_norm = producer_role.strip().lower()
    visibility_norm = visibility.strip().lower()

    for idx, rule in enumerate(policy.memory_scope_rules):
        scope_candidates = [item.strip().lower() for item in rule.scopes]
        role_candidates = [item.strip().lower() for item in rule.producer_roles]
        visibility_candidates = [item.strip().lower() for item in rule.visibilities]
        if scope_candidates and scope_norm not in scope_candidates:
            continue
        if role_candidates and role_norm not in role_candidates:
            continue
        if visibility_candidates and visibility_norm not in visibility_candidates:
            continue
        if rule.action == GovernanceAction.DENY:
            reason_code = "MEMORY_SCOPE_DENY"
        elif rule.action == GovernanceAction.REQUIRE_APPROVAL:
            reason_code = "POLICY_REQUIRE_APPROVAL"
        else:
            reason_code = "RULE_ROUTE"
        return PolicyMatch(
            action=rule.action,
            matched_rule_path=f"memory_scope_rules[{idx}]",
            explain=rule.explain,
            reason_code=reason_code,
        )

    return PolicyMatch(
        action=GovernanceAction.DENY,
        matched_rule_path=None,
        explain="default deny for memory scope writes",
        reason_code="MEMORY_SCOPE_DENY",
    )


def _reason_for_action(action: GovernanceAction) -> str:
    if action == GovernanceAction.DENY:
        return "POLICY_DENY"
    if action == GovernanceAction.REQUIRE_APPROVAL:
        return "POLICY_REQUIRE_APPROVAL"
    return "RULE_ROUTE"
