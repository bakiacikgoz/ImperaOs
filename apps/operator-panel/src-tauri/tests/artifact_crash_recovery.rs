use imperaos_operator_panel_lib::artifact_rpc::{
    build_trusted_request, TrustedArtifactIdentity, WorkspaceRpcLaunch, WorkspaceRpcSupervisor,
};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::fs;
use std::path::Path;
use std::time::{Duration, Instant};
use tempfile::tempdir;

fn document(text: &str) -> Value {
    json!({
        "kind": "document",
        "schemaVersion": 1,
        "language": "tr",
        "pageMode": "document",
        "blocks": [{
            "id": "block-1",
            "type": "paragraph",
            "content": [{"type": "text", "text": text}]
        }]
    })
}

fn count_files(root: &Path) -> usize {
    if !root.exists() {
        return 0;
    }
    fs::read_dir(root)
        .expect("storage directory must be readable")
        .map(|entry| entry.expect("storage entry must be readable").path())
        .map(|path| if path.is_dir() { count_files(&path) } else { 1 })
        .sum()
}

#[test]
fn supervisor_recovers_a_real_python_crash_after_content_publish() {
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .expect("test runtime must start");
    runtime.block_on(async {
        let worktree_root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(Path::parent)
            .and_then(Path::parent)
            .expect("manifest must be below the worktree root");
        let fixture = worktree_root.join("tests/artifact_rpc_crash_sidecar.py");
        assert!(fixture.is_file(), "crash sidecar fixture must exist");

        let python = std::env::var("IMPERAOS_TEST_PYTHON").unwrap_or_else(|_| {
            let relative = if cfg!(windows) {
                ".venv/Scripts/python.exe"
            } else {
                ".venv/bin/python"
            };
            worktree_root.join(relative).to_string_lossy().into_owned()
        });
        assert!(
            Path::new(&python).is_file(),
            "project Python must exist or IMPERAOS_TEST_PYTHON must be set"
        );
        let temp = tempdir().expect("temporary storage root must be created");
        let artifact_root = temp.path().join("artifacts");
        let mut env = HashMap::new();
        env.insert(
            "PYTHONPATH".to_string(),
            worktree_root.to_string_lossy().into_owned(),
        );
        env.insert("PYTHONUTF8".to_string(), "1".to_string());
        env.insert(
            "IMPERAOS_ARTIFACT_CRASH_AFTER_PUBLISH_REVISION".to_string(),
            "2".to_string(),
        );
        let launch = WorkspaceRpcLaunch::new(
            python,
            vec![fixture.to_string_lossy().into_owned()],
            &artifact_root,
            "enterprise",
        )
        .expect("fixture launch must be valid")
        .with_env(env)
        .expect("fixture environment must be valid");
        let supervisor = WorkspaceRpcSupervisor::new(launch);
        let identity = TrustedArtifactIdentity::new(
            "workspace-1",
            "user-1",
            "user",
            vec!["artifact_admin".to_string()],
        )
        .expect("test identity must be valid");

        let initial = supervisor
            .start()
            .await
            .expect("sidecar handshake must succeed");
        let initial_pid = initial
            .process_id
            .expect("sidecar must expose a process id");
        let create = build_trusted_request(
            "artifact.create",
            json!({
                "artifactId": "artifact-crash-drill",
                "kind": "document",
                "title": "Crash drill",
                "dataClass": "internal",
                "content": document("revision-one"),
                "idempotencyKey": "crash-create-1"
            }),
            &identity,
            Some("crash-create-1".to_string()),
            5_000,
        )
        .expect("create request must be valid");
        supervisor
            .call(create, Duration::from_secs(5))
            .await
            .expect("initial revision must be committed");

        let mutate = build_trusted_request(
            "artifact.mutate",
            json!({
                "artifactId": "artifact-crash-drill",
                "expectedRevisionNumber": 1,
                "mutationType": "replace_content",
                "content": document("revision-two-private-canary"),
                "idempotencyKey": "crash-mutate-2",
                "changeSummary": "real process crash drill"
            }),
            &identity,
            Some("crash-mutate-2".to_string()),
            5_000,
        )
        .expect("mutate request must be valid");
        let crashed = supervisor
            .call(mutate.clone(), Duration::from_secs(5))
            .await
            .expect_err("sidecar must die after publishing revision two content");
        assert_eq!(crashed.code, "ARTIFACT_RPC_UNAVAILABLE");
        assert!(crashed.retryable);

        let restart_started = Instant::now();
        let replay = supervisor
            .call(mutate, Duration::from_secs(5))
            .await
            .expect("same idempotent mutation must succeed after restart reconciliation");
        assert!(restart_started.elapsed() <= Duration::from_secs(3));
        assert_eq!(
            replay
                .pointer("/revision/revisionNumber")
                .and_then(Value::as_u64),
            Some(2)
        );

        let recovered = supervisor
            .health()
            .await
            .expect("recovered sidecar must be healthy");
        assert_ne!(recovered.process_id, Some(initial_pid));
        assert_eq!(recovered.restart_count, 1);
        assert!(!recovered.circuit_open);

        let history = build_trusted_request(
            "artifact.history",
            json!({"artifactId": "artifact-crash-drill", "limit": 10}),
            &identity,
            None,
            5_000,
        )
        .expect("history request must be valid");
        let history = supervisor
            .call(history, Duration::from_secs(5))
            .await
            .expect("history must remain readable");
        let items = history
            .get("items")
            .and_then(Value::as_array)
            .expect("history must contain revision items");
        assert_eq!(items.len(), 2);
        assert_eq!(items[0]["revisionNumber"], 2);
        assert_eq!(items[1]["revisionNumber"], 1);
        assert_eq!(count_files(&artifact_root.join("tmp")), 0);
        assert!(count_files(&artifact_root.join("quarantine")) >= 1);

        supervisor
            .shutdown()
            .await
            .expect("recovered sidecar must shut down cleanly");
    });
}
