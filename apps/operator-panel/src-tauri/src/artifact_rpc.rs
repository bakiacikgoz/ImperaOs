use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};
use tokio::sync::Mutex;

const RPC_CONTRACT_VERSION: &str = "1.0";
const RPC_MAX_FRAME_BYTES: usize = 32 * 1024 * 1024;
const RPC_HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(5);
const RPC_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(2);
const MAX_RESTART_ATTEMPTS: u8 = 3;
const ALLOWED_ARTIFACT_METHODS: &[&str] = &[
    "artifact.list",
    "artifact.get",
    "artifact.create",
    "artifact.mutate",
    "artifact.slides.patch",
    "artifact.propose_mutation",
    "artifact.apply_proposal",
    "artifact.history",
    "artifact.restore",
    "artifact.archive",
    "artifact.duplicate",
    "artifact.asset.import",
    "artifact.asset.get",
    "artifact.form.submit",
    "artifact.export.begin",
    "artifact.export.preflight",
    "artifact.export.commit",
    "artifact.export.cancel",
    "artifact.import_evidence",
];
const MUTATION_METHODS_WITH_KEYS: &[&str] = &[
    "artifact.create",
    "artifact.mutate",
    "artifact.slides.patch",
    "artifact.propose_mutation",
    "artifact.restore",
    "artifact.duplicate",
    "artifact.asset.import",
    "artifact.import_evidence",
    "artifact.form.submit",
    "artifact.export.begin",
    "artifact.export.preflight",
    "artifact.export.commit",
    "artifact.export.cancel",
];
static REQUEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WorkspaceRpcLaunch {
    program: String,
    args: Vec<String>,
    artifact_root: PathBuf,
    profile: String,
    env: HashMap<String, String>,
}

impl WorkspaceRpcLaunch {
    pub fn new(
        program: impl Into<String>,
        args: Vec<String>,
        artifact_root: impl Into<PathBuf>,
        profile: impl Into<String>,
    ) -> Result<Self, SupervisorError> {
        let launch = Self {
            program: program.into(),
            args,
            artifact_root: artifact_root.into(),
            profile: profile.into(),
            env: HashMap::new(),
        };
        launch.validate()?;
        Ok(launch)
    }

    pub fn with_env(mut self, env: HashMap<String, String>) -> Result<Self, SupervisorError> {
        self.env = env;
        self.validate()?;
        Ok(self)
    }

    fn validate(&self) -> Result<(), SupervisorError> {
        if self.program.trim().is_empty() || self.program.contains('\0') {
            return Err(SupervisorError::invalid_launch());
        }
        if self.args.iter().any(|arg| arg.contains('\0')) {
            return Err(SupervisorError::invalid_launch());
        }
        let root = self.artifact_root.to_string_lossy();
        if root.trim().is_empty() || root.contains('\0') {
            return Err(SupervisorError::invalid_launch());
        }
        if self.profile.trim().is_empty() || self.profile.contains('\0') {
            return Err(SupervisorError::invalid_launch());
        }
        if self
            .env
            .iter()
            .any(|(key, value)| key.is_empty() || key.contains(['\0', '=']) || value.contains('\0'))
        {
            return Err(SupervisorError::invalid_launch());
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct TrustedArtifactIdentity {
    workspace_id: String,
    principal_id: String,
    principal_type: String,
    roles: Vec<String>,
}

impl TrustedArtifactIdentity {
    pub fn new(
        workspace_id: impl Into<String>,
        principal_id: impl Into<String>,
        principal_type: impl Into<String>,
        roles: Vec<String>,
    ) -> Result<Self, SupervisorError> {
        let identity = Self {
            workspace_id: workspace_id.into(),
            principal_id: principal_id.into(),
            principal_type: principal_type.into(),
            roles,
        };
        if !is_bounded_id(&identity.workspace_id)
            || !is_bounded_id(&identity.principal_id)
            || !matches!(
                identity.principal_type.as_str(),
                "user" | "assistant" | "system" | "import"
            )
            || identity.roles.len() > 64
            || identity.roles.iter().any(|role| !is_bounded_id(role))
        {
            return Err(SupervisorError::new(
                "ARTIFACT_PERMISSION_DENIED",
                "trusted artifact identity is invalid",
                false,
            ));
        }
        Ok(identity)
    }

    pub fn workspace_id(&self) -> &str {
        &self.workspace_id
    }

    pub fn principal_id(&self) -> &str {
        &self.principal_id
    }

    pub fn principal_type(&self) -> &str {
        &self.principal_type
    }

    pub fn roles(&self) -> &[String] {
        &self.roles
    }
}

pub fn build_trusted_request(
    method: &str,
    params: Value,
    identity: &TrustedArtifactIdentity,
    idempotency_key: Option<String>,
    deadline_ms: u64,
) -> Result<Value, SupervisorError> {
    if !ALLOWED_ARTIFACT_METHODS.contains(&method) {
        return Err(SupervisorError::protocol(
            "artifact RPC method is not allowlisted",
        ));
    }
    if !(1..=120_000).contains(&deadline_ms) {
        return Err(SupervisorError::protocol(
            "artifact RPC deadline is outside its boundary",
        ));
    }
    let params_object = params
        .as_object()
        .ok_or_else(|| SupervisorError::protocol("artifact RPC params must be an object"))?;
    if [
        "principal",
        "principalId",
        "principalType",
        "roles",
        "workspaceId",
    ]
    .iter()
    .any(|key| params_object.contains_key(*key))
    {
        return Err(SupervisorError::new(
            "ARTIFACT_PERMISSION_DENIED",
            "renderer params cannot override trusted artifact identity",
            false,
        ));
    }
    if let Some(key) = idempotency_key.as_ref() {
        if !is_bounded_id(key) {
            return Err(SupervisorError::protocol(
                "artifact RPC idempotency key is invalid",
            ));
        }
    }
    if MUTATION_METHODS_WITH_KEYS.contains(&method)
        && (idempotency_key.is_none()
            || params_object.get("idempotencyKey").and_then(Value::as_str)
                != idempotency_key.as_deref())
    {
        return Err(SupervisorError::protocol(
            "artifact RPC mutation idempotency key is not envelope-bound",
        ));
    }
    let sequence = REQUEST_SEQUENCE.fetch_add(1, Ordering::Relaxed) + 1;
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    Ok(json!({
        "contractVersion": RPC_CONTRACT_VERSION,
        "requestId": format!("tauri-{timestamp}-{sequence}"),
        "method": method,
        "workspaceId": identity.workspace_id,
        "principal": {
            "principalId": identity.principal_id,
            "principalType": identity.principal_type,
            "roles": identity.roles,
        },
        "idempotencyKey": idempotency_key,
        "deadlineMs": deadline_ms,
        "params": params,
    }))
}

fn is_bounded_id(value: &str) -> bool {
    if value.is_empty() || value.len() > 128 {
        return false;
    }
    let mut characters = value.chars();
    let Some(first) = characters.next() else {
        return false;
    };
    first.is_ascii_alphanumeric()
        && characters.all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '.' | '_' | '-')
        })
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct SupervisorError {
    pub code: String,
    pub message: String,
    pub retryable: bool,
}

impl SupervisorError {
    fn new(code: &str, message: &str, retryable: bool) -> Self {
        Self {
            code: code.to_string(),
            message: message.to_string(),
            retryable,
        }
    }

    fn invalid_launch() -> Self {
        Self::new(
            "ARTIFACT_RPC_UNAVAILABLE",
            "artifact RPC launch configuration is invalid",
            false,
        )
    }

    fn protocol(message: &str) -> Self {
        Self::new("ARTIFACT_RPC_PROTOCOL_MISMATCH", message, false)
    }

    fn unavailable(message: &str, retryable: bool) -> Self {
        Self::new("ARTIFACT_RPC_UNAVAILABLE", message, retryable)
    }
}

#[derive(Debug, Default)]
struct RestartCircuit {
    consecutive_failures: u8,
    open: bool,
}

impl RestartCircuit {
    fn record_failure(&mut self) -> bool {
        self.consecutive_failures = self.consecutive_failures.saturating_add(1);
        if self.consecutive_failures >= MAX_RESTART_ATTEMPTS {
            self.open = true;
        }
        self.open
    }

    fn record_application_response(&mut self) {
        self.consecutive_failures = 0;
    }

    fn is_open(&self) -> bool {
        self.open
    }
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct RpcHealth {
    pub status: String,
    pub protocol_version: String,
    pub max_frame_bytes: usize,
    pub restart_count: u32,
    pub circuit_open: bool,
    pub process_id: Option<u32>,
    pub metrics: HashMap<String, u64>,
}

struct WorkspaceRpcProcess {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    max_frame_bytes: usize,
}

#[derive(Default)]
struct SupervisorState {
    process: Option<WorkspaceRpcProcess>,
    circuit: RestartCircuit,
    restart_count: u32,
    request_sequence: u64,
}

pub struct WorkspaceRpcSupervisor {
    launch: WorkspaceRpcLaunch,
    state: Mutex<SupervisorState>,
}

#[derive(Default)]
pub struct WorkspaceRpcRegistry {
    supervisor: Mutex<Option<Arc<WorkspaceRpcSupervisor>>>,
}

impl WorkspaceRpcRegistry {
    pub async fn get_or_start(
        &self,
        launch: WorkspaceRpcLaunch,
    ) -> Result<Arc<WorkspaceRpcSupervisor>, SupervisorError> {
        let stale = {
            let mut guard = self.supervisor.lock().await;
            match guard.as_ref() {
                Some(supervisor) if supervisor.launch != launch => guard.take(),
                _ => None,
            }
        };
        if let Some(supervisor) = stale {
            supervisor.shutdown().await?;
        }
        let supervisor = {
            let mut guard = self.supervisor.lock().await;
            guard
                .get_or_insert_with(|| Arc::new(WorkspaceRpcSupervisor::new(launch)))
                .clone()
        };
        supervisor.start().await?;
        Ok(supervisor)
    }

    pub async fn shutdown(&self) -> Result<(), SupervisorError> {
        let supervisor = self.supervisor.lock().await.take();
        if let Some(supervisor) = supervisor {
            supervisor.shutdown().await?;
        }
        Ok(())
    }
}

impl WorkspaceRpcSupervisor {
    pub fn new(launch: WorkspaceRpcLaunch) -> Self {
        Self {
            launch,
            state: Mutex::new(SupervisorState::default()),
        }
    }

    pub async fn start(&self) -> Result<RpcHealth, SupervisorError> {
        let mut state = self.state.lock().await;
        if state.circuit.is_open() {
            return Err(SupervisorError::unavailable(
                "artifact RPC restart circuit is open",
                false,
            ));
        }
        if let Some(process) = state.process.as_mut() {
            match process.child.try_wait() {
                Ok(None) => return Ok(Self::health_snapshot(&state)),
                Ok(Some(_)) | Err(_) => {
                    state.process = None;
                    state.restart_count = state.restart_count.saturating_add(1);
                    state.circuit.record_failure();
                }
            }
        }
        if state.circuit.is_open() {
            return Err(SupervisorError::unavailable(
                "artifact RPC restart circuit is open",
                false,
            ));
        }

        let mut process = match self.spawn_process().await {
            Ok(process) => process,
            Err(error) => {
                state.restart_count = state.restart_count.saturating_add(1);
                state.circuit.record_failure();
                return Err(error);
            }
        };
        state.request_sequence = state.request_sequence.saturating_add(1);
        let request_id = format!("supervisor-handshake-{}", state.request_sequence);
        let handshake = json!({
            "contractVersion": RPC_CONTRACT_VERSION,
            "requestId": request_id,
            "method": "rpc.handshake",
            "workspaceId": "system",
            "principal": {
                "principalId": "tauri-supervisor",
                "principalType": "system",
                "roles": ["artifact_admin"]
            },
            "idempotencyKey": null,
            "deadlineMs": 5000,
            "params": {}
        });
        let response = match tokio::time::timeout(
            RPC_HANDSHAKE_TIMEOUT,
            exchange(&mut process, &handshake, &request_id),
        )
        .await
        {
            Ok(Ok(response)) => response,
            Ok(Err(error)) => {
                state.restart_count = state.restart_count.saturating_add(1);
                state.circuit.record_failure();
                return Err(error);
            }
            Err(_) => {
                state.restart_count = state.restart_count.saturating_add(1);
                state.circuit.record_failure();
                return Err(SupervisorError::unavailable(
                    "artifact RPC handshake timed out",
                    true,
                ));
            }
        };
        let handshake_result = match validate_handshake(&response) {
            Ok(handshake) => handshake,
            Err(error) => {
                state.restart_count = state.restart_count.saturating_add(1);
                state.circuit.record_failure();
                return Err(error);
            }
        };
        process.max_frame_bytes = handshake_result.max_frame_bytes;
        state.process = Some(process);
        Ok(Self::health_snapshot(&state))
    }

    pub async fn call(&self, request: Value, timeout: Duration) -> Result<Value, SupervisorError> {
        self.start().await?;
        let request_id = request
            .get("requestId")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| SupervisorError::protocol("artifact RPC request ID is missing"))?
            .to_string();
        if request.get("contractVersion").and_then(Value::as_str) != Some(RPC_CONTRACT_VERSION) {
            return Err(SupervisorError::protocol(
                "artifact RPC request contract version is unsupported",
            ));
        }

        let mut state = self.state.lock().await;
        let outcome = {
            let process = state.process.as_mut().ok_or_else(|| {
                SupervisorError::unavailable("artifact RPC process is unavailable", true)
            })?;
            tokio::time::timeout(timeout, exchange(process, &request, &request_id)).await
        };
        match outcome {
            Ok(Ok(response)) => {
                state.circuit.record_application_response();
                response.into_result()
            }
            Ok(Err(error)) => {
                self.invalidate_process(&mut state).await;
                Err(error)
            }
            Err(_) => {
                self.invalidate_process(&mut state).await;
                Err(SupervisorError::unavailable(
                    "artifact RPC request timed out",
                    true,
                ))
            }
        }
    }

    pub async fn health(&self) -> Result<RpcHealth, SupervisorError> {
        self.start().await
    }

    pub async fn shutdown(&self) -> Result<(), SupervisorError> {
        let mut state = self.state.lock().await;
        let Some(mut process) = state.process.take() else {
            return Ok(());
        };
        state.request_sequence = state.request_sequence.saturating_add(1);
        let request_id = format!("supervisor-shutdown-{}", state.request_sequence);
        let request = json!({
            "contractVersion": RPC_CONTRACT_VERSION,
            "requestId": request_id,
            "method": "rpc.shutdown",
            "workspaceId": "system",
            "principal": {
                "principalId": "tauri-supervisor",
                "principalType": "system",
                "roles": ["artifact_admin"]
            },
            "idempotencyKey": null,
            "deadlineMs": 2000,
            "params": {}
        });
        let _ = tokio::time::timeout(
            RPC_SHUTDOWN_TIMEOUT,
            exchange(&mut process, &request, &request_id),
        )
        .await;
        if tokio::time::timeout(RPC_SHUTDOWN_TIMEOUT, process.child.wait())
            .await
            .is_err()
        {
            process
                .child
                .kill()
                .await
                .map_err(|_| SupervisorError::unavailable("artifact RPC shutdown failed", true))?;
        }
        Ok(())
    }

    async fn spawn_process(&self) -> Result<WorkspaceRpcProcess, SupervisorError> {
        self.launch.validate()?;
        let mut command = Command::new(&self.launch.program);
        command
            .args(&self.launch.args)
            .arg("workspace-rpc")
            .arg("--stdio-json")
            .arg("--profile")
            .arg(&self.launch.profile)
            .arg("--root")
            .arg(&self.launch.artifact_root)
            .envs(&self.launch.env)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);
        let mut child = command.spawn().map_err(|_| {
            SupervisorError::unavailable("artifact RPC process failed to start", true)
        })?;
        let stdin = child.stdin.take().ok_or_else(|| {
            SupervisorError::unavailable("artifact RPC stdin is unavailable", true)
        })?;
        let stdout = child.stdout.take().ok_or_else(|| {
            SupervisorError::unavailable("artifact RPC stdout is unavailable", true)
        })?;
        if let Some(mut stderr) = child.stderr.take() {
            tokio::spawn(async move {
                let mut buffer = [0_u8; 4096];
                loop {
                    match stderr.read(&mut buffer).await {
                        Ok(0) | Err(_) => break,
                        Ok(_) => {}
                    }
                }
            });
        }
        Ok(WorkspaceRpcProcess {
            child,
            stdin,
            stdout: BufReader::new(stdout),
            max_frame_bytes: RPC_MAX_FRAME_BYTES,
        })
    }

    async fn invalidate_process(&self, state: &mut SupervisorState) {
        if let Some(mut process) = state.process.take() {
            let _ = process.child.kill().await;
        }
        state.restart_count = state.restart_count.saturating_add(1);
        state.circuit.record_failure();
    }

    fn health_snapshot(state: &SupervisorState) -> RpcHealth {
        let metrics = HashMap::from([(
            "imperaos_artifact_rpc_restart_total".to_string(),
            u64::from(state.restart_count),
        )]);
        RpcHealth {
            status: if state.circuit.is_open() {
                "circuit_open".to_string()
            } else {
                "ready".to_string()
            },
            protocol_version: RPC_CONTRACT_VERSION.to_string(),
            max_frame_bytes: state
                .process
                .as_ref()
                .map(|process| process.max_frame_bytes)
                .unwrap_or(RPC_MAX_FRAME_BYTES),
            restart_count: state.restart_count,
            circuit_open: state.circuit.is_open(),
            process_id: state
                .process
                .as_ref()
                .and_then(|process| process.child.id()),
            metrics,
        }
    }
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RpcResponseEnvelope {
    contract_version: String,
    request_id: String,
    ok: bool,
    result: Option<Value>,
    error: Option<RpcErrorEnvelope>,
    server_sequence: u64,
}

impl RpcResponseEnvelope {
    fn validate(&self, request_id: &str) -> Result<(), SupervisorError> {
        if self.contract_version != RPC_CONTRACT_VERSION || self.request_id != request_id {
            return Err(SupervisorError::protocol(
                "artifact RPC response identity or version mismatched",
            ));
        }
        if self.server_sequence == 0
            || (self.ok && (self.result.is_none() || self.error.is_some()))
            || (!self.ok && (self.error.is_none() || self.result.is_some()))
        {
            return Err(SupervisorError::protocol(
                "artifact RPC response outcome is invalid",
            ));
        }
        Ok(())
    }

    fn into_result(self) -> Result<Value, SupervisorError> {
        if self.ok {
            return self
                .result
                .ok_or_else(|| SupervisorError::protocol("artifact RPC result is missing"));
        }
        let error = self
            .error
            .ok_or_else(|| SupervisorError::protocol("artifact RPC error is missing"))?;
        Err(SupervisorError::new(
            &error.code,
            &error.message,
            error.retryable,
        ))
    }
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RpcErrorEnvelope {
    code: String,
    message: String,
    retryable: bool,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RpcHandshakeResult {
    contract_version: String,
    transport: String,
    max_frame_bytes: usize,
    network_listener: bool,
    stdout_protocol_only: bool,
    graceful_shutdown: bool,
    license_capabilities: Vec<RpcLicenseCapability>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RpcLicenseCapability {
    contract_version: String,
    kind: String,
    enabled: bool,
    reason_code: String,
}

fn validate_handshake(
    response: &RpcResponseEnvelope,
) -> Result<RpcHandshakeResult, SupervisorError> {
    let result = response
        .result
        .as_ref()
        .ok_or_else(|| SupervisorError::protocol("artifact RPC handshake result is missing"))?;
    let handshake: RpcHandshakeResult = serde_json::from_value(result.clone())
        .map_err(|_| SupervisorError::protocol("artifact RPC handshake shape is invalid"))?;
    let safe_license_capabilities = handshake.license_capabilities.len() == 2
        && handshake
            .license_capabilities
            .iter()
            .any(|item| item.kind == "spreadsheet")
        && handshake
            .license_capabilities
            .iter()
            .any(|item| item.kind == "canvas")
        && handshake.license_capabilities.iter().all(|capability| {
            capability.contract_version == "artifact-license-capability/v1"
                && matches!(capability.kind.as_str(), "spreadsheet" | "canvas")
                && capability.reason_code.starts_with("ARTIFACT_LICENSE_")
                && (capability.enabled == (capability.reason_code == "ARTIFACT_LICENSE_ENABLED"))
        });
    if handshake.contract_version != RPC_CONTRACT_VERSION
        || handshake.transport != "stdio-length-prefixed-json"
        || handshake.max_frame_bytes == 0
        || handshake.max_frame_bytes > RPC_MAX_FRAME_BYTES
        || handshake.network_listener
        || !handshake.stdout_protocol_only
        || !handshake.graceful_shutdown
        || !safe_license_capabilities
    {
        return Err(SupervisorError::protocol(
            "artifact RPC handshake capabilities are unsafe or incompatible",
        ));
    }
    Ok(handshake)
}

async fn exchange(
    process: &mut WorkspaceRpcProcess,
    request: &Value,
    request_id: &str,
) -> Result<RpcResponseEnvelope, SupervisorError> {
    let payload = serde_json::to_vec(request)
        .map_err(|_| SupervisorError::protocol("artifact RPC request serialization failed"))?;
    write_frame(&mut process.stdin, &payload, process.max_frame_bytes).await?;
    let response_payload = read_frame(&mut process.stdout, process.max_frame_bytes).await?;
    let response: RpcResponseEnvelope = serde_json::from_slice(&response_payload)
        .map_err(|_| SupervisorError::protocol("artifact RPC response JSON is invalid"))?;
    response.validate(request_id)?;
    Ok(response)
}

fn encode_frame(payload: &[u8], max_frame_bytes: usize) -> Result<Vec<u8>, SupervisorError> {
    if payload.is_empty() || payload.len() > max_frame_bytes || payload.len() > u32::MAX as usize {
        return Err(SupervisorError::protocol(
            "artifact RPC frame exceeds its boundary",
        ));
    }
    let mut frame = Vec::with_capacity(4 + payload.len());
    frame.extend_from_slice(&(payload.len() as u32).to_be_bytes());
    frame.extend_from_slice(payload);
    Ok(frame)
}

async fn write_frame<W: AsyncWrite + Unpin>(
    writer: &mut W,
    payload: &[u8],
    max_frame_bytes: usize,
) -> Result<(), SupervisorError> {
    let frame = encode_frame(payload, max_frame_bytes)?;
    writer
        .write_all(&frame)
        .await
        .map_err(|_| SupervisorError::unavailable("artifact RPC write failed", true))?;
    writer
        .flush()
        .await
        .map_err(|_| SupervisorError::unavailable("artifact RPC flush failed", true))
}

async fn read_frame<R: AsyncRead + Unpin>(
    reader: &mut R,
    max_frame_bytes: usize,
) -> Result<Vec<u8>, SupervisorError> {
    let mut header = [0_u8; 4];
    reader
        .read_exact(&mut header)
        .await
        .map_err(|_| SupervisorError::unavailable("artifact RPC read failed", true))?;
    let payload_size = u32::from_be_bytes(header) as usize;
    if payload_size == 0 || payload_size > max_frame_bytes {
        return Err(SupervisorError::protocol(
            "artifact RPC frame length is invalid",
        ));
    }
    let mut payload = vec![0_u8; payload_size];
    reader
        .read_exact(&mut payload)
        .await
        .map_err(|_| SupervisorError::unavailable("artifact RPC frame is incomplete", true))?;
    Ok(payload)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn launch_contract_rejects_shell_like_or_empty_inputs() {
        assert!(
            WorkspaceRpcLaunch::new("", Vec::new(), ".imperaos/artifacts", "enterprise").is_err()
        );
        assert!(WorkspaceRpcLaunch::new(
            "python",
            vec!["bad\0arg".to_string()],
            ".imperaos/artifacts",
            "enterprise"
        )
        .is_err());
        assert!(WorkspaceRpcLaunch::new(
            "python",
            vec!["-m".to_string(), "imperaos".to_string()],
            ".imperaos/artifacts",
            "enterprise"
        )
        .is_ok());
    }

    #[test]
    fn launch_identity_includes_the_trusted_profile() {
        let enterprise = WorkspaceRpcLaunch::new(
            "python",
            vec!["-m".to_string(), "imperaos".to_string()],
            ".imperaos/artifacts",
            "enterprise",
        )
        .expect("enterprise launch");
        let balanced = WorkspaceRpcLaunch::new(
            "python",
            vec!["-m".to_string(), "imperaos".to_string()],
            ".imperaos/artifacts",
            "balanced",
        )
        .expect("balanced launch");

        assert_ne!(enterprise, balanced);
    }

    #[test]
    fn circuit_breaker_opens_after_three_transport_failures() {
        let mut circuit = RestartCircuit::default();
        assert!(!circuit.record_failure());
        assert!(!circuit.record_failure());
        assert!(circuit.record_failure());
        assert!(circuit.is_open());
    }

    #[test]
    fn health_snapshot_publishes_the_named_restart_metric() {
        let state = SupervisorState {
            restart_count: 2,
            ..SupervisorState::default()
        };
        let health = WorkspaceRpcSupervisor::health_snapshot(&state);
        assert_eq!(
            health.metrics.get("imperaos_artifact_rpc_restart_total"),
            Some(&2)
        );
    }

    #[test]
    fn valid_application_response_resets_transport_failure_sequence() {
        let mut circuit = RestartCircuit::default();
        assert!(!circuit.record_failure());
        assert!(!circuit.record_failure());
        circuit.record_application_response();
        assert!(!circuit.record_failure());
        assert!(!circuit.is_open());
    }

    #[test]
    fn frame_codec_is_bounded_and_length_prefixed() {
        let payload = br#"{"contractVersion":"1.0"}"#;
        let framed = encode_frame(payload, 1024).expect("frame should encode");
        assert_eq!(&framed[..4], &(payload.len() as u32).to_be_bytes());
        assert_eq!(&framed[4..], payload);
        assert!(encode_frame(&vec![0; 1025], 1024).is_err());
    }

    #[test]
    fn trusted_request_builder_enforces_route_and_identity_boundaries() {
        let identity = TrustedArtifactIdentity::new(
            "workspace-1",
            "user-1",
            "user",
            vec!["artifact_editor".to_string()],
        )
        .expect("identity should validate");
        let request = build_trusted_request(
            "artifact.get",
            json!({"artifactId": "artifact-1"}),
            &identity,
            None,
            5000,
        )
        .expect("request should build");

        assert_eq!(request["workspaceId"], "workspace-1");
        assert_eq!(request["principal"]["principalId"], "user-1");
        assert!(
            build_trusted_request("artifact.unknown", json!({}), &identity, None, 5000,).is_err()
        );
        assert!(build_trusted_request(
            "artifact.get",
            json!({"artifactId": "artifact-1", "workspaceId": "other"}),
            &identity,
            None,
            5000,
        )
        .is_err());
        assert!(build_trusted_request(
            "artifact.slides.patch",
            json!({"artifactId": "slides-1", "idempotencyKey": "slide-patch-1"}),
            &identity,
            Some("slide-patch-1".to_string()),
            5000,
        )
        .is_ok());
        assert!(build_trusted_request(
            "artifact.slides.patch",
            json!({"artifactId": "slides-1", "idempotencyKey": "params-key"}),
            &identity,
            Some("envelope-key".to_string()),
            5000,
        )
        .is_err());
    }
}
