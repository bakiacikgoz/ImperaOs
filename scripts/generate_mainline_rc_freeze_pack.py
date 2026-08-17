from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.mainline_rc_freeze import (  # noqa: E402
    build_gate_evidence_summary,
    build_rc_freeze_manifest,
    write_rc_freeze_manifest,
)
from imperaos.control_plane.mainline_stack import (  # noqa: E402
    MergeRehearsalSpec,
    load_stack_graph_spec,
    run_merge_rehearsal,
    verify_stack_graph,
    write_merge_rehearsal_report,
    write_stack_graph_report,
)
from imperaos.control_plane.release_train import ClaimBoundarySummary  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the mainline RC freeze pack.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--stack", default="examples/release/design_partner_rc_stack.yaml")
    parser.add_argument("--evidence-root", default="artifacts")
    parser.add_argument("--output-root", default="artifacts/mainline-rc-freeze")
    parser.add_argument("--base", default="main")
    parser.add_argument("--head", default="codex/design-partner-rc-handoff-ops-readiness-v1")
    parser.add_argument("--mode", default="dry-run", choices=["dry-run", "temp-worktree"])
    parser.add_argument("--freeze-id")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    spec = load_stack_graph_spec(Path(args.stack))
    stack_report = verify_stack_graph(spec, branch_exists=_branch_exists)
    rehearsal_report = run_merge_rehearsal(
        MergeRehearsalSpec(
            baseRef=args.base,
            headRef=args.head,
            mode=args.mode,
            outputRoot=args.output_root,
        )
    )
    write_stack_graph_report(stack_report, output_root)
    write_merge_rehearsal_report(rehearsal_report, output_root)
    manifest = build_rc_freeze_manifest(
        profile=args.profile,
        output_root=output_root,
        stack_report=stack_report,
        rehearsal_report=rehearsal_report,
        gate_evidence=build_gate_evidence_summary(artifact_root=Path(args.evidence_root)),
        claim_boundaries=ClaimBoundarySummary(
            publicDesktop="blocked",
            liveComputerUse="blocked",
            approvalFreeIrreversibleMutation="blocked",
            unsupportedClaimAllowed=False,
        ),
        evidence_root=Path(args.evidence_root),
        freeze_id=args.freeze_id,
    )
    path = write_rc_freeze_manifest(manifest, output_root)
    payload = {
        "schemaVersion": "control-plane.mainline-rc-freeze-pack/v1",
        "status": manifest.status,
        "manifestPath": str(path),
        "blockers": manifest.blockers,
        "warnings": manifest.warnings,
    }
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(str(path))
    if manifest.status == "blocked":
        raise SystemExit(1)


def _branch_exists(branch: str) -> bool:
    candidates = [branch, f"origin/{branch}"]
    for candidate in candidates:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", f"{candidate}^{{commit}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return True
    return False


if __name__ == "__main__":
    main()
