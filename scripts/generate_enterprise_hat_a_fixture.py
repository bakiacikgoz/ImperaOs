from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.qualification_closure import write_pilot_qualification_fixture
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic signed qualification evidence for Hat A closure."
    )
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument(
        "--output-root",
        default="artifacts/enterprise-hat-a/qualification",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report_path = write_pilot_qualification_fixture(
        output_root=REPO_ROOT / args.output_root,
        config=RuntimeConfig.from_profile(args.profile),
    )
    payload = {
        "version": "control-plane.enterprise-hat-a-fixture/v1",
        "status": "pass",
        "qualificationReportPath": str(report_path.relative_to(REPO_ROOT)),
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(payload["qualificationReportPath"])


if __name__ == "__main__":
    main()
