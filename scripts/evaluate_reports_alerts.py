from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.reports import build_reports_alerts_logs_manifest
from imperaos.control_plane.snapshot import build_control_plane_snapshot
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate reports, alerts, and logs manifest.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--root-dir", default=CONTROL_PLANE_STATE_ROOT)
    parser.add_argument("--evidence-root", default="artifacts")
    parser.add_argument("--output-dir", default="artifacts/design-partner-rc/reports-alerts-logs")
    args = parser.parse_args()

    snapshot = build_control_plane_snapshot(
        root_dir=REPO_ROOT / args.root_dir,
        profile=args.profile,
        evidence_root=REPO_ROOT / args.evidence_root,
        runtime_mode="cli",
        bridge_mode="cli",
        used_fixture=False,
    )
    manifest = build_reports_alerts_logs_manifest(
        snapshot=snapshot,
        output_dir=REPO_ROOT / args.output_dir,
    )
    payload = manifest.model_dump(mode="json", by_alias=True)
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    if manifest.status == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
