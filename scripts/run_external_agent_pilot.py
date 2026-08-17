from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.external_agent_client import run_external_agent_pilot_suite
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Run external agent pilot examples.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--examples-root", default="examples/external_agents")
    parser.add_argument(
        "--root-dir",
        default="artifacts/design-partner-pilot/external-agent/control-plane",
    )
    parser.add_argument(
        "--output",
        default="artifacts/design-partner-pilot/external-agent-pilot-report.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    config = RuntimeConfig.from_profile(args.profile)
    config.governance.approval_store_path = str(REPO_ROOT / args.root_dir / "approvals.sqlite3")
    report = run_external_agent_pilot_suite(
        examples_root=REPO_ROOT / args.examples_root,
        output_path=REPO_ROOT / args.output,
        config=config,
        root_dir=REPO_ROOT / args.root_dir,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(report["status"])
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
