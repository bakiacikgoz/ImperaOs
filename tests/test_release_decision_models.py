from __future__ import annotations

import pytest
from pydantic import ValidationError

from imperaos.release_decision.models import (
    EvidenceRef,
    HumanSignoffRecord,
    ReleaseDecisionDossier,
)


def test_models_validate_status_enums() -> None:
    dossier = ReleaseDecisionDossier(
        decisionId="rc-decision-enterprise",
        profile="enterprise",
        status="conditional",
        hatAStatus="conditional",
        hatBStatus="blocked_external_credentials",
        designPartnerRcStatus="conditional",
        signoffStatus="missing",
        requiredSignoffRoles=["release_owner", "security_operator"],
    )

    assert dossier.status == "conditional"
    assert dossier.hat_b_status == "blocked_external_credentials"


def test_evidence_ref_rejects_absolute_path() -> None:
    with pytest.raises(ValidationError):
        EvidenceRef(
            artifactId="ledger",
            path="C:/tmp/gate_evidence_ledger.json",
            sha256="0" * 64,
            kind="gate_ledger",
        )


def test_signoff_record_requires_hashed_identity() -> None:
    record = HumanSignoffRecord(
        signoffId="release-owner",
        role="release_owner",
        operatorDisplayNameHash="a" * 64,
        dossierSha256="b" * 64,
        acceptedBoundaries=["NO_PUBLIC_DESKTOP_RELEASE"],
        signedAtUtc="2026-06-15T10:00:00Z",
    )

    assert record.role == "release_owner"
