from pathlib import Path

import pytest

from imperaos.enterprise.observability import write_prometheus_textfile
from imperaos.runtime.config import RuntimeConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
FORMER_BRAND = "bin" + "liquid"
FORMER_DISPLAY_NAME = "Bin" + "Liquid"


def test_prometheus_textfile_uses_exact_imperaos_metric_snapshot(tmp_path: Path) -> None:
    snapshot = {
        "approval_queue": {"pending": 2, "oldest_pending_age_s": 17},
        "audit": {
            "audit_inconsistency_count": 3,
            "replay_verify_failure_count": 5,
        },
        "concurrency": {
            "memory_conflict_count": 7,
            "fallback_mode_count": 11,
        },
        "control_plane": {
            "control_plane_agents_registered": 13,
            "control_plane_claims_blocked": 19,
        },
    }
    destination = tmp_path / "imperaos.prom"

    result = write_prometheus_textfile(snapshot, destination)

    assert result == str(destination)
    assert destination.read_text(encoding="utf-8") == (
        "imperaos_approval_pending 2\n"
        "imperaos_approval_oldest_age_seconds 17\n"
        "imperaos_audit_inconsistency_total 3\n"
        "imperaos_replay_verify_failure_total 5\n"
        "imperaos_memory_conflict_total 7\n"
        "imperaos_fallback_mode_total 11\n"
        "imperaos_control_plane_agents_registered 13\n"
        "imperaos_control_plane_claims_blocked 19\n"
    )


def test_enterprise_prometheus_path_uses_imperaos_state_root_and_filename() -> None:
    path = RuntimeConfig.from_profile("enterprise").observability.prometheus_textfile_path

    assert path == ".imperaos/enterprise/metrics/imperaos.prom"


@pytest.mark.parametrize(
    ("relative_path", "required_identities", "forbidden_identities"),
    [
        (
            "imperaos/enterprise/observability.py",
            ("imperaos_approval_pending", "imperaos_control_plane_claims_blocked"),
            (f"{FORMER_BRAND}_approval_pending",),
        ),
        (
            "scripts/launch_resilient_qualification_soak.sh",
            ('/private/tmp/imperaos_soak_${RUN_ID}', 'copy_item "imperaos"'),
            (
                f'/private/tmp/{FORMER_BRAND}_soak_${{RUN_ID}}',
                f'copy_item "{FORMER_BRAND}"',
            ),
        ),
        (
            "scripts/run_qualification_soak_supervised.sh",
            ("com.imperaos.qualification-soak.",),
            (f"com.{FORMER_BRAND}.qualification-soak.",),
        ),
        (
            "scripts/watch_qualification_soak.sh",
            (
                "/private/tmp/imperaos_soak_*",
                'glob("imperaos_soak_*")',
                "ImperaOS Qualification Soak Monitor",
            ),
            (
                f"/private/tmp/{FORMER_BRAND}_soak_*",
                f'glob("{FORMER_BRAND}_soak_*")',
                f"{FORMER_DISPLAY_NAME} Qualification Soak Monitor",
            ),
        ),
        (
            "scripts/bootstrap_macos.sh",
            ("/tmp/imperaos-ollama.log",),
            (f"/tmp/{FORMER_BRAND}-ollama.log",),
        ),
        (
            "scripts/demo_governance_v03.sh",
            ("/tmp/imperaos_v03_demo.json",),
            (f"/tmp/{FORMER_BRAND}_v03_demo.json",),
        ),
        (
            "scripts/evaluate_computer_use_integration_gate.py",
            ("imperaos_gate_", "imperaos-gate-ascii", "ImperaOS Gate Space"),
            (
                f"{FORMER_BRAND}_gate_",
                f"{FORMER_BRAND}-gate-ascii",
                f"{FORMER_DISPLAY_NAME} Gate Space",
            ),
        ),
        (
            "docs/OPERATIONS_RUNBOOK.md",
            ("/private/tmp/imperaos_soak_final72h-",),
            (f"/private/tmp/{FORMER_BRAND}_soak_final72h-",),
        ),
    ],
)
def test_active_operational_identity_is_imperaos(
    relative_path: str,
    required_identities: tuple[str, ...],
    forbidden_identities: tuple[str, ...],
) -> None:
    contents = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    for identity in required_identities:
        assert identity in contents
    for identity in forbidden_identities:
        assert identity not in contents
