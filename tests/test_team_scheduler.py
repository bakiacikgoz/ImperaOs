from __future__ import annotations

from imperaos.team.models import TaskDefinition, TaskRun, TaskStatus
from imperaos.team.scheduler import ParallelScheduler


def test_parallel_scheduler_detects_deadlock() -> None:
    tasks = [
        TaskDefinition(
            task_id="a",
            title="A",
            task_type="chat",
            role="Intake Agent",
            depends_on=["b"],
        ),
        TaskDefinition(
            task_id="b",
            title="B",
            task_type="chat",
            role="Intake Agent",
            depends_on=["a"],
        ),
    ]
    scheduler = ParallelScheduler(max_parallel_tasks=2, max_total_tasks=10)

    def execute_task(task: TaskDefinition) -> TaskRun:
        return TaskRun(
            task_id=task.task_id,
            assigned_agent_id="agent-1",
            role=task.role,
            input_payload={},
            status=TaskStatus.COMPLETED,
        )

    result = scheduler.run(tasks=tasks, execute_task=execute_task)

    assert result.reason_code == "TEAM_DEADLOCK"
    assert all(item.status == TaskStatus.BLOCKED for item in result.tasks)
