from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE = REPO_ROOT / "apps/operator-panel/src-tauri/src/bridge.rs"
LIB = REPO_ROOT / "apps/operator-panel/src-tauri/src/lib.rs"
SUPERVISOR = REPO_ROOT / "apps/operator-panel/src-tauri/src/artifact_rpc.rs"

EXPECTED_COMMANDS = {
    "bridge_artifact_list",
    "bridge_artifact_get",
    "bridge_artifact_create",
    "bridge_artifact_mutate",
    "bridge_artifact_propose_mutation",
    "bridge_artifact_apply_proposal",
    "bridge_artifact_history",
    "bridge_artifact_restore",
    "bridge_artifact_archive",
    "bridge_artifact_duplicate",
    "bridge_artifact_asset_import",
    "bridge_artifact_form_submit",
    "bridge_artifact_export_begin",
    "bridge_artifact_export_commit",
    "bridge_artifact_export_cancel",
    "bridge_artifact_import_evidence",
}


def test_tauri_artifact_command_allowlist_and_handler_registration_are_complete() -> None:
    bridge = BRIDGE.read_text(encoding="utf-8")
    lib = LIB.read_text(encoding="utf-8")

    for command in EXPECTED_COMMANDS:
        assert f"artifact_bridge_command!({command}," in bridge or command in bridge
        assert f"bridge::{command}," in lib


def test_renderer_payload_cannot_supply_artifact_identity_or_shell_command() -> None:
    bridge = BRIDGE.read_text(encoding="utf-8")
    supervisor = SUPERVISOR.read_text(encoding="utf-8")
    payload = bridge.split("pub struct ArtifactBridgePayload", 1)[1].split("}", 1)[0]

    assert "deny_unknown_fields" in bridge
    assert "principal" not in payload
    assert "workspace" not in payload
    assert 'std::env::var("IMPERAOS_WORKSPACE_ID")' in bridge
    assert "Command::new(&self.launch.program)" in supervisor
    assert 'Command::new("sh")' not in supervisor
    assert '.arg("-c")' not in supervisor


def test_approval_read_surfaces_use_trusted_workspace_identity() -> None:
    bridge = BRIDGE.read_text(encoding="utf-8")
    pending = bridge.split("pub async fn bridge_approval_pending", 1)[1].split(
        "pub async fn bridge_approval_show", 1
    )[0]
    show = bridge.split("pub async fn bridge_approval_show", 1)[1].split(
        "pub async fn bridge_approval_decide", 1
    )[0]

    for command in (pending, show):
        assert "app: tauri::AppHandle" in command
        assert "resolve_trusted_artifact_identity" in command
        assert '"--workspace-id"' in command
