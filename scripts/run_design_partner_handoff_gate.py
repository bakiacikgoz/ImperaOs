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
from imperaos.control_plane.pilot_ops_drill import run_pilot_ops_drill  # noqa: E402
from imperaos.control_plane.release_train import (  # noqa: E402
    build_release_train_manifest,
    verify_release_train,
    write_release_train_manifest,
    write_release_train_verification,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run design partner handoff gate.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--artifact-root", default="artifacts")
    parser.add_argument("--output-root", default="artifacts/design-partner-handoff")
    parser.add_argument("--environment-label", default="design-partner-rc-local")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    artifact_root = Path(args.artifact_root)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = build_release_train_manifest(profile=args.profile, artifact_root=artifact_root)
    write_release_train_manifest(
        manifest=manifest,
        output_path=output_root / "release_train_manifest.json",
    )
    release_report = verify_release_train(
        manifest,
        manifest_path=output_root / "release_train_manifest.json",
    )
    write_release_train_verification(
        report=release_report,
        output_path=output_root / "RELEASE_TRAIN_REPORT.json",
    )
    drill = run_pilot_ops_drill(profile=args.profile, output_root=output_root)
    handoff = build_design_partner_handoff_pack(
        profile=args.profile,
        output_root=output_root,
        environment_label=args.environment_label,
        artifact_root=artifact_root,
        release_train_report=release_report,
        drill_report=drill,
    )
    verification = verify_design_partner_handoff_pack(manifest_path=output_root / "manifest.json")
    status = (
        "pass"
        if release_report.status in {"pass", "conditional"}
        and drill.status in {"pass", "conditional"}
        and handoff.status in {"ready", "conditional"}
        and verification.status in {"ready", "conditional"}
        else "fail"
    )
    payload = {
        "schemaVersion": "control-plane.design-partner-handoff-gate/v1",
        "status": status,
        "releaseTrainStatus": release_report.status,
        "pilotOpsDrillStatus": drill.status,
        "handoffStatus": handoff.status,
        "verificationStatus": verification.status,
        "manifestPath": str(output_root / "manifest.json"),
        "blockingReasons": sorted(
            set(release_report.blockers + drill.blockers + verification.blockers)
        ),
        "warnings": sorted(set(release_report.warnings + drill.warnings + verification.warnings)),
    }
    _write_json(output_root / "gate_result.json", payload)
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(status)
    if status != "pass":
        raise SystemExit(1)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


if __name__ == "__main__":
    main()
