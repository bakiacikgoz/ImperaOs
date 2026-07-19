from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.mainline_rc_freeze import verify_rc_freeze_manifest  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the mainline RC freeze verifier gate.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument(
        "--manifest",
        default="artifacts/mainline-rc-freeze/manifest.json",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    _ = args.profile

    report = verify_rc_freeze_manifest(manifest_path=Path(args.manifest))
    payload = {
        "schemaVersion": "control-plane.mainline-rc-freeze-gate/v1",
        "status": "pass" if report.status in {"ready", "conditional"} else "fail",
        "verificationStatus": report.status,
        "manifestPath": report.manifest_path,
        "manifestSha256": report.manifest_sha256,
        "blockingReasons": report.blockers,
        "warnings": report.warnings,
    }
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload["status"])
    if payload["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
