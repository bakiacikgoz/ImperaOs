from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from imperaos.team.models import HandoffRule, TeamSpec

_REPO_ROOT = Path(__file__).resolve().parents[2]


def validate_team_spec(
    spec: TeamSpec,
    *,
    active_policy_profile: str | None = None,
) -> list[str]:
    errors: list[str] = []
    roles = {agent.role.strip().lower() for agent in spec.team.agents}

    seen_task_ids: set[str] = set()
    tasks_by_id = {}
    for task in spec.tasks:
        normalized_role = task.role.strip().lower()
        if normalized_role not in roles:
            errors.append(f"task '{task.task_id}' references undefined role '{task.role}'")
        if task.task_id in seen_task_ids:
            errors.append(f"duplicate task id '{task.task_id}'")
        seen_task_ids.add(task.task_id)
        tasks_by_id[task.task_id] = task

    for task in spec.tasks:
        for dep_id in task.depends_on:
            if dep_id not in tasks_by_id:
                errors.append(f"task '{task.task_id}' depends on unknown task '{dep_id}'")

    graph = {task.task_id: list(task.depends_on) for task in spec.tasks}
    if _has_cycle(graph):
        errors.append("team task graph contains a dependency cycle")

    max_depth = _graph_depth(graph)
    if max_depth > spec.team.termination_rules.max_handoff_depth:
        errors.append(
            "team task graph depth exceeds termination_rules.max_handoff_depth "
            f"({max_depth} > {spec.team.termination_rules.max_handoff_depth})"
        )

    if spec.team.handoff_rules:
        for task in spec.tasks:
            for dep_id in task.depends_on:
                dep_task = tasks_by_id.get(dep_id)
                if dep_task is None:
                    continue
                if not _handoff_allowed(spec.team.handoff_rules, dep_task.role, task.role):
                    errors.append(
                        "dependency edge "
                        f"'{dep_task.task_id}:{dep_task.role} -> {task.task_id}:{task.role}' "
                        "is not covered by team.handoff_rules"
                    )

    for agent in spec.team.agents:
        if not agent.memory_scope_access:
            errors.append(f"agent '{agent.agent_id}' must declare at least one memory scope")
        requested_profile = (agent.tool_policy_profile or "").strip().lower()
        if not requested_profile:
            continue
        policy_path = _REPO_ROOT / "config" / "policies" / f"{requested_profile}.toml"
        if requested_profile != "default" and not policy_path.exists():
            errors.append(
                "agent "
                f"'{agent.agent_id}' references unknown tool_policy_profile "
                f"'{requested_profile}'"
            )
            continue
        if (
            active_policy_profile is not None
            and requested_profile not in {"", "default", active_policy_profile}
        ):
            errors.append(
                f"agent '{agent.agent_id}' requires tool_policy_profile '{requested_profile}' "
                f"but active runtime policy profile is '{active_policy_profile}'"
            )

    return errors


def _handoff_allowed(rules: list[HandoffRule], from_role: str, to_role: str) -> bool:
    from_norm = from_role.strip().lower()
    to_norm = to_role.strip().lower()
    for rule in rules:
        rule_from = rule.from_role.strip().lower()
        rule_to = rule.to_role.strip().lower()
        if rule_from and from_norm != rule_from:
            continue
        if rule_to and to_norm != rule_to:
            continue
        return bool(rule.required)
    return False


def _has_cycle(graph: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for dep in graph.get(node, []):
            if dep in graph and visit(dep):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def _graph_depth(graph: dict[str, list[str]]) -> int:
    memo: dict[str, int] = defaultdict(int)

    def depth(node: str) -> int:
        if node in memo:
            return memo[node]
        deps = graph.get(node, [])
        if not deps:
            memo[node] = 1
            return 1
        child_depths = [depth(dep) for dep in deps if dep in graph]
        value = 1 + (max(child_depths) if child_depths else 0)
        memo[node] = value
        return value

    if not graph:
        return 0
    return max(depth(node) for node in graph)
