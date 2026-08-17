from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PlatformDriverReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    platform: str
    live_execution_enabled: bool
    reason_code: str | None = None
    summary: str
