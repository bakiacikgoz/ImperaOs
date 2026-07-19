from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.field_evidence import build_design_partner_field_pack  # noqa: E402
from imperaos.runtime.config import RuntimeConfig  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate design partner field evidence pack.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--field-root", default="artifacts/design-partner-field-evidence")
    parser.add_argument("--rc-root", default="artifacts/design-partner-rc")
    parser.add_argument("--output-root", default="artifacts/design-partner-field-pack")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    manifest = build_design_partner_field_pack(
        field_root=REPO_ROOT / args.field_root,
        rc_root=REPO_ROOT / args.rc_root,
        output_root=REPO_ROOT / args.output_root,
        config=RuntimeConfig.from_profile(args.profile),
    )
    payload = manifest.model_dump(mode="json", by_alias=True)
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(manifest.status)
    if manifest.status == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
