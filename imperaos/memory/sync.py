from __future__ import annotations


def sync_status() -> dict[str, object]:
    return {
        "status": "deferred",
        "reason": "distributed memory sync is outside governed memory v1 scope",
    }
