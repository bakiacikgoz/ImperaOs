from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from imperaos.artifacts.store import ArtifactStore
from imperaos.cli import app
from imperaos.enterprise.maintenance import create_backup
from imperaos.enterprise.signing import canonical_payload_hash, verify_signed_artifact
from imperaos.governance.runtime import GovernanceRuntime
from imperaos.runtime.config import RuntimeConfig
from imperaos.schemas.models import OrchestratorResult
from imperaos.team.models import TeamSpec
from imperaos.team.supervisor import TeamSupervisor
from tests.artifact_store_support import make_artifact_pair

runner = CliRunner()


class _EnterpriseOrchestrator:
    def __init__(self, runtime: GovernanceRuntime):
        self.governance_runtime = runtime
        self._memory_manager = None

    def process(
        self,
        user_input: str,
        session_context=None,
        use_router: bool = True,
    ) -> OrchestratorResult:
        del user_input, session_context, use_router
        return OrchestratorResult(
            final_text="ok",
            used_path="llm_only",
            fallback_events=[],
            trace_id="trace-enterprise",
            metrics={"router_reason_code": "RULE_ROUTE"},
        )


def _write_signing_material(
    root: Path,
    *,
    key_id: str = "enterprise-signing-current",
) -> dict[str, str]:
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes_raw()
    public_raw = private_key.public_key().public_bytes_raw()

    private_dir = root / ".imperaos" / "enterprise" / "keys" / "private"
    trusted_dir = root / ".imperaos" / "enterprise" / "keys" / "trusted"
    private_dir.mkdir(parents=True, exist_ok=True)
    trusted_dir.mkdir(parents=True, exist_ok=True)

    private_payload = {
        "schema_version": "1",
        "key_id": key_id,
        "algorithm": "ed25519",
        "purpose": "artifact-signing",
        "private_key": base64.b64encode(private_raw).decode("ascii"),
        "public_key": base64.b64encode(public_raw).decode("ascii"),
        "created_at": datetime.now(UTC).isoformat(),
    }
    public_payload = {
        "schema_version": "1",
        "key_id": key_id,
        "algorithm": "ed25519",
        "purpose": "artifact-signing",
        "public_key": base64.b64encode(public_raw).decode("ascii"),
        "state": "active",
        "created_at": datetime.now(UTC).isoformat(),
    }
    manifest = {"schema_version": "1", "current_key_id": key_id, "revoked_keys": []}

    (private_dir / "current_key.json").write_text(
        json.dumps(private_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (trusted_dir / f"{key_id}.json").write_text(
        json.dumps(public_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ((root / ".imperaos" / "enterprise" / "keys") / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "key_id": key_id,
        "private_key": base64.b64encode(private_raw).decode("ascii"),
        "public_key": base64.b64encode(public_raw).decode("ascii"),
    }


def _write_identity_assertion(
    root: Path,
    signing_material: dict[str, str],
    *,
    permission: str,
) -> None:
    payload = {
        "schema_version": "1",
        "assertion_type": "external",
        "actor_id": "alice",
        "subject": "alice@example.com",
        "issuer": "idp.example.local",
        "roles": ["platform_admin", "security_admin"],
        "permissions": [permission],
        "issued_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        "key_id": signing_material["key_id"],
    }
    signature = Ed25519PrivateKey.from_private_bytes(
        base64.b64decode(signing_material["private_key"])
    ).sign(canonical_payload_hash(payload).encode("utf-8"))
    payload["signature"] = base64.b64encode(signature).decode("ascii")
    identity_dir = root / ".imperaos" / "enterprise" / "identity"
    identity_dir.mkdir(parents=True, exist_ok=True)
    (identity_dir / "current_assertion.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _enterprise_spec() -> TeamSpec:
    return TeamSpec.model_validate(
        {
            "version": "1",
            "team": {
                "team_id": "team-enterprise",
                "agents": [
                    {
                        "agent_id": "agent-intake",
                        "role": "Intake Agent",
                        "allowed_task_types": ["chat", "plan"],
                        "profile_name": "enterprise",
                        "model_overrides": {},
                        "memory_scope_access": ["session", "case"],
                        "tool_policy_profile": "enterprise",
                        "approval_mode": "auto",
                    }
                ],
                "supervisor_policy": "sequential_then_parallel",
                "handoff_rules": [],
                "termination_rules": {"max_tasks": 8, "max_retries": 1, "max_handoff_depth": 8},
            },
            "tasks": [],
        }
    )


def _write_enterprise_docs(root: Path) -> None:
    for name in (
        "SECURITY_BASELINE.md",
        "KEY_MANAGEMENT.md",
        "UPGRADE_AND_RECOVERY.md",
        "OBSERVABILITY_AND_SLO.md",
        "QUALIFICATION_MATRIX.md",
        "INSTALL.md",
        "DEPLOYMENT_GUIDE.md",
        "SUPPORT_BUNDLE.md",
    ):
        (root / name).write_text(f"# {name}\n", encoding="utf-8")


def test_enterprise_auth_and_security_baseline(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    signing = _write_signing_material(tmp_path)
    _write_identity_assertion(tmp_path, signing, permission="runtime.run")

    whoami = runner.invoke(app, ["auth", "whoami", "--profile", "enterprise", "--json"])
    assert whoami.exit_code == 0
    whoami_payload = json.loads(whoami.stdout)
    assert whoami_payload["contract_version"] == "3.0"
    assert whoami_payload["verified"] is True
    assert whoami_payload["actor"]["actor_id"] == "alice"

    allowed = runner.invoke(
        app,
        ["auth", "check", "--profile", "enterprise", "--permission", "runtime.run", "--json"],
    )
    assert allowed.exit_code == 0
    allowed_payload = json.loads(allowed.stdout)
    assert allowed_payload["contract_version"] == "3.0"
    assert allowed_payload["allowed"] is True

    baseline = runner.invoke(app, ["security", "baseline", "--profile", "enterprise", "--json"])
    assert baseline.exit_code == 0
    baseline_payload = json.loads(baseline.stdout)
    assert baseline_payload["contract_version"] == "3.0"
    assert baseline_payload["overall_status"] == "pass"
    assert (tmp_path / "artifacts" / "security_posture.json").exists()


def test_enterprise_mutating_command_requires_identity(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "approval",
            "decide",
            "--id",
            "missing-approval",
            "--approve",
            "--actor",
            "ops-user",
            "--profile",
            "enterprise",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "IDENTITY_REQUIRED"


def test_enterprise_team_audit_and_backup_are_signed(tmp_path: Path) -> None:
    _write_signing_material(tmp_path)
    cfg = RuntimeConfig.from_profile("enterprise").model_copy(
        update={
            "memory": RuntimeConfig.from_profile("enterprise").memory.model_copy(
                update={"db_path": str(tmp_path / "memory.sqlite3")}
            ),
            "governance": RuntimeConfig.from_profile("enterprise").governance.model_copy(
                update={
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            ),
            "team": RuntimeConfig.from_profile("enterprise").team.model_copy(
                update={
                    "artifact_dir": str(tmp_path / "team_jobs"),
                    "checkpoint_db_path": str(tmp_path / "checkpoints.sqlite3"),
                }
            ),
            "keys": RuntimeConfig.from_profile("enterprise").keys.model_copy(
                update={
                    "private_key_path": str(
                        tmp_path
                        / ".imperaos"
                        / "enterprise"
                        / "keys"
                        / "private"
                        / "current_key.json"
                    ),
                    "trusted_public_keys_dir": str(
                        tmp_path / ".imperaos" / "enterprise" / "keys" / "trusted"
                    ),
                    "key_manifest_path": str(
                        tmp_path / ".imperaos" / "enterprise" / "keys" / "manifest.json"
                    ),
                }
            ),
            "maintenance": RuntimeConfig.from_profile("enterprise").maintenance.model_copy(
                update={
                    "backup_dir": str(tmp_path / "backups"),
                }
            ),
        }
    )
    runtime = GovernanceRuntime(config=cfg)
    supervisor = TeamSupervisor(orchestrator=_EnterpriseOrchestrator(runtime), config=cfg)
    result = supervisor.run(
        spec=_enterprise_spec(),
        request="hello",
        case_id="case-1",
        job_id="job-1",
    )

    envelope = json.loads(Path(result.audit_envelope_path).read_text(encoding="utf-8"))
    assert envelope["integrity"]["signature_mode"] == "ed25519_local_file"

    verify = verify_signed_artifact(path=result.audit_envelope_path, config=cfg)
    assert verify["verified"] is True

    backup = create_backup(cfg, output_dir=tmp_path / "backup")
    assert backup["verified"] is True
    manifest_verify = verify_signed_artifact(path=backup["manifest_path"], config=cfg)
    assert manifest_verify["verified"] is True


def test_enterprise_metrics_support_bundle_and_ga_report(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    signing = _write_signing_material(tmp_path)
    _write_identity_assertion(tmp_path, signing, permission="support.export")
    _write_enterprise_docs(tmp_path)

    baseline = runner.invoke(app, ["security", "baseline", "--profile", "enterprise", "--json"])
    assert baseline.exit_code == 0
    baseline_verify = runner.invoke(
        app,
        [
            "keys",
            "verify",
            "--profile",
            "enterprise",
            "--path",
            "artifacts/security_posture.json",
            "--json",
        ],
    )
    assert baseline_verify.exit_code == 0
    baseline_verify_payload = json.loads(baseline_verify.stdout)
    assert baseline_verify_payload["contract_version"] == "3.0"
    assert baseline_verify_payload["verified"] is True

    metrics = runner.invoke(app, ["metrics", "snapshot", "--profile", "enterprise", "--json"])
    assert metrics.exit_code == 0
    assert (tmp_path / "artifacts" / "metrics_snapshot.json").exists()

    artifact_payload = (
        b'{"kind":"document","schemaVersion":1,"language":"en",'
        b'"pageMode":"document","blocks":[]}'
    )
    descriptor, revision = make_artifact_pair(artifact_payload)
    ArtifactStore(tmp_path / ".imperaos" / "artifacts").create_artifact(
        descriptor,
        revision,
        artifact_payload,
        operation="create",
        request_hash="a" * 64,
    )

    bundle = runner.invoke(
        app,
        ["support", "bundle", "export", "--profile", "enterprise", "--json"],
    )
    assert bundle.exit_code == 0
    bundle_payload = json.loads(bundle.stdout)
    assert bundle_payload["contract_version"] == "3.0"
    assert Path(bundle_payload["archive_path"]).exists()
    bundle_verify = verify_signed_artifact(path=bundle_payload["manifest_path"])
    assert bundle_verify["verified"] is True
    bundle_dir = Path(bundle_payload["bundle_dir"])
    artifact_snapshot = json.loads(
        (bundle_dir / "artifact_workspace_snapshot.json").read_text(encoding="utf-8")
    )
    assert artifact_snapshot["schemaVersion"] == "artifact-support/v1"
    assert artifact_snapshot["counts"]["artifactCount"] == 1
    serialized_snapshot = json.dumps(artifact_snapshot).lower()
    for forbidden in ("rawcontent", "relativepath", "secretref", "authorization"):
        assert forbidden not in serialized_snapshot

    readiness = runner.invoke(
        app,
        [
            "ga",
            "readiness",
            "--profile",
            "enterprise",
            "--report",
            "artifacts/ga_readiness_report.json",
            "--json",
        ],
    )
    assert readiness.exit_code == 0
    readiness_payload = json.loads(readiness.stdout)
    assert readiness_payload["contract_version"] == "3.0"
    assert readiness_payload["overall_status"] == "yellow"
    assert readiness_payload["go_no_go"] == "conditional"
    assert (tmp_path / "artifacts" / "GA_READINESS_REPORT.md").exists()
