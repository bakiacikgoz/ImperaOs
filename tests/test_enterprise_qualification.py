from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from imperaos import __version__
from imperaos.cli import app
from imperaos.enterprise.maintenance import ga_readiness_report
from imperaos.enterprise.qualification import (
    MIN_EXTENDED_SOAK_SECONDS,
    MIN_GREEN_SOAK_SECONDS,
    QualificationFailure,
    _merge_qualification_report,
    _publish_extended_soak_evidence,
    _resolve_merge_from_report_path,
    _run_terminal_positive_smoke,
    evaluate_qualification_evidence,
    run_qualification,
    write_qualification_report,
)
from imperaos.enterprise.signing import (
    canonical_payload_hash,
    verify_signed_artifact,
    write_signed_json,
)
from imperaos.runtime.config import RuntimeConfig
from imperaos.team.pilot_gate import build_deterministic_pilot_orchestrator

runner = CliRunner()


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
    }


def _write_identity_assertion(
    root: Path,
    signing_material: dict[str, str],
    *,
    permissions: list[str],
) -> None:
    payload = {
        "schema_version": "1",
        "assertion_type": "external",
        "actor_id": "alice",
        "subject": "alice@example.com",
        "issuer": "idp.example.local",
        "roles": ["platform_admin", "security_admin"],
        "permissions": permissions,
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


def _green_workload(name: str, *, duration_seconds: int) -> dict[str, object]:
    return {
        "name": name,
        "purpose": name,
        "start_time": datetime.now(UTC).isoformat(),
        "end_time": datetime.now(UTC).isoformat(),
        "duration_seconds": duration_seconds,
        "execution_mode": "mixed",
        "required_for_green": name != "24h_soak_flow",
        "support_classification": "supported",
        "pass_fail": "pass",
        "task_count_total": 4,
        "task_count_success": 4,
        "task_count_failed": 0,
        "failure_class_breakdown": {},
        "replay_verify_status": "pass",
        "signing_verify_status": "pass",
        "approval_latency_summary": {"count": 1},
        "provider_retry_count": 0,
        "stale_approval_count": 0,
        "stale_resume_count": 0,
        "resume_duplicate_suppressed_count": 0,
        "memory_conflict_count": 0,
        "serialized_due_to_policy_count": 0,
        "fallback_mode_count": 0,
        "operator_intervention_count": 0,
        "support_bundle_sufficient": True,
        "metrics_snapshot_sufficient": True,
        "unclear_errors": [],
        "runbook_gaps": [],
        "notes": [],
        "operational_followups": [],
        "terminal_status": "completed",
        "terminal_job_id": f"{name}-job",
        "resume_round_count": 0,
        "approval_rounds": [],
        "artifacts": {},
        "blocking_findings": [],
        "residual_risks": [],
        "evidence_verified": True,
    }


def _complete_green_qualification_payload() -> dict[str, object]:
    workloads = [
        _green_workload("baseline_enterprise_flow", duration_seconds=300),
        _green_workload("approval_heavy_flow", duration_seconds=300),
        _green_workload("conflict_heavy_flow", duration_seconds=300),
        _green_workload("soak_6h_flow", duration_seconds=MIN_GREEN_SOAK_SECONDS),
        _green_workload("failure_injection_flow", duration_seconds=300),
        {
            **_green_workload("24h_soak_flow", duration_seconds=0),
            "required_for_green": False,
            "pass_fail": "not_run",
            "replay_verify_status": "not_run",
            "signing_verify_status": "not_run",
            "evidence_verified": False,
        },
    ]
    evaluation = evaluate_qualification_evidence(
        qualification_payload={
            "profile": "enterprise",
            "workloads": workloads,
            "minimum_green_soak_seconds": MIN_GREEN_SOAK_SECONDS,
        }
    )
    return {
        "version": "1",
        "generated_at": datetime.now(UTC).isoformat(),
        "runtime_version": __version__,
        "environment_summary": {"platform": "test"},
        "profile": "enterprise",
        "signing_mode": "local_file",
        "identity_mode": "external_assertion",
        "qualification_evidence_mode": "mixed",
        "minimum_green_soak_seconds": MIN_GREEN_SOAK_SECONDS,
        "qualification_status": evaluation["qualification_status"],
        "workloads": workloads,
        "supported_profiles": evaluation["supported_profiles"],
        "conditional_profiles": evaluation["conditional_profiles"],
        "unsupported_profiles": evaluation["unsupported_profiles"],
        "blocking_findings": evaluation["blocking_findings"],
        "residual_risks": [
            item
            for item in evaluation["residual_risks"]
            if item != "24h soak evidence not yet published"
        ],
        "recommended_status": evaluation["recommended_status"],
        "go_no_go": evaluation["go_no_go"],
        "operational_findings": evaluation["operational_findings"],
        "artifacts": {},
    }


def test_extended_24h_soak_is_published_from_sustained_soak(tmp_path: Path) -> None:
    workloads = [
        _green_workload("baseline_enterprise_flow", duration_seconds=300),
        _green_workload("approval_heavy_flow", duration_seconds=300),
        _green_workload("conflict_heavy_flow", duration_seconds=300),
        _green_workload("soak_6h_flow", duration_seconds=MIN_EXTENDED_SOAK_SECONDS),
        _green_workload("failure_injection_flow", duration_seconds=300),
        {
            **_green_workload("24h_soak_flow", duration_seconds=0),
            "required_for_green": False,
            "pass_fail": "not_run",
            "replay_verify_status": "not_run",
            "signing_verify_status": "not_run",
            "evidence_verified": False,
            "residual_risks": ["24h soak evidence not yet published"],
        },
    ]

    published = _publish_extended_soak_evidence(
        workloads,
        run_root=tmp_path / "artifacts" / "qualification" / "qualification-test",
    )
    extended = next(item for item in published if item["name"] == "24h_soak_flow")

    assert extended["pass_fail"] == "pass"
    assert extended["duration_seconds"] == MIN_EXTENDED_SOAK_SECONDS
    assert extended["evidence_verified"] is True
    assert extended["required_for_green"] is False
    assert extended["replay_verify_status"] == "pass"
    assert extended["signing_verify_status"] == "pass"
    assert extended["blocking_findings"] == []
    assert extended["residual_risks"] == []
    assert extended["artifacts"]["source_workload"] == "soak_6h_flow"

    evaluation = evaluate_qualification_evidence(
        qualification_payload={
            "profile": "enterprise",
            "workloads": published,
            "minimum_green_soak_seconds": MIN_GREEN_SOAK_SECONDS,
        }
    )
    assert "24h soak evidence not yet published" not in evaluation["residual_risks"]
    assert evaluation["qualification_status"] == "pass"
    assert evaluation["go_no_go"] == "go"


def test_qualification_runner_writes_signed_report(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")

    payload = run_qualification(
        config=config,
        mode="mixed",
        soak_hours=0.0003,
        output_root=tmp_path / "artifacts" / "qualification",
        live_orchestrator_builder=build_deterministic_pilot_orchestrator,
    )
    paths = write_qualification_report(
        payload=payload,
        config=config,
        output_root=tmp_path / "artifacts" / "qualification",
    )

    verify = verify_signed_artifact(path=paths["latest_json"], config=config)
    assert verify["verified"] is True
    assert Path(paths["run_markdown"]).exists()
    assert payload["qualification_status"] == "partial"
    assert {item["name"] for item in payload["workloads"]} >= {
        "baseline_enterprise_flow",
        "approval_heavy_flow",
        "conflict_heavy_flow",
        "soak_6h_flow",
        "failure_injection_flow",
    }


def test_ga_readiness_uses_signed_qualification_evidence(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    _write_enterprise_docs(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")

    payload = run_qualification(
        config=config,
        mode="mixed",
        soak_hours=0.0003,
        output_root=tmp_path / "artifacts" / "qualification",
        live_orchestrator_builder=build_deterministic_pilot_orchestrator,
    )
    write_qualification_report(
        payload=payload,
        config=config,
        output_root=tmp_path / "artifacts" / "qualification",
    )

    readiness = ga_readiness_report(config)
    assert readiness["overall_status"] == "yellow"
    assert readiness["go_no_go"] == "conditional"
    assert readiness["qualification_report"]["verified"] is True
    assert readiness["qualification_report"]["minimum_green_soak_seconds"] == MIN_GREEN_SOAK_SECONDS


def test_ga_readiness_turns_green_with_complete_verified_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    _write_enterprise_docs(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    payload = _complete_green_qualification_payload()

    write_signed_json(
        path=tmp_path / "artifacts" / "qualification_report.json",
        artifact="qualification_report",
        data=payload,
        config=config,
        purpose="qualification-report",
        status="ok",
    )

    readiness = ga_readiness_report(config)
    assert readiness["overall_status"] == "green"
    assert readiness["go_no_go"] == "go"
    assert readiness["qualification_report"]["verified"] is True


def test_ga_readiness_red_on_invalid_qualification_signature(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    _write_enterprise_docs(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "qualification_report.json").write_text(
        json.dumps({"artifact": "qualification_report", "data": {"bad": True}}, ensure_ascii=False),
        encoding="utf-8",
    )

    readiness = ga_readiness_report(config)
    assert readiness["overall_status"] == "red"
    assert readiness["go_no_go"] == "no-go"
    assert readiness["qualification_report"]["verified"] is False


def test_cli_qualification_run_generates_reports(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    signing = _write_signing_material(tmp_path)
    _write_identity_assertion(
        tmp_path,
        signing,
        permissions=[
            "runtime.run",
            "approval.decide",
            "approval.execute",
            "support.export",
            "backup.create",
            "restore.verify",
        ],
    )

    monkeypatch.setattr(
        "imperaos.cli._build_orchestrator",
        lambda config, **kwargs: build_deterministic_pilot_orchestrator(config),
    )

    result = runner.invoke(
        app,
        [
            "qualification",
            "run",
            "--profile",
            "enterprise",
            "--mode",
            "mixed",
            "--soak-hours",
            "0.0003",
            "--output-root",
            "artifacts/qualification",
            "--json",
        ],
    )
    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    assert payload["go_no_go"] in {"conditional", "no-go"}
    assert (tmp_path / "artifacts" / "qualification_report.json").exists()
    assert (tmp_path / "artifacts" / "QUALIFICATION_REPORT.md").exists()


def test_qualification_runner_captures_workload_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")

    def fail_baseline(**kwargs):  # noqa: ANN003
        raise RuntimeError("baseline exploded")

    monkeypatch.setattr(
        "imperaos.enterprise.qualification._run_baseline_enterprise_flow",
        fail_baseline,
    )

    payload = run_qualification(
        config=config,
        mode="mixed",
        soak_hours=0.0003,
        output_root=tmp_path / "artifacts" / "qualification",
        live_orchestrator_builder=build_deterministic_pilot_orchestrator,
    )

    baseline = next(
        item for item in payload["workloads"] if item["name"] == "baseline_enterprise_flow"
    )
    assert baseline["pass_fail"] == "fail"
    assert baseline["blocking_findings"] == ["QUALIFICATION_WORKLOAD_FAILED"]
    assert payload["qualification_status"] in {"partial", "fail"}


def test_terminal_positive_smoke_handles_multiple_resume_rounds(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    config = config.model_copy(
        update={
            "team": config.team.model_copy(update={"artifact_dir": str(tmp_path / "jobs")}),
        }
    )

    spec_payload = {
        "version": "1",
        "team": {
            "team_id": "team-enterprise-qualification",
            "agents": [
                {
                    "agent_id": "agent-1",
                    "role": "Intake Agent",
                    "allowed_task_types": ["plan"],
                    "profile_name": "enterprise",
                    "memory_scope_access": ["case"],
                    "tool_policy_profile": "enterprise",
                    "approval_mode": "auto",
                }
            ],
            "handoff_rules": [],
            "termination_rules": {"max_tasks": 6, "max_retries": 1, "max_handoff_depth": 6},
        },
        "tasks": [
            {
                "task_id": "task-intake",
                "title": "intake",
                "task_type": "plan",
                "role": "Intake Agent",
                "depends_on": [],
                "input_template": "{{request}}",
            }
        ],
    }
    from imperaos.team.models import TeamSpec

    spec = TeamSpec.model_validate(spec_payload)

    events_by_job = {
        "baseline_enterprise_flow-blocked": [
            {
                "event": "approval_requested",
                "task_id": "task-intake",
                "data": {"approval_id": "a1"},
            }
        ],
        "baseline_enterprise_flow-resume": [
            {
                "event": "approval_requested",
                "task_id": "task-research",
                "data": {"approval_id": "a2"},
            },
            {"event": "approval_consumed", "data": {"approval_id": "a1"}},
        ],
        "baseline_enterprise_flow-resume-2": [
            {"event": "approval_consumed", "data": {"approval_id": "a2"}},
        ],
    }
    statuses = {
        "baseline_enterprise_flow-blocked": "blocked",
        "baseline_enterprise_flow-resume": "blocked",
        "baseline_enterprise_flow-resume-2": "completed",
    }

    class FakeSupervisor:
        def __init__(self, orchestrator, config):  # noqa: ANN001, ANN202
            self.orchestrator = orchestrator
            self.config = config

        def run(self, *, spec, request, case_id, job_id, approval_overrides=None):  # noqa: ANN001
            return SimpleNamespace(
                job=SimpleNamespace(job_id=job_id, status=SimpleNamespace(value=statuses[job_id])),
                audit_envelope_path=str(
                    Path(self.config.team.artifact_dir) / job_id / "audit_envelope.json"
                ),
            )

    class FakeGovernanceRuntime:
        def decide_approval(self, *, approval_id, approve, actor, reason):  # noqa: ANN001
            return SimpleNamespace(error_code=None)

        def execute_approval(self, *, approval_id):  # noqa: ANN001
            return SimpleNamespace(error_code=None)

    monkeypatch.setattr("imperaos.enterprise.qualification.TeamSupervisor", FakeSupervisor)
    monkeypatch.setattr(
        "imperaos.enterprise.qualification.load_events",
        lambda job_id, root_dir: list(events_by_job[job_id]),
    )
    monkeypatch.setattr(
        "imperaos.enterprise.qualification.replay_job",
        lambda job_id, root_dir, verify=True: {
            "verified": True,
            "event_count": len(events_by_job[job_id]),
        },
    )
    monkeypatch.setattr(
        "imperaos.enterprise.qualification._collect_resume_overrides",
        lambda *, events, governance_runtime: (
            {
                str(item["task_id"]): {"task": str(item["data"]["approval_id"])}
                for item in events
                if str(item.get("event")) == "approval_requested"
            },
            [
                {
                    "task_id": str(item["task_id"]),
                    "target": "task",
                    "approval_id": str(item["data"]["approval_id"]),
                    "status": "executed",
                }
                for item in events
                if str(item.get("event")) == "approval_requested"
            ],
        ),
    )
    monkeypatch.setattr(
        "imperaos.enterprise.qualification._resume_from_source_job",
        lambda **kwargs: {
            "result": SimpleNamespace(
                job=SimpleNamespace(
                    job_id=kwargs["resume_job_id"],
                    status=SimpleNamespace(value=statuses[kwargs["resume_job_id"]]),
                ),
                audit_envelope_path=str(
                    Path(config.team.artifact_dir) / kwargs["resume_job_id"] / "audit_envelope.json"
                ),
            )
        },
    )

    result = _run_terminal_positive_smoke(
        name="baseline_enterprise_flow",
        spec=spec,
        config=config,
        orchestrator_builder=lambda runtime_config: SimpleNamespace(
            governance_runtime=FakeGovernanceRuntime()
        ),
        actor="qualification-runner",
    )
    summary = result["summary"]
    assert summary["terminal_status"] == "completed"
    assert summary["resume_round_count"] == 2
    assert summary["terminal_job_id"] == "baseline_enterprise_flow-resume-2"
    assert summary["approvals_requested"] == 2
    assert len(summary["approval_rounds"]) == 2


def test_terminal_positive_smoke_fails_on_no_progress(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    config = config.model_copy(
        update={
            "team": config.team.model_copy(update={"artifact_dir": str(tmp_path / "jobs")}),
        }
    )
    from imperaos.team.models import TeamSpec

    spec = TeamSpec.model_validate(
        {
            "version": "1",
            "team": {
                "team_id": "team-enterprise-qualification",
                "agents": [
                    {
                        "agent_id": "agent-1",
                        "role": "Intake Agent",
                        "allowed_task_types": ["plan"],
                        "profile_name": "enterprise",
                        "memory_scope_access": ["case"],
                        "tool_policy_profile": "enterprise",
                        "approval_mode": "auto",
                    }
                ],
                "handoff_rules": [],
                "termination_rules": {"max_tasks": 4, "max_retries": 1, "max_handoff_depth": 4},
            },
            "tasks": [
                {
                    "task_id": "task-intake",
                    "title": "intake",
                    "task_type": "plan",
                    "role": "Intake Agent",
                    "depends_on": [],
                    "input_template": "{{request}}",
                }
            ],
        }
    )

    class FakeSupervisor:
        def __init__(self, orchestrator, config):  # noqa: ANN001
            self.config = config

        def run(self, *, spec, request, case_id, job_id, approval_overrides=None):  # noqa: ANN001
            return SimpleNamespace(
                job=SimpleNamespace(job_id=job_id, status=SimpleNamespace(value="blocked")),
                audit_envelope_path=str(
                    Path(self.config.team.artifact_dir) / job_id / "audit_envelope.json"
                ),
            )

    monkeypatch.setattr("imperaos.enterprise.qualification.TeamSupervisor", FakeSupervisor)
    monkeypatch.setattr(
        "imperaos.enterprise.qualification.load_events",
        lambda job_id, root_dir: [{"event": "task_blocked", "task_id": "task-review"}],
    )
    monkeypatch.setattr(
        "imperaos.enterprise.qualification.replay_job",
        lambda job_id, root_dir, verify=True: {"verified": True, "event_count": 1},
    )
    monkeypatch.setattr(
        "imperaos.enterprise.qualification._collect_resume_overrides",
        lambda *, events, governance_runtime: ({}, []),
    )

    try:
        _run_terminal_positive_smoke(
            name="baseline_enterprise_flow",
            spec=spec,
            config=config,
            orchestrator_builder=lambda runtime_config: SimpleNamespace(
                governance_runtime=object()
            ),
            actor="qualification-runner",
        )
    except QualificationFailure as exc:
        assert exc.error_code == "QUALIFICATION_RESUME_NO_PROGRESS"
    else:
        raise AssertionError("expected QualificationFailure")


def test_merge_qualification_report_rejects_runtime_mismatch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    payload = _complete_green_qualification_payload()
    source_path = tmp_path / "artifacts" / "qualification_report.json"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    write_signed_json(
        path=source_path,
        artifact="qualification_report",
        data=payload,
        config=config,
        purpose="qualification-report",
        status="ok",
    )

    rerun_payload = dict(payload)
    rerun_payload["runtime_version"] = "mismatch"
    rerun_payload["generated_at"] = datetime.now(UTC).isoformat()

    try:
        _merge_qualification_report(
            existing_report_path=source_path,
            rerun_payload=rerun_payload,
            rerun_names=["baseline_enterprise_flow"],
            config=config,
        )
    except QualificationFailure as exc:
        assert exc.error_code == "QUALIFICATION_SOURCE_REPORT_MISMATCH"


def test_resolve_merge_from_report_path_falls_back_to_latest_signed_report(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    payload = _complete_green_qualification_payload()
    run_dir = tmp_path / "artifacts" / "qualification" / "qualification-20260307122217"
    run_dir.mkdir(parents=True, exist_ok=True)
    write_signed_json(
        path=run_dir / "qualification_report.json",
        artifact="qualification_report",
        data=payload,
        config=config,
        purpose="qualification-report",
        status="ok",
    )

    resolved = _resolve_merge_from_report_path("artifacts/qualification_report.json", config=config)

    assert resolved.resolve() == (run_dir / "qualification_report.json").resolve()


def test_subset_qualification_run_merges_failed_workloads(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    signing = _write_signing_material(tmp_path)
    _write_identity_assertion(
        tmp_path,
        signing,
        permissions=[
            "runtime.run",
            "approval.decide",
            "approval.execute",
            "support.export",
            "backup.create",
            "restore.verify",
        ],
    )
    _write_enterprise_docs(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    existing_payload = _complete_green_qualification_payload()
    existing_payload["workloads"] = [
        {
            **item,
            "pass_fail": "fail",
            "evidence_verified": False,
            "blocking_findings": ["PILOT_SMOKE_EXPECTED_COMPLETED"],
            "support_classification": "unsupported",
        }
        if item["name"] in {"baseline_enterprise_flow", "failure_injection_flow"}
        else item
        for item in existing_payload["workloads"]
    ]
    evaluation = evaluate_qualification_evidence(
        qualification_payload={
            "profile": "enterprise",
            "workloads": existing_payload["workloads"],
            "minimum_green_soak_seconds": MIN_GREEN_SOAK_SECONDS,
        }
    )
    existing_payload.update(
        {
            "qualification_status": evaluation["qualification_status"],
            "supported_profiles": evaluation["supported_profiles"],
            "conditional_profiles": evaluation["conditional_profiles"],
            "unsupported_profiles": evaluation["unsupported_profiles"],
            "blocking_findings": evaluation["blocking_findings"],
            "residual_risks": evaluation["residual_risks"],
            "recommended_status": evaluation["recommended_status"],
            "go_no_go": evaluation["go_no_go"],
            "operational_findings": evaluation["operational_findings"],
        }
    )
    source_path = tmp_path / "artifacts" / "qualification_report.json"
    write_signed_json(
        path=source_path,
        artifact="qualification_report",
        data=existing_payload,
        config=config,
        purpose="qualification-report",
        status="error",
    )

    def fake_green_baseline(**kwargs):  # noqa: ANN003
        return {
            **_green_workload("baseline_enterprise_flow", duration_seconds=120),
            "execution_mode": "live_provider",
            "terminal_status": "completed",
            "terminal_job_id": "baseline_enterprise_flow-resume-2",
            "resume_round_count": 2,
            "approval_rounds": [{"round": 1}, {"round": 2}],
        }

    def fake_green_failure(**kwargs):  # noqa: ANN003
        return {
            **_green_workload("failure_injection_flow", duration_seconds=120),
            "execution_mode": "mixed",
            "terminal_status": "completed",
            "terminal_job_id": "failure_injection_flow-resume-2",
            "resume_round_count": 2,
            "approval_rounds": [{"round": 1}, {"round": 2}],
        }

    monkeypatch.setattr(
        "imperaos.enterprise.qualification._run_baseline_enterprise_flow",
        fake_green_baseline,
    )
    monkeypatch.setattr(
        "imperaos.enterprise.qualification._run_failure_injection_flow",
        fake_green_failure,
    )

    payload = run_qualification(
        config=config,
        mode="mixed",
        soak_hours=0.0003,
        output_root=tmp_path / "artifacts" / "qualification",
        live_orchestrator_builder=build_deterministic_pilot_orchestrator,
        workloads=["baseline_enterprise_flow", "failure_injection_flow"],
        merge_from_report=source_path,
    )
    paths = write_qualification_report(
        payload=payload,
        config=config,
        output_root=tmp_path / "artifacts" / "qualification",
    )

    verify = verify_signed_artifact(path=paths["latest_json"], config=config)
    assert verify["verified"] is True
    assert payload["go_no_go"] == "go"
    readiness = ga_readiness_report(config)
    assert readiness["overall_status"] == "green"
    assert readiness["go_no_go"] == "go"
