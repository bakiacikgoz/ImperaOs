from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.pilot_candidate_pack import (  # noqa: E402
    generate_design_partner_pilot_candidate_pack,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Design Partner Pilot Candidate pack.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument(
        "--target-evidence-root",
        default="artifacts/design-partner-target-evidence",
    )
    parser.add_argument("--rc-root", default="artifacts/design-partner-rc")
    parser.add_argument("--output-root", default="artifacts/design-partner-pilot-candidate")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    manifest = generate_design_partner_pilot_candidate_pack(
        profile=args.profile,
        rc_root=_resolve(args.rc_root),
        target_evidence_root=_resolve(args.target_evidence_root),
        output_root=_resolve(args.output_root),
    )
    payload = manifest.model_dump(mode="json", by_alias=True)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"wrote {_resolve(args.output_root) / 'manifest.json'}")
    if manifest.status == "blocked":
        raise SystemExit(1)


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


if __name__ == "__main__":
    main()
