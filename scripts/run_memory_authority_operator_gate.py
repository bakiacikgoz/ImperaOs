from __future__ import annotations

import json

from imperaos.control_plane.snapshot import build_control_plane_snapshot


def main() -> None:
    snapshot = build_control_plane_snapshot(profile="balanced")
    payload = snapshot.model_dump(mode="json", by_alias=True)
    authority = payload.get("memoryAuthority", {})
    status = (
        "pass"
        if authority.get("rawContentExposed") is False
        and authority.get("networkListenerEnabled") is False
        and authority.get("status") in {"disabled", "available", "setup_required", "blocked"}
        else "fail"
    )
    print(
        json.dumps(
            {
                "status": status,
                "memoryAuthority": authority,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
