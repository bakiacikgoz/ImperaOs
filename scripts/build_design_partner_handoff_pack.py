from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.design_partner_handoff import (  # noqa: E402
    build_design_partner_handoff_pack,
    verify_design_partner_handoff_pack,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build design partner handoff pack.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--environment-label", default="design-partner-rc-local")
    parser.add_argument("--artifact-root", default="artifacts")
    parser.add_argument("--output-root", default="artifacts/design-partner-handoff")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    manifest = build_design_partner_handoff_pack(
        profile=args.profile,
        environment_label=args.environment_label,
        artifact_root=Path(args.artifact_root),
        output_root=Path(args.output_root),
    )
    if args.verify:
        verification = verify_design_partner_handoff_pack(
            manifest_path=Path(args.output_root) / "manifest.json"
        )
        payload = verification.model_dump(mode="json", by_alias=True)
        status = verification.status
    else:
        payload = manifest.model_dump(mode="json", by_alias=True)
        status = manifest.status
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(status)
    if status == "blocked":
        raise SystemExit(4)
    if status == "conditional":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
