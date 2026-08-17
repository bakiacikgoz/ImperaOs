from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from imperaos.control_plane.enterprise_workspace import StrictModel, _validate_safe_id


class Project(StrictModel):
    project_id: str = Field(alias="projectId")
    workspace_id: str = Field(alias="workspaceId")
    title: str = Field(min_length=1, max_length=160)
    root_ref: str = Field(alias="rootRef")
    root_display_name: str = Field(alias="rootDisplayName", min_length=1, max_length=160)
    status: Literal["active", "archived"] = "active"
    pinned: bool = False
    manual_order: int = Field(default=0, alias="manualOrder", ge=0)
    created_at_utc: datetime = Field(alias="createdAtUtc")
    updated_at_utc: datetime = Field(alias="updatedAtUtc")
    archived_at_utc: datetime | None = Field(default=None, alias="archivedAtUtc")

    @field_validator("project_id", "workspace_id", "root_ref")
    @classmethod
    def _safe(cls, value: str, info: object) -> str:
        return _validate_safe_id(value, str(getattr(info, "field_name", "id")))


class ProjectPage(StrictModel):
    projects: list[Project]
    next_cursor: str | None = Field(default=None, alias="nextCursor")


class TaskRuntimeOptions(StrictModel):
    reasoning_effort: Literal["low", "medium", "high", "very_high"] = Field(
        default="medium", alias="reasoningEffort"
    )
    speed_profile: Literal["standard", "fast"] = Field(default="standard", alias="speedProfile")
    approval_profile: Literal["always_ask", "risk_based", "policy_automatic"] = Field(
        default="risk_based", alias="approvalProfile"
    )


class ProductTask(TaskRuntimeOptions):
    task_id: str = Field(alias="taskId")
    workspace_id: str = Field(alias="workspaceId")
    project_id: str = Field(alias="projectId")
    title: str = Field(min_length=1, max_length=500)
    status: Literal[
        "draft", "active", "awaiting_approval", "completed", "failed", "cancelled", "archived"
    ] = "active"
    priority: int = Field(default=0, ge=0, le=100)
    pinned: bool = False
    manual_order: int = Field(default=0, alias="manualOrder", ge=0)
    assistant_session_id: str | None = Field(default=None, alias="assistantSessionId")
    assistant_turn_id: str | None = Field(default=None, alias="assistantTurnId")
    team_job_id: str | None = Field(default=None, alias="teamJobId")
    created_at_utc: datetime = Field(alias="createdAtUtc")
    updated_at_utc: datetime = Field(alias="updatedAtUtc")
    archived_at_utc: datetime | None = Field(default=None, alias="archivedAtUtc")

    @field_validator(
        "task_id",
        "workspace_id",
        "project_id",
        "assistant_session_id",
        "assistant_turn_id",
        "team_job_id",
    )
    @classmethod
    def _safe(cls, value: str | None, info: object) -> str | None:
        return (
            None
            if value is None
            else _validate_safe_id(value, str(getattr(info, "field_name", "id")))
        )


class ProductMessage(StrictModel):
    message_id: str = Field(alias="messageId")
    workspace_id: str = Field(alias="workspaceId")
    task_id: str = Field(alias="taskId")
    role: Literal["user", "assistant", "system"]
    body: str = Field(min_length=1, max_length=100_000)
    created_at_utc: datetime = Field(alias="createdAtUtc")


class ProductLink(StrictModel):
    link_id: str = Field(alias="linkId")
    workspace_id: str = Field(alias="workspaceId")
    task_id: str = Field(alias="taskId")
    target_type: Literal["artifact", "approval", "team_job", "run"] = Field(alias="targetType")
    target_id: str = Field(alias="targetId")
    created_at_utc: datetime = Field(alias="createdAtUtc")


class Preference(StrictModel):
    workspace_id: str = Field(alias="workspaceId")
    principal_id: str = Field(alias="principalId")
    preference_key: str = Field(alias="preferenceKey", min_length=1, max_length=128)
    value_json: str = Field(alias="valueJson", min_length=1, max_length=100_000)
    updated_at_utc: datetime = Field(alias="updatedAtUtc")
