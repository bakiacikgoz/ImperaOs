from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.target_evidence import verify_target_evidence_bundle  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify target evidence bundle boundaries.")
    parser.add_argument(
        "--bundle",
        default="artifacts/design-partner-target-evidence/target_evidence_bundle.json",
    )
    parser.add_argument(
        "--output",
        default="artifacts/design-partner-target-evidence/target_evidence_verification.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = verify_target_evidence_bundle(_resolve(args.bundle))
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    if args.json:
        print(json.dumps(result.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True))
    else:
        print(f"wrote {output}")
    if result.status == "blocked":
        raise SystemExit(1)


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


if __name__ == "__main__":
    main()
