from __future__ import annotations

from imperaos.control_plane.release_train import (
    ClaimBoundarySummary,
    ReleaseTrainGateRef,
    ReleaseTrainManifest,
    verify_release_train,
)


def test_release_train_passes_with_blocked_no_ship_claims() -> None:
    report = verify_release_train(_manifest())

    assert report.status == "pass"
    assert report.blockers == []


def test_release_train_blocks_unsupported_claim_allowed() -> None:
    manifest = _manifest(
        claim_boundaries=ClaimBoundarySummary(
            publicDesktop="allowed",
            liveComputerUse="blocked",
            approvalFreeIrreversibleMutation="blocked",
            unsupportedClaimAllowed=True,
        )
    )

    report = verify_release_train(manifest)

    assert report.status == "blocked"
    assert "UNSUPPORTED_CLAIM_ALLOWED" in report.blockers


def test_release_train_dirty_worktree_is_strict_blocker() -> None:
    manifest = _manifest(worktree_dirty=True)

    report = verify_release_train(manifest, strict=True)

    assert report.status == "blocked"
    assert "WORKTREE_DIRTY" in report.blockers


def _manifest(
    *,
    claim_boundaries: ClaimBoundarySummary | None = None,
    worktree_dirty: bool = False,
) -> ReleaseTrainManifest:
    return ReleaseTrainManifest(
        profile="enterprise",
        mode="local",
        baseBranch="base",
        headBranch="head",
        headSha="abc123",
        worktreeDirty=worktree_dirty,
        requiredGates=[
            ReleaseTrainGateRef(
                gateId="design-partner-field-evidence-gate",
                command="make design-partner-field-evidence-gate",
                status="pass",
            )
        ],
        artifactRoots=[],
        claimBoundaries=claim_boundaries
        or ClaimBoundarySummary(
            publicDesktop="blocked",
            liveComputerUse="blocked",
            approvalFreeIrreversibleMutation="blocked",
            unsupportedClaimAllowed=False,
        ),
    )
