from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.target_evidence import collect_target_evidence_rehearsal  # noqa: E402
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect non-destructive target rehearsal evidence."
    )
    parser.add_argument("--session", required=True)
    parser.add_argument("--output-root", default="artifacts/design-partner-target-evidence")
    parser.add_argument("--state-root", default=CONTROL_PLANE_STATE_ROOT)
    parser.add_argument("--evidence-root", default="artifacts")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    bundle = collect_target_evidence_rehearsal(
        session=_resolve(args.session),
        output_root=_resolve(args.output_root),
        state_root=_resolve(args.state_root),
        evidence_root=_resolve(args.evidence_root),
    )
    payload = {
        **bundle.model_dump(mode="json", by_alias=True),
        "bundlePath": str(_resolve(args.output_root) / "target_evidence_bundle.json"),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"wrote {_resolve(args.output_root) / 'target_evidence_bundle.json'}")
    if bundle.status == "blocked":
        raise SystemExit(1)


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


if __name__ == "__main__":
    main()
