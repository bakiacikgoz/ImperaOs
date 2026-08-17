from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from imperaos.control_plane.models import ClaimItem, ClaimMatrix, ClaimStatus
from imperaos.control_plane.qualification_closure import EnterpriseHatAEvidenceClosure
from imperaos.enterprise.signing import load_signed_artifact
from imperaos.runtime.config import RuntimeConfig


class ClaimGuard:
    def __init__(self, *, config: RuntimeConfig):
        self.config = config

    def evaluate(self, *, evidence_root: str | Path = "artifacts") -> ClaimMatrix:
        root = Path(evidence_root)
        claims = [
            self._enterprise_claim(root),
            self._public_desktop_claim(root),
            self._live_macos_computer_use_claim(root),
            self._live_platform_claim(
                "live-windows-computer-use",
                root,
                flag_enabled=self.config.computer_use.windows_live_enabled,
                reason="WINDOWS_COMPUTER_USE_NOT_QUALIFIED",
            ),
            self._live_platform_claim(
                "live-linux-computer-use",
                root,
                flag_enabled=self.config.computer_use.linux_live_enabled,
                reason="LINUX_COMPUTER_USE_NOT_QUALIFIED",
            ),
            ClaimItem(
                claim_id="multi-tenant-cloud-control-plane",
                status=ClaimStatus.DEFERRED,
                required_evidence=["tenant_isolation", "network_api", "sso_iam"],
                blocking_reasons=["MULTI_TENANT_CLOUD_OUT_OF_SCOPE"],
            ),
        ]
        return ClaimMatrix(claims=claims)

    def assert_allowed(self, *, claim_id: str, evidence_root: str | Path = "artifacts") -> None:
        matrix = self.evaluate(evidence_root=evidence_root)
        for claim in matrix.claims:
            if claim.claim_id == claim_id:
                if claim.status != ClaimStatus.ALLOWED:
                    raise RuntimeError(",".join(claim.blocking_reasons))
                return
        raise RuntimeError(f"unknown claim: {claim_id}")

    def _enterprise_claim(self, root: Path) -> ClaimItem:
        required = [
            "security_baseline",
            "qualification",
            "ga_readiness",
            "signed_evidence_pack",
            "enterprise_hat_a_closure",
        ]
        closure = self._enterprise_hat_a_closure(root)
        if closure is not None:
            status = {
                "ready": ClaimStatus.ALLOWED,
                "conditional": ClaimStatus.CONDITIONAL,
                "blocked": ClaimStatus.BLOCKED,
            }[closure.claim_status]
            return ClaimItem(
                claim_id="enterprise-self-hosted-agent-control-plane",
                status=status,
                required_evidence=required,
                blocking_reasons=closure.blocking_reasons,
            )

        blockers = []
        if not (root / "security_posture.json").exists():
            blockers.append("SECURITY_BASELINE_MISSING")
        if not (root / "qualification_report.json").exists():
            blockers.append("QUALIFICATION_REPORT_MISSING")
        if not (root / "ga_readiness_report.json").exists():
            blockers.append("GA_READINESS_MISSING")
        evidence_manifests = list((root / "control-plane" / "evidence").glob("*/manifest.json"))
        if not evidence_manifests:
            blockers.append("SIGNED_EVIDENCE_PACK_MISSING")
        return ClaimItem(
            claim_id="enterprise-self-hosted-agent-control-plane",
            status=ClaimStatus.CONDITIONAL if blockers else ClaimStatus.ALLOWED,
            required_evidence=required,
            blocking_reasons=blockers,
        )

    def _enterprise_hat_a_closure(self, root: Path) -> EnterpriseHatAEvidenceClosure | None:
        candidates = [
            root / "enterprise-hat-a" / "enterprise_hat_a_closure.json",
            root / "enterprise_hat_a_closure.json",
            root / "enterprise-hat-a-closure.json",
        ]
        closure_path = next((path for path in candidates if path.exists()), None)
        if closure_path is None:
            return None
        signed = load_signed_artifact(path=closure_path, config=self.config)
        data = signed.get("data") if isinstance(signed.get("data"), dict) else None
        if data is None:
            return EnterpriseHatAEvidenceClosure(
                closure_id="hat_a_invalid",
                profile=self.config.profile_name,
                commit_sha="unknown",
                generatedAtUtc=datetime.fromtimestamp(closure_path.stat().st_mtime, UTC),
                qualificationReportPath="unknown",
                signatureStatus="invalid",
                signatureMode=str(signed.get("signature_mode") or "missing"),
                baselineStatus="unknown",
                workloadStatus="unknown",
                claimStatus="blocked",
                blockingReasons=["ENTERPRISE_HAT_A_CLOSURE_INVALID"],
            )
        closure = EnterpriseHatAEvidenceClosure.model_validate(data)
        blocking = list(closure.blocking_reasons)
        if not signed.get("verified"):
            blocking.append(str(signed.get("error_code") or "CLOSURE_INTEGRITY_INVALID"))
        if not signed.get("signature_verified"):
            blocking.append("CLOSURE_SIGNATURE_INVALID")
        if blocking:
            return closure.model_copy(
                update={
                    "claim_status": "blocked",
                    "blocking_reasons": sorted(set(blocking)),
                }
            )
        return closure

    def _public_desktop_claim(self, root: Path) -> ClaimItem:
        blockers = []
        if not (root / "windows_signed_rc_gate.json").exists():
            blockers.append("WINDOWS_SIGNED_RC_EVIDENCE_MISSING")
        if not (root / "macos_notarization.json").exists():
            blockers.append("MACOS_NOTARIZATION_EVIDENCE_MISSING")
        if not (root / "clean_machine_smoke.json").exists():
            blockers.append("CLEAN_MACHINE_SMOKE_MISSING")
        blockers.append("HAT_B_EVIDENCE_MISSING")
        return ClaimItem(
            claim_id="public-desktop-installer",
            status=ClaimStatus.BLOCKED,
            required_evidence=[
                "macos_notarization",
                "windows_signed_rc",
                "clean_machine_smoke",
            ],
            blocking_reasons=sorted(set(blockers)),
        )

    def _live_macos_computer_use_claim(self, root: Path) -> ClaimItem:
        report = root / "computer_use" / "macos_qualification_report.json"
        blockers = []
        if not self.config.computer_use.macos_live_enabled:
            blockers.append("MACOS_LIVE_DISABLED")
        if not report.exists():
            blockers.append("COMPUTER_USE_NOT_QUALIFIED")
        if self.config.computer_use.raw_screenshot_persistence:
            blockers.append("RAW_SCREENSHOT_PERSISTED")
        return ClaimItem(
            claim_id="live-macos-computer-use",
            status=ClaimStatus.CONDITIONAL if not blockers else ClaimStatus.BLOCKED,
            required_evidence=["supervised_opt_in", "platform_qualification"],
            blocking_reasons=blockers,
        )

    def _live_platform_claim(
        self,
        claim_id: str,
        root: Path,
        *,
        flag_enabled: bool,
        reason: str,
    ) -> ClaimItem:
        _ = root
        blockers = []
        if not flag_enabled:
            blockers.append(reason)
        blockers.append("SIGNED_PLATFORM_QUALIFICATION_MISSING")
        return ClaimItem(
            claim_id=claim_id,
            status=ClaimStatus.BLOCKED,
            required_evidence=["platform_qualification", "signed_trusted_evidence"],
            blocking_reasons=sorted(set(blockers)),
        )
