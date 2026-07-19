use std::{fs, path::PathBuf};

fn manifest_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

#[test]
fn desktop_metadata_uses_imperaos_identity() {
    let root = manifest_root();
    let cargo = fs::read_to_string(root.join("Cargo.toml")).expect("Cargo.toml");
    let tauri: serde_json::Value = serde_json::from_str(
        &fs::read_to_string(root.join("tauri.conf.json")).expect("tauri.conf.json"),
    )
    .expect("valid tauri config");

    assert!(cargo.contains("name = \"imperaos_operator_panel\""));
    assert!(cargo.contains("name = \"imperaos_operator_panel_lib\""));
    assert!(cargo.contains("description = \"ImperaOS Operator Panel\""));
    assert!(cargo.contains("authors = [\"ImperaOS Contributors\"]"));
    assert_eq!(tauri["productName"], "ImperaOS Operator Panel");
    assert_eq!(tauri["identifier"], "com.imperaos.operatorpanel");
    assert_eq!(
        tauri["app"]["windows"][0]["title"],
        "ImperaOS Operator Panel"
    );
}
