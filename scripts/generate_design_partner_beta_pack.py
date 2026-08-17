from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.beta_pack import generate_design_partner_beta_pack
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Design Partner Beta Operations pack.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--evidence-root", default="artifacts")
    parser.add_argument("--output-root", default="artifacts/design-partner-beta")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    manifest = generate_design_partner_beta_pack(
        output_root=REPO_ROOT / args.output_root,
        evidence_root=REPO_ROOT / args.evidence_root,
        config=RuntimeConfig.from_profile(args.profile),
    )
    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(manifest["status"])
    if manifest["status"] == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
