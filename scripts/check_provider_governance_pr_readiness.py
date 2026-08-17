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
from imperaos.control_plane.provider_conformance import run_provider_native_gate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Check provider governance PR readiness.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--branch", default="")
    parser.add_argument("--output", default="artifacts/provider-governance-pr/readiness.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    output = _resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    provider_gate = run_provider_native_gate(
        profile=args.profile,
        output_dir=output.parent / "provider-native",
    )
    rc_manifest = _build_rc_manifest(output.parent / "design-partner-rc")
    rc_audit = evaluate_design_partner_rc_audit(
        rc_manifest,
        expected_conditionals=set(EXPECTED_RC_AUDIT_CONDITIONALS),
    )
    blockers: list[str] = []
    if provider_gate["status"] != "pass":
        blockers.append("provider_native_gate")
    if rc_audit.audit_status != "pass":
        blockers.append("design_partner_rc_audit_gate")
    payload = {
        "schemaVersion": "control-plane.provider-governance-pr-readiness/v1",
        "status": "pass" if not blockers else "blocked",
        "branch": args.branch or _git(["branch", "--show-current"]).strip(),
        "requiredGates": {
            "provider_native_gate": provider_gate["status"],
            "pilot_readiness_gate": "externally_verified",
            "design_partner_rc_audit_gate": rc_audit.audit_status,
        },
        "knownConditionals": list(rc_audit.expected_conditionals),
        "blockers": blockers,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"wrote {output}")
    if blockers:
        raise SystemExit(1)


def _build_rc_manifest(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/generate_design_partner_rc_pack.py",
            "--profile",
            "enterprise",
            "--output",
            str(output_dir),
            "--json",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {"status": "blocked", "warnings": [], "blockers": ["RC_PACK_GENERATION_FAILED"]}
    return json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def _git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else ""


if __name__ == "__main__":
    main()
