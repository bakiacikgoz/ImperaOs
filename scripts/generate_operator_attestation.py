from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.models import TargetEvidenceSession  # noqa: E402
from imperaos.control_plane.operator_attestation import build_operator_attestation  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate operator attestation for target evidence."
    )
    parser.add_argument(
        "--session",
        default="artifacts/design-partner-target-evidence/session.json",
    )
    parser.add_argument("--operator-display-name", default="local-operator")
    parser.add_argument("--output-root", default="artifacts/design-partner-target-evidence")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    session = TargetEvidenceSession.model_validate_json(
        _resolve(args.session).read_text(encoding="utf-8")
    )
    attestation = build_operator_attestation(
        session=session,
        operator_display_name=args.operator_display_name,
        output_root=_resolve(args.output_root),
    )
    payload = {
        **attestation.model_dump(mode="json", by_alias=True),
        "attestationPath": str(_resolve(args.output_root) / "operator_attestation.json"),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"wrote {_resolve(args.output_root) / 'operator_attestation.json'}")


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


if __name__ == "__main__":
    main()
