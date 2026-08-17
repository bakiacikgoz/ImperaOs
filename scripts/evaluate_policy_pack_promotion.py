from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.policy_packs import (
    diff_policy_packs,
    load_policy_pack_manifest,
    promote_policy_pack_dry_run,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate policy pack promotion dry-run.")
    parser.add_argument(
        "--base",
        default="contracts/control_plane/fixtures/policy_pack_valid_enterprise.json",
    )
    parser.add_argument(
        "--candidate",
        default="contracts/control_plane/fixtures/policy_pack_valid_enterprise.json",
    )
    parser.add_argument("--root-dir", default="artifacts/design-partner-rc/policy-packs/state")
    parser.add_argument(
        "--output",
        default="artifacts/design-partner-rc/policy_pack_promotion.json",
    )
    args = parser.parse_args()

    base = load_policy_pack_manifest(REPO_ROOT / args.base)
    candidate = load_policy_pack_manifest(REPO_ROOT / args.candidate)
    diff = diff_policy_packs(base=base, candidate=candidate)
    promotion = promote_policy_pack_dry_run(
        manifest=candidate,
        root_dir=REPO_ROOT / args.root_dir,
        dry_run=True,
    )
    payload = {
        "version": "control-plane.policy-pack-evaluation/v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "status": "pass" if diff.status != "blocked" and promotion.status != "blocked" else "fail",
        "diff": diff.model_dump(mode="json", by_alias=True),
        "promotion": promotion.model_dump(mode="json", by_alias=True),
    }
    output = REPO_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    if payload["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
