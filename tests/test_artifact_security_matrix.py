from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ATTACK_CLASSES = {
    "path_traversal",
    "symlink_escape",
    "prototype_pollution",
    "remote_ref",
    "redos",
    "xss",
    "svg_script",
    "formula_injection",
    "oversize",
    "event_spoof",
    "cross_workspace",
    "approval_bypass",
    "license_bypass",
    "secret_leakage",
    "path_leakage",
}


def test_adversarial_fixture_covers_the_complete_security_matrix() -> None:
    fixture = json.loads(
        (ROOT / "contracts/artifacts/fixtures/security-adversarial.v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert fixture["version"] == "1"
    cases = fixture["cases"]
    assert {case["category"] for case in cases} == EXPECTED_ATTACK_CLASSES
    assert len(cases) == len(EXPECTED_ATTACK_CLASSES)
    assert all(case["sample"] and case["expected"] for case in cases)


def test_production_csp_and_enabled_editors_have_offline_proof() -> None:
    tauri = json.loads(
        (ROOT / "apps/operator-panel/src-tauri/tauri.conf.json").read_text(
            encoding="utf-8"
        )
    )
    csp = tauri["app"]["security"]["csp"]

    assert "script-src 'self'" in csp
    assert "worker-src 'self' blob:" in csp
    assert "connect-src ipc: http://ipc.localhost" in csp
    assert "unsafe-eval" not in csp
    assert "https:" not in csp
    assert "frame-src 'none'" in csp
    assert "object-src 'none'" in csp

    for name in ("document", "form", "code", "flow"):
        spec = (ROOT / f"apps/operator-panel/e2e/artifact-{name}.spec.ts").read_text(
            encoding="utf-8"
        )
        assert "setOffline(true)" in spec, name
        assert "Requests).toEqual([])" in spec, name
