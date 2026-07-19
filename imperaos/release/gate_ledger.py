from __future__ import annotations

import json
import subprocess
from pathlib import Path

from imperaos.control_plane.storage import canonical_json_hash
from imperaos.release.gate_models import GateEvidenceLedger, GateRunResult, ReleaseGatePlan


def build_gate_evidence_ledger(
    *,
    plan: ReleaseGatePlan,
    gate_results: list[GateRunResult],
    repo_root: Path,
    output_root: Path,
) -> GateEvidenceLedger:
    blockers: list[str] = []
    warnings: list[str] = []
    for result in gate_results:
        blockers.extend(result.blocking_reasons)
        warnings.extend(result.warnings)
        if result.missing_artifact_requirements:
            warnings.extend(
                f"MISSING_REQUIRED_ARTIFACT:{item}"
                for item in result.missing_artifact_requirements
            )
    missing_gate_ids = sorted(set(plan.required_gate_ids) - {item.gate_id for item in gate_results})
    warnings.extend(f"MISSING_REQUIRED_GATE:{item}" for item in missing_gate_ids)
    status = "blocked" if blockers else "conditional" if warnings else "ready"
    ledger = GateEvidenceLedger(
        repoHeadSha=_git_value(repo_root, ["rev-parse", "HEAD"], fallback="0" * 40),
        branch=_git_value(repo_root, ["branch", "--show-current"], fallback="unknown"),
        target=plan.target,
        gateResults=gate_results,
        requiredGateIds=plan.required_gate_ids,
        status=status,
        blockingReasons=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        artifactRoot=str(output_root).replace("\\", "/"),
    )
    return ledger.model_copy(update={"ledger_sha256": _ledger_hash(ledger)})


def write_gate_evidence_ledger(*, ledger: GateEvidenceLedger, repo_root: Path) -> Path:
    root = Path(ledger.artifact_root)
    if not root.is_absolute():
        root = repo_root / root
    root.mkdir(parents=True, exist_ok=True)
    path = root / "gate_evidence_ledger.json"
    _write_json(path, ledger.model_dump(mode="json", by_alias=True))
    _write_markdown(root / "GATE_EVIDENCE_LEDGER.md", ledger)
    return path


def _ledger_hash(ledger: GateEvidenceLedger) -> str:
    payload = ledger.model_dump(mode="json", by_alias=True)
    payload["ledgerSha256"] = None
    return canonical_json_hash(payload, prefixed=False)


def _write_json(path: Path, payload: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _write_markdown(path: Path, ledger: GateEvidenceLedger) -> None:
    lines = [
        "# Gate Evidence Ledger",
        "",
        f"- Status: `{ledger.status}`",
        f"- Target: `{ledger.target.target_id}`",
        f"- Platform: `{ledger.target.platform}`",
        f"- Ready blockers: `{len(ledger.blocking_reasons)}`",
        "",
        "## Gates",
        "",
    ]
    lines.extend(f"- `{item.gate_id}`: `{item.status}`" for item in ledger.gate_results)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _git_value(repo_root: Path, args: list[str], *, fallback: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip() or fallback
    except Exception:
        return fallback
