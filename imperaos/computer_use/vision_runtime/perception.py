from __future__ import annotations

import hashlib


def hash_screenshot_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
