from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.design_partner_rc import (  # noqa: E402
    EXPECTED_RC_AUDIT_CONDITIONALS,
    evaluate_design_partner_rc_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run blocker-only Design Partner RC audit gate.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--allow-expected-conditionals", action="store_true")
    parser.add_argument("--output", default="artifacts/design-partner-rc/rc_audit_gate.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    output = _resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pack_output = output.parent
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/generate_design_partner_rc_pack.py",
            "--profile",
            args.profile,
            "--output",
            str(pack_output),
            "--json",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        payload = {
            "schemaVersion": "control-plane.design-partner-rc-audit/v1",
            "strictStatus": "blocked",
            "auditStatus": "blocked",
            "expectedConditionals": [],
            "unexpectedWarnings": [],
            "blockers": ["DESIGN_PARTNER_RC_PACK_GENERATION_FAILED"],
            "exitMode": "blocker_only",
        }
    else:
        manifest = json.loads((pack_output / "manifest.json").read_text(encoding="utf-8"))
        expected = EXPECTED_RC_AUDIT_CONDITIONALS if args.allow_expected_conditionals else set()
        payload = evaluate_design_partner_rc_audit(
            manifest,
            expected_conditionals=set(expected),
        ).to_payload()
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"wrote {output}")
    if payload["auditStatus"] != "pass":
        raise SystemExit(1)


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


if __name__ == "__main__":
    main()
