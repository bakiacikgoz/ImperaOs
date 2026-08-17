from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.claim_guard import ClaimGuard  # noqa: E402
from imperaos.runtime.config import RuntimeConfig  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Agent Control Plane claim matrix.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--evidence-root", default="artifacts")
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    matrix = ClaimGuard(config=RuntimeConfig.from_profile(args.profile)).evaluate(
        evidence_root=args.evidence_root
    )
    payload = matrix.model_dump(mode="json")
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
    if args.json or not args.output:
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
