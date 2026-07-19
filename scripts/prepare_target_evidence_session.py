from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.target_evidence import prepare_target_evidence_session  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a target evidence session manifest.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--mode", choices=["rehearsal", "target"], default="rehearsal")
    parser.add_argument("--environment-label", required=True)
    parser.add_argument("--operator-id")
    parser.add_argument("--output-root", default="artifacts/design-partner-target-evidence")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    output_root = _resolve(args.output_root)
    session = prepare_target_evidence_session(
        profile=args.profile,
        mode=args.mode,
        environment_label=args.environment_label,
        output_root=output_root,
        operator_id=args.operator_id,
    )
    payload = {
        **session.model_dump(mode="json", by_alias=True),
        "status": "pass",
        "sessionPath": str(output_root / "session.json"),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"wrote {output_root / 'session.json'}")


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


if __name__ == "__main__":
    main()
