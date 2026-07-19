from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.control_plane.models import ProviderInvocationArtifact, ProviderToolPolicy


@dataclass(frozen=True)
class ProviderEvidenceWriteResult:
    status: str
    artifact_path: str | None
    artifact_hash: str | None
    blocking_reasons: tuple[str, ...] = ()


class ProviderEvidenceWriter:
    """Writes provider evidence without raw prompt, response, secret, or PII payloads."""

    def __init__(self, *, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def write_invocation(
        self,
        *,
        invocation_id: str,
        provider_kind: str,
        model: str,
        runtime_mode: str,
        status: str,
        policy_decision: dict[str, Any],
        request_hash: str,
        response_hash: str | None,
        tool_policy: dict[str, Any] | ProviderToolPolicy,
        blocking_reasons: list[str],
        extra_payload: dict[str, Any] | None = None,
        raw_inputs_for_scan: list[str] | None = None,
    ) -> ProviderEvidenceWriteResult:
        policy = (
            tool_policy
            if isinstance(tool_policy, ProviderToolPolicy)
            else ProviderToolPolicy.model_validate(tool_policy)
        )
        artifact = ProviderInvocationArtifact(
            status=status,
            invocationId=invocation_id,
            providerKind=provider_kind,
            model=model,
            runtimeMode=runtime_mode,
            policyDecision=policy_decision,
            requestHash=request_hash,
            responseHash=response_hash,
            rawPersistence=False,
            evidenceMode="hash_only",
            toolPolicy=policy,
            blockingReasons=blocking_reasons,
            createdAtUtc=datetime.now(UTC),
        )
        payload = artifact.model_dump(mode="json", by_alias=True)
        if extra_payload:
            payload.update(extra_payload)

        encoded = json.dumps(payload, indent=2, sort_keys=True)
        leaks = [
            raw
            for raw in raw_inputs_for_scan or []
            if raw and len(raw) >= 4 and raw in encoded
        ]
        if leaks:
            return ProviderEvidenceWriteResult(
                status="error",
                artifact_path=None,
                artifact_hash=None,
                blocking_reasons=("PROVIDER_EVIDENCE_LEAKAGE_DETECTED",),
            )

        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"{invocation_id}.json"
        path.write_text(encoded + "\n", encoding="utf-8")
        return ProviderEvidenceWriteResult(
            status=status,
            artifact_path=str(path),
            artifact_hash=_file_sha256(path),
            blocking_reasons=tuple(blocking_reasons),
        )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"
