from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from imperaos.runtime.paths import ROUTER_DATASET_PATH, TRACE_STATE_ROOT
from imperaos.schemas.models import TraceEvent


class Tracer:
    """Collects in-memory events and optionally persists JSONL traces."""

    def __init__(
        self,
        debug_mode: bool = False,
        privacy_mode: bool = True,
        trace_dir: str = TRACE_STATE_ROOT,
        router_dataset_path: str = ROUTER_DATASET_PATH,
        event_redactor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ):
        self._events: list[TraceEvent] = []
        self._privacy_mode = privacy_mode
        self._event_redactor = event_redactor
        self._persist_to_disk = debug_mode and not privacy_mode
        self._trace_dir = Path(trace_dir)
        self._router_dataset_path = Path(router_dataset_path)
        if self._persist_to_disk:
            self._trace_dir.mkdir(parents=True, exist_ok=True)
            self._router_dataset_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, request_id: str, stage: str, data: dict[str, Any] | None = None) -> TraceEvent:
        payload = data or {}
        if self._privacy_mode and self._event_redactor is not None:
            payload = self._event_redactor(payload)
        event = TraceEvent(request_id=request_id, stage=stage, data=payload)
        self._events.append(event)

        if self._persist_to_disk:
            path = self._trace_dir / f"{request_id}.jsonl"
            with path.open("a", encoding="utf-8") as file_obj:
                file_obj.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")

        return event

    def emit_router_sample(self, sample: dict[str, Any]) -> None:
        if not self._persist_to_disk:
            return
        self._router_dataset_path.parent.mkdir(parents=True, exist_ok=True)
        with self._router_dataset_path.open("a", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps(sample, ensure_ascii=False) + "\n")

    def events_for(self, request_id: str) -> list[TraceEvent]:
        return [event for event in self._events if event.request_id == request_id]

    def all_events(self) -> list[TraceEvent]:
        return list(self._events)
