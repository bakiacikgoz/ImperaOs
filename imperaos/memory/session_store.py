from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import time


@dataclass(slots=True)
class SessionMemoryItem:
    role: str
    content: str
    ts: float


class SessionStore:
    """Ephemeral session memory. No disk persistence by design."""

    def __init__(self, max_items: int = 200):
        self._items: deque[SessionMemoryItem] = deque(maxlen=max_items)

    def add(self, role: str, content: str) -> None:
        self._items.append(SessionMemoryItem(role=role, content=content, ts=time()))

    def last(self, n: int = 8) -> list[SessionMemoryItem]:
        if n <= 0:
            return []
        return list(self._items)[-n:]

    def summary_text(self, n: int = 8) -> str:
        snippets = [f"{item.role}: {item.content}" for item in self.last(n)]
        return "\n".join(snippets)
