from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from imperaos.control_plane.models import (
    AttestationVerificationResult,
    OperatorAttestation,
    OperatorClaimReview,
)
from imperaos.control_plane.storage import canonical_json_hash
from imperaos.control_plane.target_evidence import REQUIRED_BLOCKED_CLAIMS


def build_operator_attestation(
    *,
    session,
    operator_display_name: str,
    output_root: str | Path,
    accepted_boundaries: list[str] | tuple[str, ...] | None = None,
    signed: bool = False,
) -> OperatorAttestation:
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    accepted = list(accepted_boundaries or REQUIRED_BLOCKED_CLAIMS)
    reviews = [
        OperatorClaimReview(
            claimId=claim,
            status="accepted" if claim in accepted else "not_reviewed",
            boundaryStatus="blocked",
            notesHash=None,
        )
        for claim in REQUIRED_BLOCKED_CLAIMS
    ]
    seed = {
        "sessionId": session.session_id,
        "operatorDisplayNameHash": _hash_string(operator_display_name),
    }
    attestation = OperatorAttestation(
        attestationId=f"operator-attestation-{canonical_json_hash(seed, prefixed=False)[:16]}",
        sessionId=session.session_id,
        operatorDisplayNameHash=_hash_string(operator_display_name),
        reviewedClaims=reviews,
        acceptedBoundaries=accepted,
        signedAtUtc=datetime.now(UTC) if signed else None,
        signature=None,
    )
    path = output / "operator_attestation.json"
    path.write_text(
        json.dumps(attestation.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return attestation


def verify_operator_attestation(
    attestation: OperatorAttestation | dict,
    *,
    required_boundaries,
) -> AttestationVerificationResult:
    model = (
        attestation
        if isinstance(attestation, OperatorAttestation)
        else OperatorAttestation.model_validate(attestation)
    )
    blocking: list[str] = []
    accepted = set(model.accepted_boundaries)
    reviewed = {item.claim_id: item for item in model.reviewed_claims}
    for boundary in required_boundaries:
        if boundary not in accepted:
            blocking.append(f"MISSING_ACCEPTED_BOUNDARY:{boundary}")
        review = reviewed.get(boundary)
        if review is None or review.status != "accepted" or review.boundary_status != "blocked":
            blocking.append(f"MISSING_ACCEPTED_REVIEW:{boundary}")
    return AttestationVerificationResult(
        status="blocked" if blocking else "pass",
        blockingReasons=sorted(set(blocking)),
        warnings=[],
    )


def _hash_string(value: str) -> str:
    return canonical_json_hash({"value": value})
