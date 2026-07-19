from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass

from imperaos.team.models import TaskDefinition, TaskRun, TaskStatus

TaskExecutor = Callable[[TaskDefinition], TaskRun]


@dataclass(slots=True)
class SchedulerResult:
    tasks: list[TaskRun]
    reason_code: str | None = None


class ParallelScheduler:
    def __init__(
        self,
        *,
        max_parallel_tasks: int,
        max_total_tasks: int,
    ):
        self._max_parallel_tasks = max(1, int(max_parallel_tasks))
        self._max_total_tasks = max(1, int(max_total_tasks))

    def run(
        self,
        *,
        tasks: list[TaskDefinition],
        execute_task: TaskExecutor,
        initially_completed: set[str] | None = None,
    ) -> SchedulerResult:
        if len(tasks) > self._max_total_tasks:
            blocked = [
                TaskRun(
                    task_id=item.task_id,
                    assigned_agent_id="unassigned",
                    role=item.role,
                    input_payload={},
                    status=TaskStatus.BLOCKED,
                    reason_code="TEAM_BUDGET_EXCEEDED",
                )
                for item in tasks
            ]
            return SchedulerResult(tasks=blocked, reason_code="TEAM_BUDGET_EXCEEDED")

        by_id = {item.task_id: item for item in tasks}
        if len(by_id) != len(tasks):
            dup_ids = _duplicate_ids([item.task_id for item in tasks])
            blocked = [
                TaskRun(
                    task_id=item.task_id,
                    assigned_agent_id="unassigned",
                    role=item.role,
                    input_payload={},
                    status=TaskStatus.BLOCKED,
                    reason_code=f"TASK_ID_DUPLICATE:{dup_ids[0]}",
                )
                for item in tasks
            ]
            return SchedulerResult(tasks=blocked, reason_code="TEAM_DEADLOCK")

        pending = set(by_id.keys())
        completed: set[str] = set(initially_completed or set())
        done_or_failed: set[str] = set()
        task_runs: dict[str, TaskRun] = {}
        running: dict[Future[TaskRun], str] = {}

        with ThreadPoolExecutor(max_workers=self._max_parallel_tasks) as pool:
            while pending or running:
                runnable = sorted(
                    tid
                    for tid in pending
                    if all(dep in completed for dep in by_id[tid].depends_on)
                )

                while runnable and len(running) < self._max_parallel_tasks:
                    tid = runnable.pop(0)
                    pending.remove(tid)
                    future = pool.submit(execute_task, by_id[tid])
                    running[future] = tid

                if not running:
                    # Remaining tasks have unsatisfied dependencies.
                    # This is deadlock or failed dependencies.
                    for tid in sorted(pending):
                        task_def = by_id[tid]
                        task_runs[tid] = TaskRun(
                            task_id=task_def.task_id,
                            assigned_agent_id="unassigned",
                            role=task_def.role,
                            input_payload={},
                            status=TaskStatus.BLOCKED,
                            reason_code="TEAM_DEADLOCK",
                        )
                    return SchedulerResult(
                        tasks=[task_runs[item.task_id] for item in tasks],
                        reason_code="TEAM_DEADLOCK",
                    )

                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for fut in done:
                    tid = running.pop(fut)
                    try:
                        run = fut.result()
                    except Exception as exc:  # noqa: BLE001
                        task_def = by_id[tid]
                        run = TaskRun(
                            task_id=task_def.task_id,
                            assigned_agent_id="unassigned",
                            role=task_def.role,
                            input_payload={},
                            status=TaskStatus.FAILED,
                            reason_code=f"TASK_EXEC_EXCEPTION:{type(exc).__name__}",
                        )

                    task_runs[tid] = run
                    done_or_failed.add(tid)
                    if run.status == TaskStatus.COMPLETED:
                        completed.add(tid)

        # Mark tasks that were never executed because dependencies failed.
        for task_def in tasks:
            if task_def.task_id in task_runs:
                continue
            task_runs[task_def.task_id] = TaskRun(
                task_id=task_def.task_id,
                assigned_agent_id="unassigned",
                role=task_def.role,
                input_payload={},
                status=TaskStatus.BLOCKED,
                reason_code="TASK_ESCALATED",
            )

        reason_code = None
        if any(
            task.status in {TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.ESCALATED}
            for task in task_runs.values()
        ):
            reason_code = "TASK_ESCALATED"

        ordered = [task_runs[item.task_id] for item in tasks]
        return SchedulerResult(tasks=ordered, reason_code=reason_code)


def _duplicate_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    dup: list[str] = []
    for item in values:
        if item in seen and item not in dup:
            dup.append(item)
        seen.add(item)
    return dup
