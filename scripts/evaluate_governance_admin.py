from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.admin_store import (
    IdentityAssertion,
    apply_admin_change,
    build_governance_admin_report,
    propose_admin_change,
)
from imperaos.control_plane.policy_pack_store import (
    build_policy_pack_lifecycle_report,
    plan_policy_pack_rollback,
    promote_policy_pack,
    stage_policy_pack,
    validate_lifecycle_policy_pack,
)
from imperaos.control_plane.policy_packs import load_policy_pack_manifest
from imperaos.governance.approval_store import ApprovalStore
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate persistent governance admin store.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument(
        "--root-dir",
        default="artifacts/design-partner-pilot/governance/control-plane",
    )
    parser.add_argument(
        "--output",
        default="artifacts/design-partner-pilot/governance-admin-report.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    config = RuntimeConfig.from_profile(args.profile)
    store_root = REPO_ROOT / args.root_dir
    actor = IdentityAssertion(
        actor_id="enterprise-admin",
        roles=["platform_admin", "security_admin"],
        permissions=["config.write", "policy.promote", "reports.read"],
    )
    proposal = propose_admin_change(
        store_root=store_root,
        actor=actor,
        kind="user",
        operation="update",
        payload={"id": "pilot-operator", "status": "active", "roles": ["operator"]},
        dry_run=True,
        config=config,
    )
    blocked_apply = apply_admin_change(
        store_root=store_root,
        proposal_id=proposal.proposal_id,
        approval_id=proposal.approval_id or "missing",
        actor=actor,
        config=config,
    )
    if blocked_apply.status != "blocked":
        raise SystemExit("admin apply succeeded before approval")

    approvals = ApprovalStore(store_root / "approvals.sqlite3")
    approvals.decide(
        approval_id=proposal.approval_id or "",
        approve=True,
        actor=actor.actor_id,
        reason="governance-admin-gate",
    )
    applied = apply_admin_change(
        store_root=store_root,
        proposal_id=proposal.proposal_id,
        approval_id=proposal.approval_id or "",
        actor=actor,
        config=config,
    )
    manifest = load_policy_pack_manifest(
        REPO_ROOT / "contracts/control_plane/fixtures/policy_pack_valid_enterprise.json"
    )
    validate_lifecycle_policy_pack(manifest=manifest, store_root=store_root)
    stage_policy_pack(manifest=manifest, store_root=store_root)
    promoted = promote_policy_pack(manifest=manifest, store_root=store_root, config=config)
    rollback = plan_policy_pack_rollback(
        policy_pack_id=manifest.policy_pack_id,
        store_root=store_root,
    )
    admin_report = build_governance_admin_report(
        store_root=store_root,
        output_path=REPO_ROOT / args.output,
    )
    policy_report = build_policy_pack_lifecycle_report(
        store_root=store_root,
        output_path=REPO_ROOT / "artifacts/design-partner-pilot/policy-pack-lifecycle-report.json",
    )
    report = {
        **admin_report,
        "status": "pass"
        if applied.status == "applied"
        and promoted.status == "active"
        and rollback.status == "rollback_planned"
        else "fail",
        "blockedApplyBeforeApproval": blocked_apply.model_dump(mode="json", by_alias=True),
        "applied": applied.model_dump(mode="json", by_alias=True),
        "policyPackLifecycle": policy_report,
    }
    output = REPO_ROOT / args.output
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(report["status"])
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
