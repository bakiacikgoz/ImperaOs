from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.claim_guard import ClaimGuard  # noqa: E402
from imperaos.control_plane.readiness import build_readiness_report  # noqa: E402
from imperaos.runtime.config import RuntimeConfig  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local control-plane release pack.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--output", default="artifacts/release-pack/control-plane-v1")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    config = RuntimeConfig.from_profile(args.profile)
    _write_text(output / "head_commit.txt", _git(["rev-parse", "HEAD"]))
    _write_text(output / "git_status.txt", _git(["status", "--short"]))

    copied = []
    for source_name, target_name in [
        ("artifacts/security_posture.json", "security_posture.json"),
        ("artifacts/qualification_report.json", "qualification_report.json"),
        ("artifacts/ga_readiness_report.json", "ga_readiness_report.json"),
        ("artifacts/metrics_snapshot.json", "metrics_snapshot.json"),
        ("artifacts/support_bundle_manifest.json", "support_bundle_manifest.json"),
    ]:
        source = Path(source_name)
        if source.exists():
            shutil.copy2(source, output / target_name)
            copied.append(target_name)

    matrix = ClaimGuard(config=config).evaluate(evidence_root="artifacts")
    readiness = build_readiness_report(config)
    (output / "control_plane_claim_matrix.json").write_text(
        json.dumps(matrix.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    (output / "control_plane_readiness_report.json").write_text(
        json.dumps(
            readiness.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    payload = {
        "status": "built",
        "output": str(output),
        "copied": copied,
        "claim_blockers": {
            item.claim_id: item.blocking_reasons
            for item in matrix.claims
            if item.blocking_reasons
        },
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(f"built {output}")


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return proc.stdout if proc.returncode == 0 else proc.stderr


if __name__ == "__main__":
    main()
