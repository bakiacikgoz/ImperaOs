from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.pilot_ops_drill import run_pilot_ops_drill  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run design partner pilot ops drill.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--mode", default="deterministic")
    parser.add_argument("--output-root", default="artifacts/design-partner-handoff")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    report = run_pilot_ops_drill(
        profile=args.profile,
        mode=args.mode,
        output_root=Path(args.output_root),
    )
    payload = report.model_dump(mode="json", by_alias=True)
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(report.status)
    if report.status == "blocked":
        raise SystemExit(4)
    if report.status == "conditional":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
