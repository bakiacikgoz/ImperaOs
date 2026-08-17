use crate::artifact_asset::{
    ArtifactAssetState, AssetBinding, DEFAULT_ASSET_TICKET_TTL, DEFAULT_MAX_ASSET_BYTES,
};
use crate::artifact_export::{
    ArtifactExportCancelResult, ArtifactExportResult, ArtifactExportState, ExportBinding,
    ExportBoundaryError, ExportReconciliationAction, DEFAULT_MAX_EXPORT_BYTES, DEFAULT_TICKET_TTL,
};
use crate::artifact_rpc::{
    build_trusted_request, SupervisorError, TrustedArtifactIdentity, WorkspaceRpcLaunch,
    WorkspaceRpcRegistry,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader as StdBufReader, Read, Seek, SeekFrom};
use std::path::{Component, Path, PathBuf};
use std::process::Stdio;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{Emitter, Manager};
use tauri_plugin_dialog::DialogExt;
use tokio::io::{AsyncBufReadExt, AsyncReadExt, BufReader as TokioBufReader};
use tokio::process::Command;
use tokio::process::{ChildStderr, ChildStdout};
use tokio::sync::Mutex;

const CONTRACT_VERSION: &str = "3.0";
const DEFAULT_TIMEOUT_MS: u64 = 15_000;
const DEFAULT_MAX_BYTES: usize = 256 * 1024;
const DEFAULT_MAX_LINES: usize = 500;
const DEFAULT_ASSISTANT_PROMPT_MAX_CHARS: usize = 24_000;
const ASSISTANT_EVENT_NAME: &str = "assistant://event";

const ARTIFACT_ALLOWLIST: &[&str] = &[
    "status.json",
    "tasks.json",
    "handoffs.json",
    "audit_envelope.json",
    "events.jsonl",
];

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BridgeError {
    code: String,
    message: String,
    stderr_preview: String,
    command: String,
    retryable: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BridgeResult<T: Serialize> {
    ok: bool,
    data: Option<T>,
    error: Option<BridgeError>,
}

#[derive(Debug, Clone)]
struct AssistantProcessRef {
    process_id: u32,
    session_id: String,
    prompt_path: PathBuf,
}

struct AssistantPromptFileGuard(PathBuf);

impl Drop for AssistantPromptFileGuard {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
}

fn create_assistant_prompt_file_with_writer<F>(
    prompt_path: &Path,
    writer: F,
) -> std::io::Result<AssistantPromptFileGuard>
where
    F: FnOnce(&mut File) -> std::io::Result<()>,
{
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(prompt_path)?;
    let guard = AssistantPromptFileGuard(prompt_path.to_path_buf());
    writer(&mut file)?;
    Ok(guard)
}

fn cleanup_stale_assistant_prompt_files(prompt_dir: &Path, max_age: Duration) {
    let now = SystemTime::now();
    let Ok(entries) = std::fs::read_dir(prompt_dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) != Some("md") {
            continue;
        }
        let stale = entry
            .metadata()
            .and_then(|metadata| metadata.modified())
            .ok()
            .and_then(|modified| now.duration_since(modified).ok())
            .is_some_and(|age| age >= max_age);
        if stale {
            let _ = std::fs::remove_file(path);
        }
    }
}

#[derive(Default)]
pub struct AssistantProcessRegistry {
    turns: Mutex<HashMap<String, AssistantProcessRef>>,
}

impl<T: Serialize> BridgeResult<T> {
    fn ok(data: T) -> Self {
        Self {
            ok: true,
            data: Some(data),
            error: None,
        }
    }

    fn err(error: BridgeError) -> Self {
        Self {
            ok: false,
            data: None,
            error: Some(error),
        }
    }
}

impl BridgeError {
    fn new(
        code: &str,
        message: impl Into<String>,
        stderr_preview: impl Into<String>,
        command: impl Into<String>,
        retryable: bool,
    ) -> Self {
        Self {
            code: code.to_string(),
            message: message.into(),
            stderr_preview: stderr_preview.into(),
            command: command.into(),
            retryable,
        }
    }
}

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct BridgeConfig {
    pub mode: Option<String>,
    pub cli_path: Option<String>,
    pub bundled_python_path: Option<String>,
    pub profile: Option<String>,
    pub root_dir: Option<String>,
    #[serde(default)]
    pub env: HashMap<String, String>,
    pub timeout_ms: Option<u64>,
}

impl BridgeConfig {
    fn profile(&self) -> String {
        self.profile
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .unwrap_or("balanced")
            .to_string()
    }

    fn root_dir(&self) -> String {
        self.root_dir
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .unwrap_or(".imperaos/team/jobs")
            .to_string()
    }
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ArtifactBridgePayload {
    params: Value,
    idempotency_key: Option<String>,
    timeout_ms: Option<u64>,
}

macro_rules! artifact_bridge_command {
    ($name:ident, $method:literal) => {
        #[tauri::command]
        pub async fn $name(
            app: tauri::AppHandle,
            payload: ArtifactBridgePayload,
        ) -> BridgeResult<Value> {
            bridge_artifact_rpc_call(app, $method.to_string(), payload).await
        }
    };
}

artifact_bridge_command!(bridge_artifact_list, "artifact.list");
artifact_bridge_command!(bridge_artifact_handshake, "rpc.handshake");
artifact_bridge_command!(bridge_artifact_get, "artifact.get");
artifact_bridge_command!(bridge_artifact_create, "artifact.create");
artifact_bridge_command!(bridge_artifact_mutate, "artifact.mutate");
artifact_bridge_command!(
    bridge_artifact_spreadsheet_patch,
    "artifact.spreadsheet.patch"
);
artifact_bridge_command!(bridge_artifact_slides_patch, "artifact.slides.patch");
artifact_bridge_command!(
    bridge_artifact_propose_mutation,
    "artifact.propose_mutation"
);
artifact_bridge_command!(bridge_artifact_apply_proposal, "artifact.apply_proposal");
artifact_bridge_command!(bridge_artifact_history, "artifact.history");
artifact_bridge_command!(bridge_artifact_restore, "artifact.restore");
artifact_bridge_command!(bridge_artifact_archive, "artifact.archive");
artifact_bridge_command!(bridge_artifact_duplicate, "artifact.duplicate");
artifact_bridge_command!(bridge_artifact_asset_get, "artifact.asset.get");
artifact_bridge_command!(bridge_artifact_form_submit, "artifact.form.submit");
artifact_bridge_command!(bridge_artifact_import_evidence, "artifact.import_evidence");
artifact_bridge_command!(bridge_product_project_list, "project.list");
artifact_bridge_command!(bridge_product_project_create, "project.create");
artifact_bridge_command!(bridge_product_project_update, "project.update");
artifact_bridge_command!(bridge_product_project_archive, "project.archive");
artifact_bridge_command!(bridge_product_task_get, "task.get");
artifact_bridge_command!(bridge_product_task_list, "task.list");
artifact_bridge_command!(bridge_product_task_create, "task.create");
artifact_bridge_command!(bridge_product_task_update, "task.update");
artifact_bridge_command!(bridge_product_task_archive, "task.archive");
artifact_bridge_command!(bridge_product_task_message_add, "task.message.add");
artifact_bridge_command!(bridge_product_task_message_list, "task.message.list");
artifact_bridge_command!(bridge_product_task_link_add, "task.link.add");
artifact_bridge_command!(bridge_product_task_link_list, "task.link.list");
artifact_bridge_command!(bridge_product_preferences_get, "preferences.get");
artifact_bridge_command!(bridge_product_preferences_set, "preferences.set");

#[derive(Default)]
pub struct ProductFolderTicketState {
    tickets: Mutex<HashMap<String, PathBuf>>,
    roots: Mutex<HashMap<String, PathBuf>>,
}

impl ProductFolderTicketState {
    async fn issue(&self, selected_path: PathBuf) -> Result<(String, String), String> {
        let canonical = selected_path
            .canonicalize()
            .map_err(|_| "Selected folder is unavailable.".to_string())?;
        if !canonical.is_dir() {
            return Err("Selected path is not a folder.".to_string());
        }
        let display_name = canonical
            .file_name()
            .and_then(|name| name.to_str())
            .filter(|name| !name.trim().is_empty())
            .unwrap_or("Selected folder")
            .to_string();
        let ticket = format!("folder-{}", uuid::Uuid::new_v4());
        self.tickets.lock().await.insert(ticket.clone(), canonical);
        Ok((ticket, display_name))
    }

    async fn bind_in_memory(&self, folder_ticket: &str, root_ref: &str) -> Result<(), String> {
        let path = self
            .tickets
            .lock()
            .await
            .remove(folder_ticket)
            .ok_or_else(|| "Folder selection ticket is unavailable.".to_string())?;
        if !path.is_dir() || root_ref.trim().is_empty() || root_ref.contains('\0') {
            return Err("Folder registration is invalid.".to_string());
        }
        self.roots.lock().await.insert(root_ref.to_string(), path);
        Ok(())
    }

    async fn bind(
        &self,
        app: &tauri::AppHandle,
        folder_ticket: &str,
        root_ref: &str,
    ) -> Result<(), String> {
        self.bind_in_memory(folder_ticket, root_ref).await?;
        let roots = self.roots.lock().await;
        if let Err(error) = persist_native_project_roots(app, &roots) {
            drop(roots);
            self.roots.lock().await.remove(root_ref);
            return Err(error);
        }
        Ok(())
    }

    /// Resolves an opaque product root only inside the native process. A
    /// renderer-provided root reference can select a registered root, but can
    /// never supply or learn a filesystem path.
    pub async fn resolve_registered_root(&self, root_ref: &str) -> Result<PathBuf, String> {
        if root_ref.trim().is_empty() || root_ref.len() > 256 || root_ref.contains('\0') {
            return Err("Registered project root is invalid.".to_string());
        }
        let path = self
            .roots
            .lock()
            .await
            .get(root_ref)
            .cloned()
            .ok_or_else(|| "Registered project root is unavailable.".to_string())?;
        let canonical = path
            .canonicalize()
            .map_err(|_| "Registered project root is unavailable.".to_string())?;
        if !canonical.is_dir() {
            return Err("Registered project root is unavailable.".to_string());
        }
        Ok(canonical)
    }

    pub async fn resolve_registered_root_from_native_store(
        &self,
        app: &tauri::AppHandle,
        root_ref: &str,
    ) -> Result<PathBuf, String> {
        if root_ref.trim().is_empty() || root_ref.len() > 256 || root_ref.contains('\0') {
            return Err("Registered project root is invalid.".to_string());
        }
        if let Ok(path) = self.resolve_registered_root(root_ref).await {
            return Ok(path);
        }
        let recovered = load_native_project_roots(app)?
            .remove(root_ref)
            .ok_or_else(|| "Registered project root is unavailable.".to_string())?;
        self.roots
            .lock()
            .await
            .insert(root_ref.to_string(), recovered);
        self.resolve_registered_root(root_ref).await
    }
}

fn native_project_roots_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let directory = app
        .path()
        .app_data_dir()
        .map_err(|_| "Native project-root storage is unavailable.".to_string())?
        .join("product-workspace");
    fs::create_dir_all(&directory)
        .map_err(|_| "Native project-root storage is unavailable.".to_string())?;
    Ok(directory.join("registered-project-roots.json"))
}

fn persist_native_project_roots(
    app: &tauri::AppHandle,
    roots: &HashMap<String, PathBuf>,
) -> Result<(), String> {
    let destination = native_project_roots_path(app)?;
    let temporary = destination.with_extension("json.tmp");
    let encoded = serde_json::to_vec(roots)
        .map_err(|_| "Native project-root storage is unavailable.".to_string())?;
    fs::write(&temporary, encoded)
        .map_err(|_| "Native project-root storage is unavailable.".to_string())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&temporary, fs::Permissions::from_mode(0o600))
            .map_err(|_| "Native project-root storage is unavailable.".to_string())?;
    }
    fs::rename(&temporary, &destination)
        .map_err(|_| "Native project-root storage is unavailable.".to_string())
}

fn load_native_project_roots(app: &tauri::AppHandle) -> Result<HashMap<String, PathBuf>, String> {
    let path = native_project_roots_path(app)?;
    match fs::read(path) {
        Ok(bytes) => serde_json::from_slice(&bytes)
            .map_err(|_| "Native project-root storage is unavailable.".to_string()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(HashMap::new()),
        Err(_) => Err("Native project-root storage is unavailable.".to_string()),
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProductFolderSelectResult {
    cancelled: bool,
    folder_ticket: Option<String>,
    display_name: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ProductProjectRegisterRequest {
    folder_ticket: String,
    name: String,
    idempotency_key: String,
}

#[tauri::command]
pub async fn bridge_product_project_folder_select(
    app: tauri::AppHandle,
) -> BridgeResult<ProductFolderSelectResult> {
    if let Err(error) =
        resolve_trusted_artifact_identity(&trusted_artifact_bridge_config(), &app).await
    {
        return BridgeResult::err(error);
    }
    let dialog_app = app.clone();
    let selection = match tokio::task::spawn_blocking(move || {
        dialog_app.dialog().file().blocking_pick_folder()
    })
    .await
    {
        Ok(selection) => selection,
        Err(_) => {
            return BridgeResult::err(BridgeError::new(
                "PRODUCT_FOLDER_UNAVAILABLE",
                "Native folder dialog failed.",
                "",
                "product folder select",
                true,
            ))
        }
    };
    let Some(selection) = selection else {
        return BridgeResult::ok(ProductFolderSelectResult {
            cancelled: true,
            folder_ticket: None,
            display_name: None,
        });
    };
    let path = match selection.into_path() {
        Ok(path) => path,
        Err(_) => {
            return BridgeResult::err(BridgeError::new(
                "PRODUCT_FOLDER_UNAVAILABLE",
                "Selected folder is not a local filesystem path.",
                "",
                "product folder select",
                false,
            ))
        }
    };
    match app.state::<ProductFolderTicketState>().issue(path).await {
        Ok((folder_ticket, display_name)) => BridgeResult::ok(ProductFolderSelectResult {
            cancelled: false,
            folder_ticket: Some(folder_ticket),
            display_name: Some(display_name),
        }),
        Err(message) => BridgeResult::err(BridgeError::new(
            "PRODUCT_FOLDER_UNAVAILABLE",
            message,
            "",
            "product folder select",
            false,
        )),
    }
}

#[tauri::command]
pub async fn bridge_product_project_register(
    app: tauri::AppHandle,
    request: ProductProjectRegisterRequest,
) -> BridgeResult<Value> {
    if normalize_required_text(&request.folder_ticket, "folder ticket", "project register").is_err()
        || normalize_required_text(&request.name, "project name", "project register").is_err()
        || normalize_required_text(
            &request.idempotency_key,
            "idempotency key",
            "project register",
        )
        .is_err()
    {
        return BridgeResult::err(BridgeError::new(
            "INVALID_INPUT",
            "Project registration request is incomplete.",
            "",
            "project register",
            false,
        ));
    }
    if !app
        .state::<ProductFolderTicketState>()
        .tickets
        .lock()
        .await
        .contains_key(&request.folder_ticket)
    {
        return BridgeResult::err(BridgeError::new(
            "PRODUCT_FOLDER_UNAVAILABLE",
            "Folder selection ticket is unavailable.",
            "",
            "project register",
            false,
        ));
    }
    let response = bridge_artifact_rpc_call(
        app.clone(),
        "project.register".to_string(),
        ArtifactBridgePayload {
            params: json!({
                "folderTicket": request.folder_ticket,
                "name": request.name,
                "idempotencyKey": request.idempotency_key,
            }),
            idempotency_key: Some(request.idempotency_key),
            timeout_ms: Some(DEFAULT_TIMEOUT_MS),
        },
    )
    .await;
    if !response.ok {
        return response;
    }
    let Some(root_ref) = response
        .data
        .as_ref()
        .and_then(|data| data.get("rootRef"))
        .and_then(Value::as_str)
    else {
        return BridgeResult::err(BridgeError::new(
            "PRODUCT_PROJECT_INVALID",
            "Project registration did not return a root reference.",
            "",
            "project register",
            false,
        ));
    };
    if let Err(message) = app
        .state::<ProductFolderTicketState>()
        .bind(&app, &request.folder_ticket, root_ref)
        .await
    {
        return BridgeResult::err(BridgeError::new(
            "PRODUCT_FOLDER_UNAVAILABLE",
            message,
            "",
            "project register",
            false,
        ));
    }
    response
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ArtifactAssetSelectResult {
    cancelled: bool,
    ticket: Option<String>,
    file_name: Option<String>,
    expires_in_ms: Option<u64>,
    max_bytes: usize,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ArtifactAssetImportRequest {
    ticket: String,
    data_class: String,
    idempotency_key: String,
}

#[tauri::command]
pub async fn bridge_artifact_asset_select(
    app: tauri::AppHandle,
) -> BridgeResult<ArtifactAssetSelectResult> {
    let identity =
        match resolve_trusted_artifact_identity(&trusted_artifact_bridge_config(), &app).await {
            Ok(identity) => identity,
            Err(error) => return BridgeResult::err(error),
        };
    let binding = match AssetBinding::new(identity.workspace_id(), identity.principal_id()) {
        Ok(binding) => binding,
        Err(message) => {
            return BridgeResult::err(BridgeError::new(
                "ARTIFACT_ASSET_UNSAFE",
                message,
                "",
                "artifact asset select",
                false,
            ))
        }
    };
    let dialog_app = app.clone();
    let selection = match tokio::task::spawn_blocking(move || {
        dialog_app
            .dialog()
            .file()
            .add_filter("Images", &["png", "jpg", "jpeg", "gif", "webp", "svg"])
            .blocking_pick_file()
    })
    .await
    {
        Ok(selection) => selection,
        Err(_) => {
            return BridgeResult::err(BridgeError::new(
                "ARTIFACT_ASSET_UNSAFE",
                "Native asset dialog failed.",
                "",
                "artifact asset select",
                true,
            ))
        }
    };
    let Some(selection) = selection else {
        return BridgeResult::ok(ArtifactAssetSelectResult {
            cancelled: true,
            ticket: None,
            file_name: None,
            expires_in_ms: None,
            max_bytes: DEFAULT_MAX_ASSET_BYTES,
        });
    };
    let path = match selection.into_path() {
        Ok(path) => path,
        Err(_) => {
            return BridgeResult::err(BridgeError::new(
                "ARTIFACT_ASSET_UNSAFE",
                "Selected asset is not a local filesystem path.",
                "",
                "artifact asset select",
                false,
            ))
        }
    };
    match app
        .state::<ArtifactAssetState>()
        .issue_ticket(path, binding, DEFAULT_ASSET_TICKET_TTL)
        .await
    {
        Ok(issued) => BridgeResult::ok(ArtifactAssetSelectResult {
            cancelled: false,
            ticket: Some(issued.ticket),
            file_name: Some(issued.file_name),
            expires_in_ms: Some(issued.expires_in_ms),
            max_bytes: issued.max_bytes,
        }),
        Err(message) => BridgeResult::err(BridgeError::new(
            "ARTIFACT_ASSET_UNSAFE",
            message,
            "",
            "artifact asset select",
            false,
        )),
    }
}

#[tauri::command]
pub async fn bridge_artifact_asset_import(
    app: tauri::AppHandle,
    request: ArtifactAssetImportRequest,
) -> BridgeResult<Value> {
    if !matches!(
        request.data_class.as_str(),
        "public" | "internal" | "confidential" | "regulated"
    ) || normalize_required_text(
        &request.idempotency_key,
        "idempotency_key",
        "artifact asset import",
    )
    .is_err()
    {
        return BridgeResult::err(BridgeError::new(
            "INVALID_INPUT",
            "Asset classification and idempotency key are required.",
            "",
            "artifact asset import",
            false,
        ));
    }
    let identity =
        match resolve_trusted_artifact_identity(&trusted_artifact_bridge_config(), &app).await {
            Ok(identity) => identity,
            Err(error) => return BridgeResult::err(error),
        };
    let binding = match AssetBinding::new(identity.workspace_id(), identity.principal_id()) {
        Ok(binding) => binding,
        Err(message) => {
            return BridgeResult::err(BridgeError::new(
                "ARTIFACT_ASSET_UNSAFE",
                message,
                "",
                "artifact asset import",
                false,
            ))
        }
    };
    let consumed = match app
        .state::<ArtifactAssetState>()
        .consume(&request.ticket, &binding)
        .await
    {
        Ok(consumed) => consumed,
        Err(message) => {
            return BridgeResult::err(BridgeError::new(
                "ARTIFACT_ASSET_UNSAFE",
                message,
                "",
                "artifact asset import",
                false,
            ))
        }
    };
    let declared_media_type = match detect_asset_media_type(&consumed.bytes) {
        Some(value) => value,
        None => {
            return BridgeResult::err(BridgeError::new(
                "ARTIFACT_ASSET_TYPE_UNSUPPORTED",
                "Selected asset type is unsupported.",
                "",
                "artifact asset import",
                false,
            ))
        }
    };
    bridge_artifact_rpc_call(
        app,
        "artifact.asset.import".to_string(),
        ArtifactBridgePayload {
            params: json!({
                "fileName": consumed.file_name,
                "declaredMediaType": declared_media_type,
                "contentBase64": encode_base64(&consumed.bytes),
                "dataClass": request.data_class,
                "idempotencyKey": request.idempotency_key,
            }),
            idempotency_key: Some(request.idempotency_key),
            timeout_ms: Some(DEFAULT_TIMEOUT_MS),
        },
    )
    .await
}

fn detect_asset_media_type(payload: &[u8]) -> Option<&'static str> {
    if payload.starts_with(b"\x89PNG\r\n\x1a\n") {
        return Some("image/png");
    }
    if payload.starts_with(b"\xff\xd8\xff") {
        return Some("image/jpeg");
    }
    if payload.starts_with(b"GIF87a") || payload.starts_with(b"GIF89a") {
        return Some("image/gif");
    }
    if payload.len() >= 12 && payload.starts_with(b"RIFF") && &payload[8..12] == b"WEBP" {
        return Some("image/webp");
    }
    let prefix = &payload[..payload.len().min(4096)];
    let text = String::from_utf8_lossy(prefix).to_ascii_lowercase();
    let normalized = text.trim_start_matches(['\u{feff}', '\0', '\t', '\r', '\n', ' ']);
    if normalized.starts_with("<svg")
        || (normalized.starts_with("<?xml") && normalized.contains("<svg"))
    {
        return Some("image/svg+xml");
    }
    None
}

fn encode_base64(payload: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut output = String::with_capacity(payload.len().div_ceil(3) * 4);
    for chunk in payload.chunks(3) {
        let first = chunk[0];
        let second = *chunk.get(1).unwrap_or(&0);
        let third = *chunk.get(2).unwrap_or(&0);
        output.push(TABLE[(first >> 2) as usize] as char);
        output.push(TABLE[(((first & 0x03) << 4) | (second >> 4)) as usize] as char);
        output.push(if chunk.len() > 1 {
            TABLE[(((second & 0x0F) << 2) | (third >> 6)) as usize] as char
        } else {
            '='
        });
        output.push(if chunk.len() > 2 {
            TABLE[(third & 0x3F) as usize] as char
        } else {
            '='
        });
    }
    output
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ArtifactExportBeginRequest {
    artifact_id: String,
    revision_id: String,
    format: String,
    idempotency_key: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct AuthorizedExportBegin {
    export_id: String,
    artifact_id: String,
    revision_id: String,
    format: String,
    basename: String,
    max_bytes: usize,
    disposition: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ArtifactExportBeginResult {
    cancelled: bool,
    export_id: String,
    ticket: Option<String>,
    expires_in_ms: Option<u64>,
    max_bytes: usize,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ArtifactExportCommitRequest {
    ticket: String,
    bytes: Vec<u8>,
    sha256: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ArtifactExportCancelRequest {
    ticket: String,
}

#[tauri::command]
pub async fn bridge_artifact_export_begin(
    app: tauri::AppHandle,
    request: ArtifactExportBeginRequest,
) -> BridgeResult<ArtifactExportBeginResult> {
    if normalize_required_text(&request.artifact_id, "artifact_id", "artifact export begin")
        .is_err()
        || normalize_required_text(&request.revision_id, "revision_id", "artifact export begin")
            .is_err()
    {
        return BridgeResult::err(BridgeError::new(
            "INVALID_INPUT",
            "artifact_id and revision_id are required",
            "",
            "artifact export begin",
            false,
        ));
    }
    let identity =
        match resolve_trusted_artifact_identity(&trusted_artifact_bridge_config(), &app).await {
            Ok(identity) => identity,
            Err(error) => return BridgeResult::err(error),
        };
    if let Err(error) = reconcile_artifact_exports(app.clone(), &identity).await {
        return BridgeResult::err(error);
    }
    let authority = bridge_artifact_rpc_call(
        app.clone(),
        "artifact.export.begin".to_string(),
        ArtifactBridgePayload {
            params: json!({
                "artifactId": request.artifact_id.clone(),
                "revisionId": request.revision_id.clone(),
                "format": request.format.clone(),
                "idempotencyKey": request.idempotency_key.clone(),
            }),
            idempotency_key: Some(request.idempotency_key.clone()),
            timeout_ms: Some(DEFAULT_TIMEOUT_MS),
        },
    )
    .await;
    let authorized: AuthorizedExportBegin = match authority.data {
        Some(value) => match serde_json::from_value(value) {
            Ok(value) => value,
            Err(_) => {
                return BridgeResult::err(BridgeError::new(
                    "ARTIFACT_RPC_PROTOCOL_MISMATCH",
                    "Artifact export authority returned an invalid result.",
                    "",
                    "artifact export begin",
                    false,
                ))
            }
        },
        None => {
            return BridgeResult::err(authority.error.unwrap_or_else(|| {
                BridgeError::new(
                    "ARTIFACT_RPC_UNAVAILABLE",
                    "Artifact export authority is unavailable.",
                    "",
                    "artifact export begin",
                    true,
                )
            }))
        }
    };
    let _ = &authorized.disposition;
    let (filter_name, extensions) = match export_format(&authorized.format) {
        Ok(format) => format,
        Err(error) => {
            let _ =
                cancel_export_authority(app.clone(), &authorized.export_id, "native_write_failed")
                    .await;
            return BridgeResult::err(error);
        }
    };
    let suggested_name = if authorized.format == "source" {
        authorized.basename.clone()
    } else {
        sanitize_export_filename(&authorized.basename, extensions[0])
    };
    if suggested_name != authorized.basename {
        let _ = cancel_export_authority(app.clone(), &authorized.export_id, "native_write_failed")
            .await;
        return BridgeResult::err(BridgeError::new(
            "ARTIFACT_EXPORT_FAILED",
            "Backend export basename is not portable.",
            "",
            "artifact export begin",
            false,
        ));
    }
    let binding = match ExportBinding::authorized(
        identity.workspace_id(),
        identity.principal_id(),
        identity.principal_type(),
        &authorized.export_id,
        &authorized.artifact_id,
        &authorized.revision_id,
        &authorized.format,
    ) {
        Ok(binding) => binding,
        Err(error) => {
            let _ =
                cancel_export_authority(app.clone(), &authorized.export_id, "native_write_failed")
                    .await;
            return BridgeResult::err(export_bridge_error("artifact export begin", error));
        }
    };
    let dialog_app = app.clone();
    let selection = match tokio::task::spawn_blocking(move || {
        dialog_app
            .dialog()
            .file()
            .set_file_name(suggested_name)
            .add_filter(filter_name, &extensions)
            .blocking_save_file()
    })
    .await
    {
        Ok(selection) => selection,
        Err(_) => {
            let _ =
                cancel_export_authority(app.clone(), &authorized.export_id, "native_write_failed")
                    .await;
            return BridgeResult::err(BridgeError::new(
                "ARTIFACT_EXPORT_FAILED",
                "Native export dialog failed.",
                "",
                "artifact export begin",
                true,
            ));
        }
    };
    let Some(selection) = selection else {
        if let Err(error) =
            cancel_export_authority(app.clone(), &authorized.export_id, "user_cancelled").await
        {
            return BridgeResult::err(error);
        }
        return BridgeResult::ok(ArtifactExportBeginResult {
            cancelled: true,
            export_id: authorized.export_id.clone(),
            ticket: None,
            expires_in_ms: None,
            max_bytes: configured_max_export_bytes(),
        });
    };
    let target = match selection.into_path() {
        Ok(path) => path,
        Err(_) => {
            let _ =
                cancel_export_authority(app.clone(), &authorized.export_id, "native_write_failed")
                    .await;
            return BridgeResult::err(BridgeError::new(
                "ARTIFACT_EXPORT_FAILED",
                "Native export target is not a local filesystem path.",
                "",
                "artifact export begin",
                false,
            ));
        }
    };
    if target.file_name().and_then(|value| value.to_str()) != Some(authorized.basename.as_str()) {
        let _ = cancel_export_authority(app.clone(), &authorized.export_id, "user_cancelled").await;
        return BridgeResult::err(BridgeError::new(
            "ARTIFACT_EXPORT_FAILED",
            "The export filename must match the backend-authorized basename.",
            "",
            "artifact export begin",
            false,
        ));
    }
    let state = app.state::<ArtifactExportState>();
    match state
        .issue_ticket(
            target,
            binding,
            configured_max_export_bytes().min(authorized.max_bytes),
            DEFAULT_TICKET_TTL,
        )
        .await
    {
        Ok(issued) => BridgeResult::ok(ArtifactExportBeginResult {
            cancelled: false,
            export_id: authorized.export_id.clone(),
            ticket: Some(issued.ticket),
            expires_in_ms: Some(issued.expires_in_ms),
            max_bytes: issued.max_bytes,
        }),
        Err(error) => {
            let _ =
                cancel_export_authority(app.clone(), &authorized.export_id, "native_write_failed")
                    .await;
            BridgeResult::err(export_bridge_error("artifact export begin", error))
        }
    }
}

#[tauri::command]
pub async fn bridge_artifact_export_commit(
    app: tauri::AppHandle,
    request: ArtifactExportCommitRequest,
) -> BridgeResult<ArtifactExportResult> {
    let identity =
        match resolve_trusted_artifact_identity(&trusted_artifact_bridge_config(), &app).await {
            Ok(identity) => identity,
            Err(error) => return BridgeResult::err(error),
        };
    let binding = match ExportBinding::new(identity.workspace_id(), identity.principal_id()) {
        Ok(binding) => binding,
        Err(error) => {
            return BridgeResult::err(export_bridge_error("artifact export commit", error))
        }
    };
    let state = app.state::<ArtifactExportState>();
    let authorized_binding = match state.binding_for_ticket(&request.ticket, &binding).await {
        Ok(binding) => binding,
        Err(error) => {
            return BridgeResult::err(export_bridge_error("artifact export commit", error))
        }
    };
    let preflight = match state
        .preflight(&request.ticket, &binding, &request.bytes, &request.sha256)
        .await
    {
        Ok(result) => result,
        Err(error) => {
            let _ = cancel_export_authority(
                app.clone(),
                authorized_binding.export_id(),
                "native_write_failed",
            )
            .await;
            return BridgeResult::err(export_bridge_error("artifact export commit", error));
        }
    };
    let authority = bridge_artifact_rpc_call(
        app.clone(),
        "artifact.export.preflight".to_string(),
        ArtifactBridgePayload {
            params: json!({
                "exportId": preflight.binding.export_id(),
                "basename": preflight.basename,
                "sha256": preflight.sha256,
                "sizeBytes": preflight.size_bytes,
                "idempotencyKey": format!("preflight-{}", preflight.binding.export_id()),
            }),
            idempotency_key: Some(format!("preflight-{}", preflight.binding.export_id())),
            timeout_ms: Some(DEFAULT_TIMEOUT_MS),
        },
    )
    .await;
    if authority.data.is_none() {
        let _ = state.cancel(&request.ticket, &binding).await;
        let _ = cancel_export_authority(
            app.clone(),
            authorized_binding.export_id(),
            "native_write_failed",
        )
        .await;
        return BridgeResult::err(authority.error.unwrap_or_else(|| {
            BridgeError::new(
                "ARTIFACT_RPC_UNAVAILABLE",
                "Artifact export preflight could not be authorized.",
                "",
                "artifact export commit",
                true,
            )
        }));
    }
    if let Err(error) = state
        .prepare_reconciliation(&request.ticket, &binding, &preflight)
        .await
    {
        if cancel_export_authority(
            app.clone(),
            authorized_binding.export_id(),
            "native_write_failed",
        )
        .await
        .is_ok()
        {
            let _ = state.cancel(&request.ticket, &binding).await;
        }
        return BridgeResult::err(export_bridge_error("artifact export commit", error));
    }
    let result = match state
        .commit(&request.ticket, &binding, request.bytes, &request.sha256)
        .await
    {
        Ok(result) => result,
        Err(error) => {
            if error.requires_reconciliation() {
                return BridgeResult::err(export_bridge_error("artifact export commit", error));
            }
            if cancel_export_authority(
                app.clone(),
                authorized_binding.export_id(),
                "native_write_failed",
            )
            .await
            .is_ok()
            {
                let _ = state.cancel(&request.ticket, &binding).await;
            }
            return BridgeResult::err(export_bridge_error("artifact export commit", error));
        }
    };
    if let Err(error) = commit_export_authority(
        app.clone(),
        result.binding.export_id(),
        &result.basename,
        &result.sha256,
        result.size_bytes,
    )
    .await
    {
        return BridgeResult::err(error);
    }
    if let Err(error) = state.finalize(&request.ticket, &binding).await {
        return BridgeResult::err(export_bridge_error("artifact export commit", error));
    }
    BridgeResult::ok(result)
}

#[tauri::command]
pub async fn bridge_artifact_export_cancel(
    app: tauri::AppHandle,
    request: ArtifactExportCancelRequest,
) -> BridgeResult<ArtifactExportCancelResult> {
    let identity =
        match resolve_trusted_artifact_identity(&trusted_artifact_bridge_config(), &app).await {
            Ok(identity) => identity,
            Err(error) => return BridgeResult::err(error),
        };
    let binding = match ExportBinding::new(identity.workspace_id(), identity.principal_id()) {
        Ok(binding) => binding,
        Err(error) => {
            return BridgeResult::err(export_bridge_error("artifact export cancel", error))
        }
    };
    let state = app.state::<ArtifactExportState>();
    if let Err(error) = state.require_cancellable(&request.ticket, &binding).await {
        return BridgeResult::err(export_bridge_error("artifact export cancel", error));
    }
    let authorized_binding = match state.binding_for_ticket(&request.ticket, &binding).await {
        Ok(result) => result,
        Err(error) => {
            return BridgeResult::err(export_bridge_error("artifact export cancel", error))
        }
    };
    if let Err(error) = cancel_export_authority(
        app.clone(),
        authorized_binding.export_id(),
        "user_cancelled",
    )
    .await
    {
        return BridgeResult::err(error);
    }
    let result = match state.cancel(&request.ticket, &binding).await {
        Ok(result) => result,
        Err(error) => {
            return BridgeResult::err(export_bridge_error("artifact export cancel", error))
        }
    };
    BridgeResult::ok(result)
}

fn export_format(format: &str) -> Result<(&'static str, Vec<&'static str>), BridgeError> {
    match format.trim().to_ascii_lowercase().as_str() {
        "json" => Ok(("JSON", vec!["json"])),
        "submission-json" => Ok(("Submission JSON", vec!["submission.json"])),
        "markdown" | "md" => Ok(("Markdown", vec!["md"])),
        "html" => Ok(("HTML", vec!["html"])),
        "csv" => Ok(("CSV", vec!["csv"])),
        "xlsx" => Ok(("Excel", vec!["xlsx"])),
        "png" => Ok(("PNG", vec!["png"])),
        "svg" => Ok(("SVG", vec!["svg"])),
        "pptx" => Ok(("PowerPoint", vec!["pptx"])),
        "source" => Ok(("Source", vec!["txt"])),
        "txt" => Ok(("Text", vec!["txt"])),
        _ => Err(BridgeError::new(
            "ARTIFACT_EXPORT_FAILED",
            "Artifact export format is unsupported.",
            "",
            "artifact export begin",
            false,
        )),
    }
}

fn sanitize_export_filename(value: &str, extension: &str) -> String {
    let basename = Path::new(value)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("artifact");
    let mut sanitized = basename
        .chars()
        .map(|character| {
            if character.is_alphanumeric() || matches!(character, ' ' | '-' | '_' | '.') {
                character
            } else {
                '_'
            }
        })
        .take(120)
        .collect::<String>();
    sanitized = sanitized.trim_matches([' ', '.']).to_string();
    if sanitized.is_empty() {
        sanitized = "artifact".to_string();
    }
    let suffix = format!(".{extension}");
    if !sanitized.to_ascii_lowercase().ends_with(&suffix) {
        sanitized.push_str(&suffix);
    }
    sanitized
}

fn configured_max_export_bytes() -> usize {
    std::env::var("IMPERAOS_ARTIFACT_MAX_EXPORT_BYTES")
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| *value > 0 && *value <= DEFAULT_MAX_EXPORT_BYTES)
        .unwrap_or(DEFAULT_MAX_EXPORT_BYTES)
}

pub(crate) fn artifact_export_journal_root() -> PathBuf {
    default_cli_workdir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".imperaos")
        .join("artifact-export-reconciliation")
}

fn export_bridge_error(command: &str, error: ExportBoundaryError) -> BridgeError {
    BridgeError::new(&error.code, error.message, "", command, error.retryable)
}

async fn cancel_export_authority(
    app: tauri::AppHandle,
    export_id: &str,
    reason: &str,
) -> Result<(), BridgeError> {
    let idempotency_key = format!("cancel-{export_id}-{reason}");
    let response = bridge_artifact_rpc_call(
        app,
        "artifact.export.cancel".to_string(),
        ArtifactBridgePayload {
            params: json!({
                "exportId": export_id,
                "reason": reason,
                "idempotencyKey": idempotency_key,
            }),
            idempotency_key: Some(idempotency_key.clone()),
            timeout_ms: Some(DEFAULT_TIMEOUT_MS),
        },
    )
    .await;
    if response.data.is_some() {
        Ok(())
    } else {
        Err(response.error.unwrap_or_else(|| {
            BridgeError::new(
                "ARTIFACT_RPC_UNAVAILABLE",
                "Artifact export cancellation could not be acknowledged.",
                "",
                "artifact export cancel",
                true,
            )
        }))
    }
}

fn export_commit_terminal_request(
    export_id: &str,
    basename: &str,
    sha256: &str,
    size_bytes: usize,
) -> (String, ArtifactBridgePayload) {
    let idempotency_key = format!("commit-{export_id}");
    (
        "artifact.export.commit".to_string(),
        ArtifactBridgePayload {
            params: json!({
                "exportId": export_id,
                "basename": basename,
                "sha256": sha256,
                "sizeBytes": size_bytes,
                "idempotencyKey": idempotency_key,
            }),
            idempotency_key: Some(idempotency_key),
            timeout_ms: Some(DEFAULT_TIMEOUT_MS),
        },
    )
}

fn export_reconciliation_terminal_request(
    action: &ExportReconciliationAction,
) -> (String, ArtifactBridgePayload) {
    match action {
        ExportReconciliationAction::Commit(receipt) => export_commit_terminal_request(
            receipt.export_id(),
            receipt.basename(),
            receipt.sha256(),
            receipt.size_bytes(),
        ),
        ExportReconciliationAction::CancelNativeWriteFailed(receipt) => {
            let idempotency_key = format!("cancel-{}-native_write_failed", receipt.export_id());
            (
                "artifact.export.cancel".to_string(),
                ArtifactBridgePayload {
                    params: json!({
                        "exportId": receipt.export_id(),
                        "reason": "native_write_failed",
                        "idempotencyKey": idempotency_key.clone(),
                    }),
                    idempotency_key: Some(idempotency_key),
                    timeout_ms: Some(DEFAULT_TIMEOUT_MS),
                },
            )
        }
    }
}

async fn call_export_terminal_authority(
    app: tauri::AppHandle,
    method: String,
    payload: ArtifactBridgePayload,
) -> Result<(), BridgeError> {
    let response = bridge_artifact_rpc_call(app, method.clone(), payload).await;
    if response.data.is_some() {
        Ok(())
    } else {
        Err(response.error.unwrap_or_else(|| {
            BridgeError::new(
                "ARTIFACT_RPC_UNAVAILABLE",
                "Artifact export terminal state could not be acknowledged.",
                "",
                method,
                true,
            )
        }))
    }
}

async fn commit_export_authority(
    app: tauri::AppHandle,
    export_id: &str,
    basename: &str,
    sha256: &str,
    size_bytes: usize,
) -> Result<(), BridgeError> {
    let (method, payload) = export_commit_terminal_request(export_id, basename, sha256, size_bytes);
    call_export_terminal_authority(app, method, payload).await
}

async fn reconcile_export_actions_with<F, Fut>(
    state: &ArtifactExportState,
    actions: Vec<ExportReconciliationAction>,
    mut terminal: F,
) -> Result<(), BridgeError>
where
    F: FnMut(ExportReconciliationAction) -> Fut,
    Fut: std::future::Future<Output = Result<(), BridgeError>>,
{
    for action in actions {
        let export_id = action.receipt().export_id().to_string();
        terminal(action).await?;
        state
            .acknowledge_reconciliation(&export_id)
            .await
            .map_err(|error| export_bridge_error("artifact export reconciliation", error))?;
    }
    Ok(())
}

async fn reconcile_artifact_exports(
    app: tauri::AppHandle,
    identity: &TrustedArtifactIdentity,
) -> Result<(), BridgeError> {
    let binding = ExportBinding::new(identity.workspace_id(), identity.principal_id())
        .map_err(|error| export_bridge_error("artifact export reconciliation", error))?;
    let state = app.state::<ArtifactExportState>();
    let actions = state
        .reconciliation_actions(&binding)
        .await
        .map_err(|error| export_bridge_error("artifact export reconciliation", error))?;
    reconcile_export_actions_with(&state, actions, |action| {
        let app = app.clone();
        async move {
            let (method, payload) = export_reconciliation_terminal_request(&action);
            call_export_terminal_authority(app, method, payload).await
        }
    })
    .await
}

async fn bridge_artifact_rpc_call(
    app: tauri::AppHandle,
    method: String,
    payload: ArtifactBridgePayload,
) -> BridgeResult<Value> {
    let registry = app.state::<WorkspaceRpcRegistry>();
    let config = trusted_artifact_bridge_config();
    let identity = match resolve_trusted_artifact_identity(&config, &app).await {
        Ok(identity) => identity,
        Err(error) => return BridgeResult::err(error),
    };
    let resolved = match resolve_cli_command(&config, app_resource_dir(&app).as_deref()) {
        Ok(resolved) => resolved,
        Err(error) => return BridgeResult::err(error),
    };
    let artifact_root = default_cli_workdir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".imperaos")
        .join("artifacts");
    let launch = match WorkspaceRpcLaunch::new(
        resolved.program,
        resolved.prefix_args,
        artifact_root,
        trusted_artifact_profile(),
    ) {
        Ok(launch) => launch,
        Err(error) => return BridgeResult::err(supervisor_bridge_error(&method, error)),
    };
    let timeout_ms = payload
        .timeout_ms
        .unwrap_or(DEFAULT_TIMEOUT_MS)
        .clamp(1, 120_000);
    let request = match build_trusted_request(
        &method,
        payload.params,
        &identity,
        payload.idempotency_key,
        timeout_ms,
    ) {
        Ok(request) => request,
        Err(error) => return BridgeResult::err(supervisor_bridge_error(&method, error)),
    };
    let supervisor = match registry.get_or_start(launch).await {
        Ok(supervisor) => supervisor,
        Err(error) => return BridgeResult::err(supervisor_bridge_error(&method, error)),
    };
    match supervisor
        .call(request, Duration::from_millis(timeout_ms))
        .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(supervisor_bridge_error(&method, error)),
    }
}

fn trusted_artifact_bridge_config() -> BridgeConfig {
    BridgeConfig {
        mode: Some("auto".to_string()),
        cli_path: None,
        bundled_python_path: None,
        profile: Some(trusted_artifact_profile()),
        root_dir: None,
        env: HashMap::new(),
        timeout_ms: Some(DEFAULT_TIMEOUT_MS),
    }
}

fn trusted_artifact_profile() -> String {
    std::env::var("IMPERAOS_PROFILE")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty() && !value.contains('\0'))
        .unwrap_or_else(|| "enterprise".to_string())
}

fn trusted_artifact_command_config(config: &BridgeConfig) -> BridgeConfig {
    let mut trusted = trusted_artifact_bridge_config();
    trusted.timeout_ms = config.timeout_ms;
    trusted
}

async fn resolve_trusted_artifact_identity(
    config: &BridgeConfig,
    app: &tauri::AppHandle,
) -> Result<TrustedArtifactIdentity, BridgeError> {
    let profile = config.profile();
    let workspace_id = match std::env::var("IMPERAOS_WORKSPACE_ID") {
        Ok(value) if !value.trim().is_empty() => value.trim().to_string(),
        _ if profile != "enterprise" => "local".to_string(),
        _ => {
            return Err(BridgeError::new(
                "ARTIFACT_PERMISSION_DENIED",
                "Trusted artifact workspace identity is unavailable.",
                "",
                "artifact identity",
                false,
            ))
        }
    };

    if profile == "enterprise" {
        let whoami = run_cli_json_owned_with_resource_dir(
            config,
            vec![
                "auth".to_string(),
                "whoami".to_string(),
                "--profile".to_string(),
                profile,
                "--json".to_string(),
            ],
            app_resource_dir(app).as_deref(),
        )
        .await?;
        if whoami.get("verified").and_then(Value::as_bool) != Some(true) {
            return Err(BridgeError::new(
                "ARTIFACT_PERMISSION_DENIED",
                "Trusted artifact principal could not be verified.",
                "",
                "artifact identity",
                false,
            ));
        }
        let actor = whoami
            .get("actor")
            .and_then(Value::as_object)
            .ok_or_else(|| {
                BridgeError::new(
                    "ARTIFACT_PERMISSION_DENIED",
                    "Trusted artifact principal is missing.",
                    "",
                    "artifact identity",
                    false,
                )
            })?;
        let principal_id = actor
            .get("actor_id")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let roles = actor
            .get("roles")
            .and_then(Value::as_array)
            .map(|values| {
                values
                    .iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        return TrustedArtifactIdentity::new(workspace_id, principal_id, "user", roles)
            .map_err(|error| supervisor_bridge_error("artifact identity", error));
    }

    let principal_id = std::env::var("IMPERAOS_ACTOR_ID")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "local-user".to_string());
    let roles = std::env::var("IMPERAOS_ARTIFACT_ROLES")
        .ok()
        .map(|value| {
            value
                .split(',')
                .map(str::trim)
                .filter(|role| !role.is_empty())
                .map(str::to_string)
                .collect::<Vec<_>>()
        })
        .filter(|roles| !roles.is_empty())
        .unwrap_or_else(|| vec!["artifact_admin".to_string()]);
    TrustedArtifactIdentity::new(workspace_id, principal_id, "user", roles)
        .map_err(|error| supervisor_bridge_error("artifact identity", error))
}

fn supervisor_bridge_error(command: &str, error: SupervisorError) -> BridgeError {
    BridgeError::new(&error.code, error.message, "", command, error.retryable)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum CoreMode {
    Auto,
    External,
    Bundled,
}

#[derive(Debug)]
struct ResolvedCli {
    mode: CoreMode,
    program: String,
    prefix_args: Vec<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HandshakePayload {
    ui_version: String,
    core_version: String,
    profile: String,
    contract_version: String,
    capabilities: Value,
    doctor: Value,
    root_dir: String,
    mode: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ReadArtifactPayload {
    contract_version: String,
    artifact_name: String,
    payload: Value,
    truncated: bool,
    bytes_read: usize,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TailEventsPayload {
    contract_version: String,
    events: Vec<Value>,
    next_cursor: u64,
    reset: bool,
    truncated: bool,
    bad_line_count: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SpawnedRunPayload {
    contract_version: String,
    job_id: String,
    profile: String,
    root_dir: String,
    process_id: Option<u32>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AssistantStartTurnPayload {
    contract_version: String,
    assistant_turn_id: String,
    session_id: String,
    process_id: Option<u32>,
    status: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AssistantStreamEventPayload {
    contract_version: String,
    assistant_turn_id: String,
    session_id: String,
    event: String,
    sequence: u64,
    timestamp_utc: String,
    data: Value,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ControlPlaneRunSubmitPayload {
    agent_id: String,
    prompt: String,
    operator_id: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ControlPlaneEvidenceExportPayload {
    run_id: String,
    output_dir: Option<String>,
}

#[derive(Debug)]
struct RawCliOutput {
    stdout: String,
    stderr: String,
    command: String,
}

#[derive(Debug)]
struct TailOutcome {
    events: Vec<Value>,
    next_cursor: u64,
    reset: bool,
    truncated: bool,
    bad_line_count: u64,
}

#[tauri::command]
pub async fn bridge_handshake(
    app: tauri::AppHandle,
    config: BridgeConfig,
) -> BridgeResult<HandshakePayload> {
    let profile = config.profile();
    let resource_dir = app_resource_dir(&app);
    let version = match run_cli_text_with_resource_dir(
        &config,
        vec!["--version".to_string()],
        resource_dir.as_deref(),
    )
    .await
    {
        Ok(text) => text.lines().next().unwrap_or_default().trim().to_string(),
        Err(error) => return BridgeResult::err(error),
    };

    let capabilities = match run_cli_json_with_resource_dir(
        &config,
        vec!["operator", "capabilities", "--json"],
        resource_dir.as_deref(),
    )
    .await
    {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };

    let doctor = match run_cli_json_with_resource_dir(
        &config,
        vec!["doctor", "--profile", profile.as_str()],
        resource_dir.as_deref(),
    )
    .await
    {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };

    let resolved = match resolve_cli_command(&config, resource_dir.as_deref()) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };

    BridgeResult::ok(HandshakePayload {
        ui_version: env!("CARGO_PKG_VERSION").to_string(),
        core_version: version,
        profile,
        contract_version: CONTRACT_VERSION.to_string(),
        capabilities,
        doctor,
        root_dir: config.root_dir(),
        mode: core_mode_name(resolved.mode).to_string(),
    })
}

#[tauri::command]
pub async fn bridge_approval_pending(
    app: tauri::AppHandle,
    config: BridgeConfig,
) -> BridgeResult<Value> {
    let config = trusted_artifact_command_config(&config);
    let identity = match resolve_trusted_artifact_identity(&config, &app).await {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    match run_cli_json_owned(
        &config,
        vec![
            "approval".to_string(),
            "pending".to_string(),
            "--profile".to_string(),
            config.profile(),
            "--workspace-id".to_string(),
            identity.workspace_id().to_string(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_approval_show(
    app: tauri::AppHandle,
    config: BridgeConfig,
    approval_id: String,
) -> BridgeResult<Value> {
    let config = trusted_artifact_command_config(&config);
    let identity = match resolve_trusted_artifact_identity(&config, &app).await {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    if approval_id.trim().is_empty() {
        return BridgeResult::err(BridgeError::new(
            "INVALID_INPUT",
            "approval_id is required",
            "",
            "approval show",
            false,
        ));
    }
    match run_cli_json_owned(
        &config,
        vec![
            "approval".to_string(),
            "show".to_string(),
            "--id".to_string(),
            approval_id.trim().to_string(),
            "--profile".to_string(),
            config.profile(),
            "--workspace-id".to_string(),
            identity.workspace_id().to_string(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_approval_decide(
    app: tauri::AppHandle,
    config: BridgeConfig,
    approval_id: String,
    approve: bool,
    reason: Option<String>,
    _operator_id: String,
) -> BridgeResult<Value> {
    let config = trusted_artifact_command_config(&config);
    let identity = match resolve_trusted_artifact_identity(&config, &app).await {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };

    let mut args = vec![
        "approval".to_string(),
        "decide".to_string(),
        "--id".to_string(),
        approval_id.trim().to_string(),
        if approve {
            "--approve".to_string()
        } else {
            "--reject".to_string()
        },
        "--actor".to_string(),
        identity.principal_id().to_string(),
        "--workspace-id".to_string(),
        identity.workspace_id().to_string(),
        "--profile".to_string(),
        config.profile(),
    ];
    if let Some(value) = reason {
        let normalized = value.trim();
        if !normalized.is_empty() {
            args.push("--reason".to_string());
            args.push(normalized.to_string());
        }
    }

    match run_cli_json_owned(&config, args).await {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_approval_execute(
    app: tauri::AppHandle,
    config: BridgeConfig,
    approval_id: String,
    _operator_id: String,
) -> BridgeResult<Value> {
    let config = trusted_artifact_command_config(&config);
    let identity = match resolve_trusted_artifact_identity(&config, &app).await {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };

    match run_cli_json_owned(
        &config,
        vec![
            "approval".to_string(),
            "execute".to_string(),
            "--id".to_string(),
            approval_id.trim().to_string(),
            "--actor".to_string(),
            identity.principal_id().to_string(),
            "--workspace-id".to_string(),
            identity.workspace_id().to_string(),
            "--profile".to_string(),
            config.profile(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_control_plane_doctor(config: BridgeConfig) -> BridgeResult<Value> {
    match run_cli_json_owned(
        &config,
        vec![
            "control-plane".to_string(),
            "doctor".to_string(),
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_control_plane_snapshot(config: BridgeConfig) -> BridgeResult<Value> {
    match run_cli_json_owned(
        &config,
        vec![
            "control-plane".to_string(),
            "snapshot".to_string(),
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_control_plane_agent_list(config: BridgeConfig) -> BridgeResult<Value> {
    match run_cli_json_owned(
        &config,
        vec![
            "control-plane".to_string(),
            "agent".to_string(),
            "list".to_string(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_control_plane_agent_register(
    config: BridgeConfig,
    spec_path: String,
) -> BridgeResult<Value> {
    let spec = match normalize_required_path(&spec_path, "spec_path", "control-plane agent") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    match run_cli_json_owned(
        &config,
        vec![
            "control-plane".to_string(),
            "agent".to_string(),
            "register".to_string(),
            "--spec".to_string(),
            spec,
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_control_plane_policy_simulate(
    config: BridgeConfig,
    agent_id: String,
) -> BridgeResult<Value> {
    let agent = match normalize_control_plane_id(&agent_id, "agent_id") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    match run_cli_json_owned(
        &config,
        vec![
            "control-plane".to_string(),
            "policy".to_string(),
            "simulate".to_string(),
            "--agent-id".to_string(),
            agent,
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_control_plane_run_submit(
    config: BridgeConfig,
    payload: ControlPlaneRunSubmitPayload,
) -> BridgeResult<Value> {
    let agent = match normalize_control_plane_id(&payload.agent_id, "agent_id") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let prompt = match normalize_required_text(&payload.prompt, "prompt", "control-plane run") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let actor = match normalize_actor(&payload.operator_id) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    match run_cli_json_owned(
        &config,
        vec![
            "control-plane".to_string(),
            "run".to_string(),
            "submit".to_string(),
            "--agent-id".to_string(),
            agent,
            "--once".to_string(),
            prompt,
            "--actor".to_string(),
            actor,
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_control_plane_evidence_export(
    config: BridgeConfig,
    payload: ControlPlaneEvidenceExportPayload,
) -> BridgeResult<Value> {
    let run_id = match normalize_control_plane_id(&payload.run_id, "run_id") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let mut args = vec![
        "control-plane".to_string(),
        "evidence".to_string(),
        "export".to_string(),
        "--run-id".to_string(),
        run_id,
        "--profile".to_string(),
        config.profile(),
        "--json".to_string(),
    ];
    if let Some(output_dir) = payload.output_dir {
        if !output_dir.trim().is_empty() {
            args.push("--output".to_string());
            args.push(output_dir.trim().to_string());
        }
    }
    match run_cli_json_owned(&config, args).await {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_control_plane_evidence_verify(
    config: BridgeConfig,
    manifest_path: String,
) -> BridgeResult<Value> {
    let path = match normalize_required_path(&manifest_path, "manifest_path", "evidence verify") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    match run_cli_json_owned(
        &config,
        vec![
            "control-plane".to_string(),
            "evidence".to_string(),
            "verify".to_string(),
            "--path".to_string(),
            path,
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_control_plane_claims_verify(config: BridgeConfig) -> BridgeResult<Value> {
    match run_cli_json_owned(
        &config,
        vec![
            "control-plane".to_string(),
            "claims".to_string(),
            "verify".to_string(),
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_team_list(config: BridgeConfig, since: Option<String>) -> BridgeResult<Value> {
    let mut args = vec![
        "team".to_string(),
        "list".to_string(),
        "--root-dir".to_string(),
        config.root_dir(),
        "--json".to_string(),
    ];
    if let Some(value) = since {
        let normalized = value.trim();
        if !normalized.is_empty() {
            args.push("--since".to_string());
            args.push(normalized.to_string());
        }
    }

    match run_cli_json_owned(&config, args).await {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_team_submit(
    config: BridgeConfig,
    spec_path: String,
    request: String,
    case_id: Option<String>,
    job_id: Option<String>,
    provider: Option<String>,
    fallback_provider: Option<String>,
    model: Option<String>,
    hf_model_id: Option<String>,
    safety_options: Option<Value>,
) -> BridgeResult<SpawnedRunPayload> {
    let _ = safety_options;
    let spec = match normalize_required_path(&spec_path, "spec_path", "team run") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let request = match normalize_required_text(&request, "request", "team run") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let run_job_id = match job_id.as_deref().map(normalize_job_id).transpose() {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };

    let generated_job_id = run_job_id.unwrap_or_else(generate_job_id);
    let mut args = vec![
        "team".to_string(),
        "run".to_string(),
        "--spec".to_string(),
        spec,
        "--once".to_string(),
        request,
        "--job-id".to_string(),
        generated_job_id.clone(),
        "--profile".to_string(),
        config.profile(),
        "--json".to_string(),
    ];
    push_optional_arg(&mut args, "--case-id", case_id.as_deref());
    push_optional_arg(&mut args, "--provider", provider.as_deref());
    push_optional_arg(
        &mut args,
        "--fallback-provider",
        fallback_provider.as_deref(),
    );
    push_optional_arg(&mut args, "--model", model.as_deref());
    push_optional_arg(&mut args, "--hf-model-id", hf_model_id.as_deref());

    match spawn_cli_background(&config, args).await {
        Ok(process_id) => BridgeResult::ok(SpawnedRunPayload {
            contract_version: CONTRACT_VERSION.to_string(),
            job_id: generated_job_id,
            profile: config.profile(),
            root_dir: config.root_dir(),
            process_id,
        }),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_team_resume_submit(
    config: BridgeConfig,
    spec_path: String,
    source_job_id: String,
    resume_job_id: Option<String>,
    provider: Option<String>,
    fallback_provider: Option<String>,
    model: Option<String>,
    hf_model_id: Option<String>,
    safety_options: Option<Value>,
) -> BridgeResult<SpawnedRunPayload> {
    let _ = safety_options;
    let spec = match normalize_required_path(&spec_path, "spec_path", "team resume") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let source_job_id = match normalize_job_id(&source_job_id) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let resume_job_id = match resume_job_id.as_deref().map(normalize_job_id).transpose() {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let generated_job_id = resume_job_id.unwrap_or_else(|| format!("{source_job_id}-resume-ui"));
    let mut args = vec![
        "team".to_string(),
        "resume".to_string(),
        "--spec".to_string(),
        spec,
        "--job-id".to_string(),
        source_job_id,
        "--resume-job-id".to_string(),
        generated_job_id.clone(),
        "--root-dir".to_string(),
        config.root_dir(),
        "--profile".to_string(),
        config.profile(),
        "--json".to_string(),
    ];
    push_optional_arg(&mut args, "--provider", provider.as_deref());
    push_optional_arg(
        &mut args,
        "--fallback-provider",
        fallback_provider.as_deref(),
    );
    push_optional_arg(&mut args, "--model", model.as_deref());
    push_optional_arg(&mut args, "--hf-model-id", hf_model_id.as_deref());

    match spawn_cli_background(&config, args).await {
        Ok(process_id) => BridgeResult::ok(SpawnedRunPayload {
            contract_version: CONTRACT_VERSION.to_string(),
            job_id: generated_job_id,
            profile: config.profile(),
            root_dir: config.root_dir(),
            process_id,
        }),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_computer_use_submit(
    config: BridgeConfig,
    request: String,
    case_id: Option<String>,
    job_id: Option<String>,
    mode: Option<String>,
    runtime: Option<String>,
    provider: Option<String>,
    fallback_provider: Option<String>,
    model: Option<String>,
    hf_model_id: Option<String>,
) -> BridgeResult<SpawnedRunPayload> {
    let request = match normalize_required_text(&request, "request", "computer-use run") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let run_job_id = match job_id.as_deref().map(normalize_job_id).transpose() {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let generated_job_id = run_job_id.unwrap_or_else(generate_job_id);
    let mut args = vec![
        "computer-use".to_string(),
        "run".to_string(),
        "--once".to_string(),
        request,
        "--job-id".to_string(),
        generated_job_id.clone(),
        "--root-dir".to_string(),
        config.root_dir(),
        "--profile".to_string(),
        config.profile(),
        "--json".to_string(),
    ];
    push_optional_arg(&mut args, "--case-id", case_id.as_deref());
    push_optional_arg(&mut args, "--mode", mode.as_deref());
    let runtime = match normalize_computer_use_runtime(runtime.as_deref()) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    push_optional_arg(&mut args, "--runtime", runtime.as_deref());
    push_optional_arg(&mut args, "--provider", provider.as_deref());
    push_optional_arg(
        &mut args,
        "--fallback-provider",
        fallback_provider.as_deref(),
    );
    push_optional_arg(&mut args, "--model", model.as_deref());
    push_optional_arg(&mut args, "--hf-model-id", hf_model_id.as_deref());

    match spawn_cli_background(&config, args).await {
        Ok(process_id) => BridgeResult::ok(SpawnedRunPayload {
            contract_version: CONTRACT_VERSION.to_string(),
            job_id: generated_job_id,
            profile: config.profile(),
            root_dir: config.root_dir(),
            process_id,
        }),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_computer_use_summary(
    config: BridgeConfig,
    limit: Option<u32>,
) -> BridgeResult<Value> {
    let mut args = vec![
        "computer-use".to_string(),
        "summary".to_string(),
        "--root-dir".to_string(),
        config.root_dir(),
        "--profile".to_string(),
        config.profile(),
        "--json".to_string(),
    ];
    if let Some(value) = limit {
        args.push("--limit".to_string());
        args.push(value.clamp(1, 200).to_string());
    }

    match run_cli_json_owned(&config, args).await {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_computer_use_pause(
    config: BridgeConfig,
    job_id: String,
) -> BridgeResult<Value> {
    let normalized = match normalize_job_id(&job_id) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    match run_cli_json_owned(
        &config,
        vec![
            "computer-use".to_string(),
            "pause".to_string(),
            "--job-id".to_string(),
            normalized,
            "--root-dir".to_string(),
            config.root_dir(),
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_computer_use_resume(
    config: BridgeConfig,
    job_id: String,
) -> BridgeResult<Value> {
    let normalized = match normalize_job_id(&job_id) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    match run_cli_json_owned(
        &config,
        vec![
            "computer-use".to_string(),
            "resume".to_string(),
            "--job-id".to_string(),
            normalized,
            "--root-dir".to_string(),
            config.root_dir(),
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_computer_use_stop(config: BridgeConfig, job_id: String) -> BridgeResult<Value> {
    let normalized = match normalize_job_id(&job_id) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    match run_cli_json_owned(
        &config,
        vec![
            "computer-use".to_string(),
            "stop".to_string(),
            "--job-id".to_string(),
            normalized,
            "--root-dir".to_string(),
            config.root_dir(),
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_computer_use_state(
    config: BridgeConfig,
    job_id: String,
) -> BridgeResult<Value> {
    let normalized = match normalize_job_id(&job_id) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    match run_cli_json_owned(
        &config,
        vec![
            "computer-use".to_string(),
            "state".to_string(),
            "--job-id".to_string(),
            normalized,
            "--root-dir".to_string(),
            config.root_dir(),
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_team_replay(config: BridgeConfig, job_id: String) -> BridgeResult<Value> {
    let normalized = match normalize_job_id(&job_id) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };

    match run_cli_json_owned(
        &config,
        vec![
            "team".to_string(),
            "replay".to_string(),
            "--job-id".to_string(),
            normalized,
            "--root-dir".to_string(),
            config.root_dir(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_team_status(config: BridgeConfig, job_id: String) -> BridgeResult<Value> {
    let normalized = match normalize_job_id(&job_id) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };

    match run_cli_json_owned(
        &config,
        vec![
            "team".to_string(),
            "status".to_string(),
            "--job-id".to_string(),
            normalized,
            "--root-dir".to_string(),
            config.root_dir(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_team_export(
    config: BridgeConfig,
    job_id: String,
    export_dir: String,
) -> BridgeResult<Value> {
    let normalized = match normalize_job_id(&job_id) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let export_path = export_dir.trim();
    if export_path.is_empty() {
        return BridgeResult::err(BridgeError::new(
            "INVALID_INPUT",
            "export_dir is required",
            "",
            "team artifacts",
            false,
        ));
    }

    match run_cli_json_owned(
        &config,
        vec![
            "team".to_string(),
            "artifacts".to_string(),
            "--job-id".to_string(),
            normalized,
            "--root-dir".to_string(),
            config.root_dir(),
            "--export".to_string(),
            export_path.to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_config_resolve(
    config: BridgeConfig,
    provider: Option<String>,
    fallback_provider: Option<String>,
    model: Option<String>,
    hf_model_id: Option<String>,
) -> BridgeResult<Value> {
    let mut args = vec![
        "config".to_string(),
        "resolve".to_string(),
        "--profile".to_string(),
        config.profile(),
        "--json".to_string(),
    ];
    push_optional_arg(&mut args, "--provider", provider.as_deref());
    push_optional_arg(
        &mut args,
        "--fallback-provider",
        fallback_provider.as_deref(),
    );
    push_optional_arg(&mut args, "--model", model.as_deref());
    push_optional_arg(&mut args, "--hf-model-id", hf_model_id.as_deref());

    match run_cli_json_owned(&config, args).await {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_assistant_provider_models(
    config: BridgeConfig,
    profile: Option<String>,
    provider: Option<String>,
    refresh: Option<bool>,
) -> BridgeResult<Value> {
    let profile =
        match normalize_optional_cli_token(profile.as_deref(), "profile", "provider models") {
            Ok(value) => value.unwrap_or_else(|| config.profile()),
            Err(error) => return BridgeResult::err(error),
        };
    let provider =
        match normalize_optional_cli_token(provider.as_deref(), "provider", "provider models") {
            Ok(value) => value,
            Err(error) => return BridgeResult::err(error),
        };

    let mut args = vec![
        "provider".to_string(),
        "models".to_string(),
        "--profile".to_string(),
        profile,
        "--json".to_string(),
    ];
    push_optional_arg(&mut args, "--provider", provider.as_deref());
    if refresh.unwrap_or(false) {
        args.push("--refresh".to_string());
    }

    match run_cli_json_owned(&config, args).await {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_auth_whoami(config: BridgeConfig) -> BridgeResult<Value> {
    match run_cli_json_owned(
        &config,
        vec![
            "auth".to_string(),
            "whoami".to_string(),
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_auth_check(config: BridgeConfig, permission: String) -> BridgeResult<Value> {
    let permission = match normalize_required_text(&permission, "permission", "auth check") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    match run_cli_json_owned(
        &config,
        vec![
            "auth".to_string(),
            "check".to_string(),
            "--profile".to_string(),
            config.profile(),
            "--permission".to_string(),
            permission,
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_security_baseline(config: BridgeConfig) -> BridgeResult<Value> {
    match run_cli_json_owned(
        &config,
        vec![
            "security".to_string(),
            "baseline".to_string(),
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_install_rehearsal(
    config: BridgeConfig,
    target_root: Option<String>,
    output: Option<String>,
    mode: Option<String>,
) -> BridgeResult<Value> {
    let mut args = vec![
        "control-plane".to_string(),
        "install".to_string(),
        "rehearsal".to_string(),
        "--profile".to_string(),
        config.profile(),
        "--target-root".to_string(),
        target_root.unwrap_or_else(|| ".imperaos/rehearsal/design-partner".to_string()),
        "--mode".to_string(),
        mode.unwrap_or_else(|| "source-cli".to_string()),
        "--output".to_string(),
        output.unwrap_or_else(|| "artifacts/install-rehearsal/report.json".to_string()),
        "--json".to_string(),
    ];
    match run_cli_json_owned(&config, std::mem::take(&mut args)).await {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_security_review(
    config: BridgeConfig,
    output_root: Option<String>,
    evidence_root: Option<String>,
) -> BridgeResult<Value> {
    let mut args = vec![
        "control-plane".to_string(),
        "security".to_string(),
        "review".to_string(),
        "--profile".to_string(),
        config.profile(),
        "--output-root".to_string(),
        output_root.unwrap_or_else(|| "artifacts/security-review".to_string()),
        "--evidence-root".to_string(),
        evidence_root.unwrap_or_else(|| "artifacts/evidence-corpus/valid".to_string()),
        "--json".to_string(),
    ];
    match run_cli_json_owned(&config, std::mem::take(&mut args)).await {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_keys_status(config: BridgeConfig) -> BridgeResult<Value> {
    match run_cli_json_owned(
        &config,
        vec![
            "keys".to_string(),
            "status".to_string(),
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_keys_verify(config: BridgeConfig, path: String) -> BridgeResult<Value> {
    let path = match normalize_required_text(&path, "path", "keys verify") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    match run_cli_json_owned(
        &config,
        vec![
            "keys".to_string(),
            "verify".to_string(),
            "--profile".to_string(),
            config.profile(),
            "--path".to_string(),
            path,
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_keys_rotate_plan(
    config: BridgeConfig,
    next_key_id: Option<String>,
    activate_at: Option<String>,
    retire_after: Option<String>,
) -> BridgeResult<Value> {
    let mut args = vec![
        "keys".to_string(),
        "rotate-plan".to_string(),
        "--profile".to_string(),
        config.profile(),
        "--json".to_string(),
    ];
    push_optional_arg(&mut args, "--next-key-id", next_key_id.as_deref());
    push_optional_arg(&mut args, "--activate-at", activate_at.as_deref());
    push_optional_arg(&mut args, "--retire-after", retire_after.as_deref());

    match run_cli_json_owned(&config, args).await {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_support_bundle_export(
    config: BridgeConfig,
    output: Option<String>,
) -> BridgeResult<Value> {
    let mut args = vec![
        "support".to_string(),
        "bundle".to_string(),
        "export".to_string(),
        "--profile".to_string(),
        config.profile(),
        "--json".to_string(),
    ];
    push_optional_arg(&mut args, "--output", output.as_deref());
    match run_cli_json_owned(&config, args).await {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_backup_create(
    config: BridgeConfig,
    output_dir: Option<String>,
) -> BridgeResult<Value> {
    let mut args = vec![
        "backup".to_string(),
        "create".to_string(),
        "--profile".to_string(),
        config.profile(),
        "--json".to_string(),
    ];
    push_optional_arg(&mut args, "--output-dir", output_dir.as_deref());
    match run_cli_json_owned(&config, args).await {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_backup_verify(config: BridgeConfig, backup_dir: String) -> BridgeResult<Value> {
    let backup_dir = match normalize_required_text(&backup_dir, "backup_dir", "backup verify") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    match run_cli_json_owned(
        &config,
        vec![
            "backup".to_string(),
            "verify".to_string(),
            "--profile".to_string(),
            config.profile(),
            "--backup-dir".to_string(),
            backup_dir,
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_restore_verify(
    config: BridgeConfig,
    backup_dir: String,
) -> BridgeResult<Value> {
    let backup_dir = match normalize_required_text(&backup_dir, "backup_dir", "restore verify") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    match run_cli_json_owned(
        &config,
        vec![
            "restore".to_string(),
            "verify".to_string(),
            "--profile".to_string(),
            config.profile(),
            "--backup-dir".to_string(),
            backup_dir,
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_migrate_plan(config: BridgeConfig) -> BridgeResult<Value> {
    match run_cli_json_owned(
        &config,
        vec![
            "migrate".to_string(),
            "plan".to_string(),
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_migrate_apply_dry_run(config: BridgeConfig) -> BridgeResult<Value> {
    match run_cli_json_owned(
        &config,
        vec![
            "migrate".to_string(),
            "apply".to_string(),
            "--profile".to_string(),
            config.profile(),
            "--dry-run".to_string(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_metrics_snapshot(config: BridgeConfig) -> BridgeResult<Value> {
    match run_cli_json_owned(
        &config,
        vec![
            "metrics".to_string(),
            "snapshot".to_string(),
            "--profile".to_string(),
            config.profile(),
            "--json".to_string(),
        ],
    )
    .await
    {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_ga_readiness(
    config: BridgeConfig,
    report: Option<String>,
    qualification_report: Option<String>,
) -> BridgeResult<Value> {
    let mut args = vec![
        "ga".to_string(),
        "readiness".to_string(),
        "--profile".to_string(),
        config.profile(),
        "--json".to_string(),
    ];
    push_optional_arg(&mut args, "--report", report.as_deref());
    push_optional_arg(
        &mut args,
        "--qualification-report",
        qualification_report.as_deref(),
    );
    match run_cli_json_owned(&config, args).await {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_qualification_run(
    config: BridgeConfig,
    mode: Option<String>,
    soak_hours: Option<f64>,
    output_root: Option<String>,
    workloads: Option<String>,
    merge_from_report: Option<String>,
    provider: Option<String>,
    fallback_provider: Option<String>,
    model: Option<String>,
    hf_model_id: Option<String>,
) -> BridgeResult<Value> {
    let mut args = vec![
        "qualification".to_string(),
        "run".to_string(),
        "--profile".to_string(),
        config.profile(),
        "--json".to_string(),
    ];
    push_optional_arg(&mut args, "--mode", mode.as_deref());
    if let Some(hours) = soak_hours {
        args.push("--soak-hours".to_string());
        args.push(hours.to_string());
    }
    push_optional_arg(&mut args, "--output-root", output_root.as_deref());
    push_optional_arg(&mut args, "--workloads", workloads.as_deref());
    push_optional_arg(
        &mut args,
        "--merge-from-report",
        merge_from_report.as_deref(),
    );
    push_optional_arg(&mut args, "--provider", provider.as_deref());
    push_optional_arg(
        &mut args,
        "--fallback-provider",
        fallback_provider.as_deref(),
    );
    push_optional_arg(&mut args, "--model", model.as_deref());
    push_optional_arg(&mut args, "--hf-model-id", hf_model_id.as_deref());

    match run_cli_json_owned(&config, args).await {
        Ok(value) => BridgeResult::ok(value),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_assistant_start_turn(
    app: tauri::AppHandle,
    config: BridgeConfig,
    assistant_turn_id: String,
    session_id: String,
    user_message: String,
    compiled_prompt: String,
    provider: Option<String>,
    provider_id: Option<String>,
    fallback_provider: Option<String>,
    fallback_provider_id: Option<String>,
    model: Option<String>,
    hf_model_id: Option<String>,
    reasoning_effort: Option<String>,
    speed_profile: Option<String>,
    approval_profile: Option<String>,
) -> BridgeResult<AssistantStartTurnPayload> {
    let config = trusted_artifact_command_config(&config);
    let assistant_turn_id = match normalize_assistant_turn_id(&assistant_turn_id) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let session_id = match normalize_session_id(&session_id) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let _user_message = match normalize_assistant_prompt(
        &user_message,
        DEFAULT_ASSISTANT_PROMPT_MAX_CHARS,
        "user_message",
    ) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let compiled_prompt = match normalize_assistant_prompt(
        &compiled_prompt,
        DEFAULT_ASSISTANT_PROMPT_MAX_CHARS,
        "compiled_prompt",
    ) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let provider =
        match normalize_optional_cli_token(provider.as_deref(), "provider", "assistant start") {
            Ok(value) => value,
            Err(error) => return BridgeResult::err(error),
        };
    let provider_id = match normalize_optional_cli_token(
        provider_id.as_deref(),
        "provider_id",
        "assistant start",
    ) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let fallback_provider = match normalize_optional_cli_token(
        fallback_provider.as_deref(),
        "fallback_provider",
        "assistant start",
    ) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let fallback_provider_id = match normalize_optional_cli_token(
        fallback_provider_id.as_deref(),
        "fallback_provider_id",
        "assistant start",
    ) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let model = match normalize_optional_cli_token(model.as_deref(), "model", "assistant start") {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let hf_model_id = match normalize_optional_cli_token(
        hf_model_id.as_deref(),
        "hf_model_id",
        "assistant start",
    ) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let reasoning_effort = match normalize_runtime_choice(
        reasoning_effort.as_deref(),
        "medium",
        &["low", "medium", "high", "very_high"],
        "reasoning_effort",
    ) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let speed_profile = match normalize_runtime_choice(
        speed_profile.as_deref(),
        "standard",
        &["standard", "fast"],
        "speed_profile",
    ) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let approval_profile = match normalize_runtime_choice(
        approval_profile.as_deref(),
        "risk_based",
        &["always_ask", "risk_based", "policy_automatic"],
        "approval_profile",
    ) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };

    let resource_dir = app_resource_dir(&app);
    let resolved = match resolve_cli_command(&config, resource_dir.as_deref()) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let identity =
        match resolve_trusted_artifact_identity(&trusted_artifact_bridge_config(), &app).await {
            Ok(value) => value,
            Err(error) => return BridgeResult::err(error),
        };
    let runtime_root = default_cli_workdir().unwrap_or_else(|| PathBuf::from("."));
    let artifact_root = runtime_root.join(".imperaos").join("artifacts");
    let prompt_dir = std::env::temp_dir().join("imperaos-assistant-prompts");
    if let Err(error) = std::fs::create_dir_all(&prompt_dir) {
        return BridgeResult::err(BridgeError::new(
            "CLI_FAILED",
            format!("Assistant prompt directory could not be prepared: {error}"),
            "",
            "assistant prompt preparation",
            true,
        ));
    }
    cleanup_stale_assistant_prompt_files(&prompt_dir, Duration::from_secs(24 * 60 * 60));
    let prompt_path = prompt_dir.join(format!("{assistant_turn_id}-{}.md", uuid::Uuid::new_v4()));
    let prompt_guard = match create_assistant_prompt_file_with_writer(&prompt_path, |file| {
        std::io::Write::write_all(file, compiled_prompt.as_bytes())
    }) {
        Ok(guard) => guard,
        Err(error) => {
            return BridgeResult::err(BridgeError::new(
                "CLI_FAILED",
                format!("Assistant prompt could not be prepared: {error}"),
                "",
                "assistant prompt preparation",
                true,
            ))
        }
    };
    let args = build_assistant_turn_args(
        &config,
        &prompt_path,
        &assistant_turn_id,
        &session_id,
        provider.as_deref(),
        provider_id.as_deref(),
        fallback_provider.as_deref(),
        fallback_provider_id.as_deref(),
        model.as_deref(),
        hf_model_id.as_deref(),
        &reasoning_effort,
        &speed_profile,
        &approval_profile,
        &artifact_root,
        &identity,
    );
    let command_preview =
        format_assistant_command_preview(&resolved.program, &resolved.prefix_args, &args);

    let mut command = Command::new(&resolved.program);
    command.args(&resolved.prefix_args);
    command.args(&args);
    command.stdout(Stdio::piped());
    command.stderr(Stdio::piped());
    configure_cli_env(&mut command, &config, &resolved);
    configure_cli_workdir(&mut command);

    let mut child = match command.spawn() {
        Ok(value) => value,
        Err(error) => {
            let _ = std::fs::remove_file(&prompt_path);
            let code = if error.kind() == std::io::ErrorKind::NotFound {
                "CLI_NOT_FOUND"
            } else {
                "CLI_FAILED"
            };
            return BridgeResult::err(BridgeError::new(
                code,
                error.to_string(),
                "",
                command_preview,
                code != "CLI_NOT_FOUND",
            ));
        }
    };

    let process_id = child.id();
    if let Some(process_id) = process_id {
        app.state::<AssistantProcessRegistry>()
            .turns
            .lock()
            .await
            .insert(
                assistant_turn_id.clone(),
                AssistantProcessRef {
                    process_id,
                    session_id: session_id.clone(),
                    prompt_path: prompt_path.clone(),
                },
            );
    }
    let stdout = match child.stdout.take() {
        Some(value) => value,
        None => {
            if process_id.is_some() {
                app.state::<AssistantProcessRegistry>()
                    .turns
                    .lock()
                    .await
                    .remove(&assistant_turn_id);
            }
            let _ = child.kill().await;
            let _ = std::fs::remove_file(&prompt_path);
            return BridgeResult::err(BridgeError::new(
                "CLI_FAILED",
                "Assistant process stdout was not available.",
                "",
                command_preview,
                true,
            ));
        }
    };
    let stderr = child.stderr.take();
    let task_app = app.clone();
    let task_turn_id = assistant_turn_id.clone();
    let task_session_id = session_id.clone();
    let task_command_preview = command_preview.clone();
    let task_prompt_guard = prompt_guard;

    tokio::spawn(async move {
        let _prompt_guard = task_prompt_guard;
        let stderr_task = tokio::spawn(read_assistant_stderr_preview(stderr));
        let stream_result = stream_assistant_stdout(
            task_app.clone(),
            stdout,
            task_turn_id.clone(),
            task_session_id.clone(),
        )
        .await;
        let observed_events = match stream_result {
            Ok(count) => count,
            Err(error) => {
                if !task_app
                    .state::<AssistantProcessRegistry>()
                    .turns
                    .lock()
                    .await
                    .contains_key(&task_turn_id)
                {
                    return;
                }
                let _ = emit_assistant_error(&task_app, &task_turn_id, &task_session_id, 1, &error);
                1
            }
        };

        let stderr_preview = stderr_task.await.unwrap_or_default();
        match child.wait().await {
            Ok(status) if status.success() => {}
            Ok(status) => {
                if !task_app
                    .state::<AssistantProcessRegistry>()
                    .turns
                    .lock()
                    .await
                    .contains_key(&task_turn_id)
                {
                    return;
                }
                let error = BridgeError::new(
                    "CLI_FAILED",
                    format!("Assistant command exited with status {status}."),
                    stderr_preview,
                    task_command_preview,
                    false,
                );
                let _ = emit_assistant_error(
                    &task_app,
                    &task_turn_id,
                    &task_session_id,
                    observed_events + 1,
                    &error,
                );
            }
            Err(error) => {
                if !task_app
                    .state::<AssistantProcessRegistry>()
                    .turns
                    .lock()
                    .await
                    .contains_key(&task_turn_id)
                {
                    return;
                }
                let error = BridgeError::new(
                    "CLI_FAILED",
                    format!("Failed to wait for assistant process: {error}"),
                    stderr_preview,
                    task_command_preview,
                    true,
                );
                let _ = emit_assistant_error(
                    &task_app,
                    &task_turn_id,
                    &task_session_id,
                    observed_events + 1,
                    &error,
                );
            }
        }
        task_app
            .state::<AssistantProcessRegistry>()
            .turns
            .lock()
            .await
            .remove(&task_turn_id);
    });

    BridgeResult::ok(AssistantStartTurnPayload {
        contract_version: CONTRACT_VERSION.to_string(),
        assistant_turn_id,
        session_id,
        process_id,
        status: "started".to_string(),
    })
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AssistantCancelTurnPayload {
    contract_version: String,
    assistant_turn_id: String,
    session_id: String,
    process_id: u32,
    status: String,
}

#[tauri::command]
pub async fn bridge_assistant_cancel_turn(
    app: tauri::AppHandle,
    assistant_turn_id: String,
) -> BridgeResult<AssistantCancelTurnPayload> {
    let assistant_turn_id = match normalize_assistant_turn_id(&assistant_turn_id) {
        Ok(value) => value,
        Err(error) => return BridgeResult::err(error),
    };
    let process_ref = app
        .state::<AssistantProcessRegistry>()
        .turns
        .lock()
        .await
        .remove(&assistant_turn_id);
    let Some(process_ref) = process_ref else {
        return BridgeResult::err(BridgeError::new(
            "ASSISTANT_TURN_NOT_RUNNING",
            "Assistant turn is not running or has already completed.",
            "",
            "assistant cancel",
            false,
        ));
    };

    let termination = terminate_process(process_ref.process_id).await;
    let _ = std::fs::remove_file(&process_ref.prompt_path);
    if let Err(error) = termination {
        return BridgeResult::err(error);
    }

    let payload = assistant_event_payload(
        &assistant_turn_id,
        &process_ref.session_id,
        "cancelled",
        9_000_000_000,
        json!({
            "message": "Assistant turn cancelled by operator.",
            "processId": process_ref.process_id,
        }),
    );
    if let Err(error) = emit_assistant_payload(&app, &payload) {
        return BridgeResult::err(error);
    }

    BridgeResult::ok(AssistantCancelTurnPayload {
        contract_version: CONTRACT_VERSION.to_string(),
        assistant_turn_id,
        session_id: process_ref.session_id,
        process_id: process_ref.process_id,
        status: "cancelled".to_string(),
    })
}

#[tauri::command]
pub async fn bridge_read_artifact(
    root_dir: String,
    job_id: String,
    artifact_name: String,
    max_bytes: Option<usize>,
) -> BridgeResult<ReadArtifactPayload> {
    match read_artifact_impl(&root_dir, &job_id, &artifact_name, max_bytes) {
        Ok(payload) => BridgeResult::ok(payload),
        Err(error) => BridgeResult::err(error),
    }
}

#[tauri::command]
pub async fn bridge_tail_events(
    root_dir: String,
    job_id: String,
    cursor: Option<u64>,
    max_bytes: Option<usize>,
    max_lines: Option<usize>,
) -> BridgeResult<TailEventsPayload> {
    match tail_events_impl(
        &root_dir,
        &job_id,
        cursor.unwrap_or(0),
        max_bytes.unwrap_or(DEFAULT_MAX_BYTES),
        max_lines.unwrap_or(DEFAULT_MAX_LINES),
    ) {
        Ok(result) => BridgeResult::ok(TailEventsPayload {
            contract_version: CONTRACT_VERSION.to_string(),
            events: result.events,
            next_cursor: result.next_cursor,
            reset: result.reset,
            truncated: result.truncated,
            bad_line_count: result.bad_line_count,
        }),
        Err(error) => BridgeResult::err(error),
    }
}

fn normalize_assistant_turn_id(value: &str) -> Result<String, BridgeError> {
    normalize_assistant_id(value, "assistant_turn_id")
}

fn normalize_session_id(value: &str) -> Result<String, BridgeError> {
    normalize_assistant_id(value, "session_id")
}

fn normalize_assistant_id(value: &str, field: &str) -> Result<String, BridgeError> {
    let normalized = value.trim();
    let valid = !normalized.is_empty()
        && normalized.len() <= 128
        && normalized
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '.'));
    if valid {
        return Ok(normalized.to_string());
    }
    Err(BridgeError::new(
        "INVALID_INPUT",
        format!("{field} must be 1-128 chars using [a-zA-Z0-9._-]"),
        "",
        "assistant id validation",
        false,
    ))
}

fn normalize_assistant_prompt(
    value: &str,
    max_chars: usize,
    field: &str,
) -> Result<String, BridgeError> {
    let normalized = value.trim();
    if normalized.is_empty() {
        return Err(BridgeError::new(
            "INVALID_INPUT",
            format!("{field} is required"),
            "",
            "assistant prompt validation",
            false,
        ));
    }
    if normalized.chars().count() > max_chars {
        return Err(BridgeError::new(
            "INVALID_INPUT",
            format!("{field} exceeds {max_chars} characters"),
            "",
            "assistant prompt validation",
            false,
        ));
    }
    Ok(normalized.to_string())
}

fn normalize_runtime_choice(
    value: Option<&str>,
    default: &str,
    allowed: &[&str],
    field: &str,
) -> Result<String, BridgeError> {
    let normalized = value.unwrap_or(default).trim();
    if allowed.contains(&normalized) {
        return Ok(normalized.to_string());
    }
    Err(BridgeError::new(
        "INVALID_INPUT",
        format!("{field} is not supported"),
        "",
        "assistant start",
        false,
    ))
}

fn build_assistant_turn_args(
    config: &BridgeConfig,
    prompt_path: &Path,
    assistant_turn_id: &str,
    session_id: &str,
    provider: Option<&str>,
    provider_id: Option<&str>,
    fallback_provider: Option<&str>,
    fallback_provider_id: Option<&str>,
    model: Option<&str>,
    hf_model_id: Option<&str>,
    reasoning_effort: &str,
    speed_profile: &str,
    approval_profile: &str,
    artifact_root: &Path,
    identity: &TrustedArtifactIdentity,
) -> Vec<String> {
    let mut args = vec![
        "assistant".to_string(),
        "turn".to_string(),
        "--profile".to_string(),
        config.profile(),
        "--session-id".to_string(),
        session_id.to_string(),
        "--turn-id".to_string(),
        assistant_turn_id.to_string(),
        "--prompt-file".to_string(),
        prompt_path.to_string_lossy().to_string(),
        "--stream-json".to_string(),
        "--artifact-root".to_string(),
        artifact_root.to_string_lossy().to_string(),
        "--artifact-workspace-id".to_string(),
        identity.workspace_id().to_string(),
        "--artifact-principal-id".to_string(),
        identity.principal_id().to_string(),
        "--artifact-prompt-data-class".to_string(),
        "regulated".to_string(),
    ];
    for role in identity.roles() {
        args.push("--artifact-role".to_string());
        args.push(role.clone());
    }
    push_optional_arg(&mut args, "--provider", provider);
    push_optional_arg(&mut args, "--provider-id", provider_id);
    push_optional_arg(&mut args, "--fallback-provider", fallback_provider);
    push_optional_arg(&mut args, "--fallback-provider-id", fallback_provider_id);
    push_optional_arg(&mut args, "--model", model);
    push_optional_arg(&mut args, "--hf-model-id", hf_model_id);
    push_optional_arg(&mut args, "--reasoning-effort", Some(reasoning_effort));
    push_optional_arg(&mut args, "--speed-profile", Some(speed_profile));
    push_optional_arg(&mut args, "--approval-profile", Some(approval_profile));
    args
}

#[cfg(test)]
fn build_assistant_chat_args(
    config: &BridgeConfig,
    user_message: &str,
    session_id: &str,
    provider: Option<&str>,
    provider_id: Option<&str>,
    fallback_provider: Option<&str>,
    fallback_provider_id: Option<&str>,
    model: Option<&str>,
    hf_model_id: Option<&str>,
) -> Vec<String> {
    let mut args = vec![
        "chat".to_string(),
        "--profile".to_string(),
        config.profile(),
        "--once".to_string(),
        user_message.to_string(),
        "--stdio-json".to_string(),
        "--stream".to_string(),
        "--session-id".to_string(),
        session_id.to_string(),
    ];
    push_optional_arg(&mut args, "--provider", provider);
    push_optional_arg(&mut args, "--provider-id", provider_id);
    push_optional_arg(&mut args, "--fallback-provider", fallback_provider);
    push_optional_arg(&mut args, "--fallback-provider-id", fallback_provider_id);
    push_optional_arg(&mut args, "--model", model);
    push_optional_arg(&mut args, "--hf-model-id", hf_model_id);
    args
}

fn format_assistant_command_preview(program: &str, prefix: &[String], args: &[String]) -> String {
    let sanitized_args = args
        .iter()
        .enumerate()
        .map(|(index, value)| {
            if index > 0 && args[index - 1] == "--once" {
                "[user_message]".to_string()
            } else if index > 0 && args[index - 1] == "--prompt-file" {
                "[compiled_prompt_file]".to_string()
            } else if index > 0 && args[index - 1] == "--artifact-root" {
                "[artifact_root]".to_string()
            } else if index > 0 && args[index - 1] == "--artifact-principal-id" {
                "[artifact_principal]".to_string()
            } else {
                value.clone()
            }
        })
        .collect::<Vec<_>>();
    format_command(program, prefix, &sanitized_args)
}

fn assistant_now_utc() -> String {
    time::OffsetDateTime::now_utc()
        .format(&time::format_description::well_known::Rfc3339)
        .unwrap_or_else(|_| {
            let millis = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis();
            format!("{millis}")
        })
}

fn assistant_event_payload(
    assistant_turn_id: &str,
    session_id: &str,
    event: &str,
    sequence: u64,
    data: Value,
) -> AssistantStreamEventPayload {
    AssistantStreamEventPayload {
        contract_version: CONTRACT_VERSION.to_string(),
        assistant_turn_id: assistant_turn_id.to_string(),
        session_id: session_id.to_string(),
        event: event.to_string(),
        sequence,
        timestamp_utc: assistant_now_utc(),
        data,
    }
}

fn parse_assistant_json_line(
    line: &str,
    assistant_turn_id: &str,
    session_id: &str,
    sequence: u64,
) -> Result<AssistantStreamEventPayload, BridgeError> {
    let parsed = serde_json::from_str::<Value>(line).map_err(|error| {
        BridgeError::new(
            "PARSE_FAILED",
            format!("Failed to parse assistant JSONL event: {error}"),
            sanitize_preview(line),
            "assistant stream parse",
            false,
        )
    })?;
    let raw_event = parsed
        .get("event")
        .or_else(|| parsed.get("type"))
        .and_then(Value::as_str)
        .unwrap_or("status")
        .to_string();
    let event = normalize_assistant_event_name(&raw_event).to_string();
    let data = parsed.get("data").cloned().unwrap_or(parsed);
    Ok(assistant_event_payload(
        assistant_turn_id,
        session_id,
        &event,
        sequence,
        data,
    ))
}

fn normalize_assistant_event_name(value: &str) -> &str {
    match value {
        "status"
        | "token"
        | "delta"
        | "text_delta"
        | "router_decision"
        | "policy_decision"
        | "approval_pending"
        | "expert_start"
        | "expert_end"
        | "artifact_proposed"
        | "artifact_committed"
        | "artifact_patch_proposed"
        | "artifact_patch_applied"
        | "form_requested"
        | "form_submitted"
        | "tool_result"
        | "audit_artifact"
        | "final"
        | "warning"
        | "error"
        | "cancelled" => value,
        _ => "status",
    }
}

async fn stream_assistant_stdout(
    app: tauri::AppHandle,
    stdout: ChildStdout,
    assistant_turn_id: String,
    session_id: String,
) -> Result<u64, BridgeError> {
    let mut reader = TokioBufReader::new(stdout).lines();
    let mut sequence = 0u64;
    let mut final_seen = false;

    while let Some(line) = reader.next_line().await.map_err(|error| {
        BridgeError::new(
            "CLI_FAILED",
            format!("Failed to read assistant stdout: {error}"),
            "",
            "assistant stream read",
            true,
        )
    })? {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        sequence += 1;
        match parse_assistant_json_line(trimmed, &assistant_turn_id, &session_id, sequence) {
            Ok(payload) => {
                if payload.event == "final" {
                    final_seen = true;
                }
                emit_assistant_payload(&app, &payload)?;
            }
            Err(error) => {
                let warning = assistant_event_payload(
                    &assistant_turn_id,
                    &session_id,
                    "warning",
                    sequence,
                    json!({
                        "message": "Ignored malformed assistant stream line.",
                        "stderrPreview": sanitize_preview(&error.stderr_preview),
                    }),
                );
                emit_assistant_payload(&app, &warning)?;
            }
        }
    }

    if !final_seen {
        if !app
            .state::<AssistantProcessRegistry>()
            .turns
            .lock()
            .await
            .contains_key(&assistant_turn_id)
        {
            return Ok(sequence);
        }
        let error = BridgeError::new(
            "PARSE_FAILED",
            "Assistant stream ended before a final event.",
            "",
            "assistant stream final",
            false,
        );
        emit_assistant_error(&app, &assistant_turn_id, &session_id, sequence + 1, &error)?;
        sequence += 1;
    }

    Ok(sequence)
}

async fn terminate_process(process_id: u32) -> Result<(), BridgeError> {
    #[cfg(unix)]
    let mut command = {
        let mut command = Command::new("kill");
        command.arg("-TERM").arg(process_id.to_string());
        command
    };

    #[cfg(windows)]
    let mut command = {
        let mut command = Command::new("taskkill");
        command
            .arg("/PID")
            .arg(process_id.to_string())
            .arg("/T")
            .arg("/F");
        command
    };

    let status = command.status().await.map_err(|error| {
        BridgeError::new(
            "ASSISTANT_CANCEL_FAILED",
            format!("Failed to cancel assistant process: {error}"),
            "",
            format!("assistant cancel {process_id}"),
            true,
        )
    })?;

    if status.success() {
        Ok(())
    } else {
        Err(BridgeError::new(
            "ASSISTANT_CANCEL_FAILED",
            format!("Assistant cancel command exited with status {status}."),
            "",
            format!("assistant cancel {process_id}"),
            true,
        ))
    }
}

async fn read_assistant_stderr_preview(stderr: Option<ChildStderr>) -> String {
    let Some(stderr) = stderr else {
        return String::new();
    };
    let reader = TokioBufReader::new(stderr);
    let mut buffer = Vec::new();
    let mut limited = reader.take((4 * 1024) + 1);
    let _ = limited.read_to_end(&mut buffer).await;
    sanitize_preview(&String::from_utf8_lossy(&buffer))
}

fn emit_assistant_payload(
    app: &tauri::AppHandle,
    payload: &AssistantStreamEventPayload,
) -> Result<(), BridgeError> {
    app.emit(ASSISTANT_EVENT_NAME, payload).map_err(|error| {
        BridgeError::new(
            "CLI_FAILED",
            format!("Failed to emit assistant event: {error}"),
            "",
            ASSISTANT_EVENT_NAME,
            true,
        )
    })
}

fn emit_assistant_error(
    app: &tauri::AppHandle,
    assistant_turn_id: &str,
    session_id: &str,
    sequence: u64,
    error: &BridgeError,
) -> Result<(), BridgeError> {
    let payload = assistant_event_payload(
        assistant_turn_id,
        session_id,
        "error",
        sequence,
        json!({
            "code": error.code,
            "message": error.message,
            "stderrPreview": error.stderr_preview,
            "command": error.command,
            "retryable": error.retryable,
        }),
    );
    emit_assistant_payload(app, &payload)
}

fn parse_core_mode(value: Option<&str>) -> CoreMode {
    match value.map(|item| item.trim().to_lowercase()) {
        Some(mode) if mode == "external" => CoreMode::External,
        Some(mode) if mode == "bundled" => CoreMode::Bundled,
        _ => CoreMode::Auto,
    }
}

fn core_mode_name(mode: CoreMode) -> &'static str {
    match mode {
        CoreMode::Auto => "auto",
        CoreMode::External => "external",
        CoreMode::Bundled => "bundled",
    }
}

fn app_resource_dir(app: &tauri::AppHandle) -> Option<PathBuf> {
    app.path().resource_dir().ok()
}

fn resolve_cli_command(
    config: &BridgeConfig,
    resource_dir: Option<&Path>,
) -> Result<ResolvedCli, BridgeError> {
    let mode = parse_core_mode(config.mode.as_deref());

    let cli_path = config
        .cli_path
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string);

    let configured_bundled_path = config
        .bundled_python_path
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from);

    let bundled_path = configured_bundled_path
        .or_else(|| resource_dir.and_then(resolve_bundled_python_from_resource_dir))
        .or_else(default_bundled_python_path);

    if mode == CoreMode::External {
        return Ok(ResolvedCli {
            mode,
            program: cli_path.unwrap_or_else(|| "imperaos".to_string()),
            prefix_args: vec![],
        });
    }

    if mode == CoreMode::Bundled {
        let python = bundled_path.ok_or_else(|| {
            BridgeError::new(
                "CLI_NOT_FOUND",
                "Bundled python runtime was not found.",
                "",
                "resolve bundled runtime",
                false,
            )
        })?;

        return Ok(ResolvedCli {
            mode,
            program: python.to_string_lossy().to_string(),
            prefix_args: vec!["-m".to_string(), "imperaos".to_string()],
        });
    }

    if let Some(path) = cli_path {
        return Ok(ResolvedCli {
            mode: CoreMode::External,
            program: path,
            prefix_args: vec![],
        });
    }

    if let Some(path) = bundled_path {
        return Ok(ResolvedCli {
            mode: CoreMode::Bundled,
            program: path.to_string_lossy().to_string(),
            prefix_args: vec!["-m".to_string(), "imperaos".to_string()],
        });
    }

    Ok(ResolvedCli {
        mode: CoreMode::External,
        program: "imperaos".to_string(),
        prefix_args: vec![],
    })
}

fn default_bundled_python_path() -> Option<PathBuf> {
    let current = std::env::current_exe().ok()?;
    let exe_dir = current.parent()?;
    let mut resource_dirs = vec![exe_dir.join("resources"), exe_dir.to_path_buf()];

    if let Some(contents) = exe_dir.parent() {
        resource_dirs.push(contents.join("Resources"));
    }

    for resource_dir in resource_dirs {
        if let Some(path) = resolve_bundled_python_from_resource_dir(&resource_dir) {
            return Some(path);
        }
    }

    None
}

fn bundled_python_relative_path() -> &'static str {
    if cfg!(windows) {
        "imperaos-runtime/python/Scripts/python.exe"
    } else {
        "imperaos-runtime/python/bin/python"
    }
}

fn resolve_bundled_python_from_resource_dir(resource_dir: &Path) -> Option<PathBuf> {
    [
        resource_dir.join(bundled_python_relative_path()),
        resource_dir
            .join("resources")
            .join(bundled_python_relative_path()),
    ]
    .into_iter()
    .find(|path| path.exists())
}

fn path_separator() -> &'static str {
    if cfg!(windows) {
        ";"
    } else {
        ":"
    }
}

fn fallback_system_path() -> &'static str {
    if cfg!(windows) {
        r"C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem"
    } else {
        "/usr/bin:/bin:/usr/sbin:/sbin"
    }
}

fn push_optional_arg(args: &mut Vec<String>, flag: &str, value: Option<&str>) {
    if let Some(raw) = value {
        let normalized = raw.trim();
        if !normalized.is_empty() {
            args.push(flag.to_string());
            args.push(normalized.to_string());
        }
    }
}

fn normalize_required_text(value: &str, field: &str, command: &str) -> Result<String, BridgeError> {
    let normalized = value.trim();
    if normalized.is_empty() {
        return Err(BridgeError::new(
            "INVALID_INPUT",
            format!("{field} is required"),
            "",
            command,
            false,
        ));
    }
    Ok(normalized.to_string())
}

fn normalize_required_path(value: &str, field: &str, command: &str) -> Result<String, BridgeError> {
    let normalized = normalize_required_text(value, field, command)?;
    let path = PathBuf::from(&normalized);
    if !path.exists() {
        return Err(BridgeError::new(
            "INVALID_INPUT",
            format!("{field} does not exist"),
            "",
            command,
            false,
        ));
    }
    Ok(normalized)
}

fn generate_job_id() -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    format!("job-ui-{now}")
}

fn configure_cli_env(command: &mut Command, config: &BridgeConfig, resolved: &ResolvedCli) {
    command.env_clear();
    let base_path = std::env::var("PATH").unwrap_or_else(|_| fallback_system_path().to_string());

    match resolved.mode {
        CoreMode::Bundled => {
            let runtime_path = Path::new(&resolved.program)
                .parent()
                .map(|value| value.to_string_lossy().to_string())
                .unwrap_or_default();
            if runtime_path.is_empty() {
                command.env("PATH", base_path);
            } else {
                command.env(
                    "PATH",
                    format!("{runtime_path}{}{base_path}", path_separator()),
                );
            }
        }
        _ => {
            command.env("PATH", base_path);
        }
    }

    let env_keys: &[&str] = if cfg!(windows) {
        &[
            "SystemRoot",
            "WINDIR",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
            "PROGRAMDATA",
            "TEMP",
            "TMP",
            "ComSpec",
            "PATHEXT",
            "PROCESSOR_ARCHITECTURE",
            "NUMBER_OF_PROCESSORS",
        ]
    } else {
        &["HOME", "USER", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL"]
    };

    for key in env_keys {
        if let Ok(value) = std::env::var(key) {
            command.env(key, value);
        }
    }
    for key in [
        "IMPERAOS_PROFILE",
        "IMPERAOS_WORKSPACE_ID",
        "IMPERAOS_IDENTITY_ASSERTION_PATH",
        "IMPERAOS_BREAK_GLASS_ASSERTION_PATH",
        "IMPERAOS_ACTOR_ID",
        "IMPERAOS_ARTIFACT_ROLES",
        "IMPERAOS_GOVERNANCE_APPROVAL_STORE_PATH",
        "IMPERAOS_ARTIFACT_WORKSPACE_ENABLED",
        "IMPERAOS_ARTIFACT_DOCUMENT_EDITOR_ENABLED",
        "IMPERAOS_ARTIFACT_FORM_EDITOR_ENABLED",
        "IMPERAOS_ARTIFACT_CODE_EDITOR_ENABLED",
        "IMPERAOS_ARTIFACT_FLOW_EDITOR_ENABLED",
        "IMPERAOS_ARTIFACT_SPREADSHEET_EDITOR_ENABLED",
        "IMPERAOS_ARTIFACT_CANVAS_EDITOR_ENABLED",
        "IMPERAOS_ARTIFACT_SLIDES_EDITOR_ENABLED",
        "IMPERAOS_ARTIFACT_EXPORT_ENABLED",
        "IMPERAOS_ASSISTANT_UI_RUNTIME_ENABLED",
        "IMPERAOS_ASSISTANT_AI_SDK_RUNTIME_ENABLED",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "COMPANY_LLM_API_KEY",
    ] {
        if let Ok(value) = std::env::var(key) {
            command.env(key, value);
        }
    }

    command.env("PYTHONNOUSERSITE", "1");
    command.env("PYTHONDONTWRITEBYTECODE", "1");
    if let Some(config_dir) = bundled_config_dir(resolved) {
        command.env("IMPERAOS_CONFIG_ROOT", &config_dir);
        let provider_registry = config_dir.join("providers.toml");
        let provider_registry_example = config_dir.join("providers.example.toml");
        if provider_registry.exists() {
            command.env("IMPERAOS_PROVIDER_REGISTRY_PATH", provider_registry);
        } else if provider_registry_example.exists() {
            command.env("IMPERAOS_PROVIDER_REGISTRY_PATH", provider_registry_example);
        }
    }

    for (key, value) in &config.env {
        if is_allowed_cli_env_key(key) && !value.trim().is_empty() {
            command.env(key, value);
        }
    }
}

fn is_allowed_cli_env_key(key: &str) -> bool {
    key.starts_with("IMPERAOS_")
        || matches!(
            key,
            "OPENAI_API_KEY" | "DEEPSEEK_API_KEY" | "ANTHROPIC_API_KEY" | "COMPANY_LLM_API_KEY"
        )
}

fn bundled_runtime_root(resolved: &ResolvedCli) -> Option<PathBuf> {
    if resolved.mode != CoreMode::Bundled {
        return None;
    }
    Path::new(&resolved.program)
        .parent()
        .and_then(Path::parent)
        .and_then(Path::parent)
        .map(Path::to_path_buf)
}

fn bundled_config_dir(resolved: &ResolvedCli) -> Option<PathBuf> {
    let config_dir = bundled_runtime_root(resolved)?.join("config");
    if config_dir.exists() {
        Some(config_dir)
    } else {
        None
    }
}

fn macos_runtime_workdir(base: &Path) -> PathBuf {
    base.join("com.imperaos.operatorpanel").join("runtime")
}

fn windows_runtime_workdir(base: &Path) -> PathBuf {
    base.join("ImperaOS Operator Panel").join("runtime")
}

fn unix_runtime_workdir(base: &Path) -> PathBuf {
    base.join("imperaos-operator-panel").join("runtime")
}

fn default_cli_workdir() -> Option<PathBuf> {
    if cfg!(target_os = "macos") {
        let home = std::env::var_os("HOME")?;
        let base = PathBuf::from(home)
            .join("Library")
            .join("Application Support");
        return Some(macos_runtime_workdir(&base));
    }
    if cfg!(windows) {
        if let Some(base) = std::env::var_os("LOCALAPPDATA").or_else(|| std::env::var_os("APPDATA"))
        {
            return Some(windows_runtime_workdir(&PathBuf::from(base)));
        }
    }
    let base = std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .or_else(|| {
            std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".local/share"))
        })?;
    Some(unix_runtime_workdir(&base))
}

fn configure_cli_workdir(command: &mut Command) {
    if let Some(workdir) = default_cli_workdir() {
        if fs::create_dir_all(&workdir).is_ok() {
            command.current_dir(workdir);
        }
    }
}

async fn run_cli_text_with_resource_dir(
    config: &BridgeConfig,
    args: Vec<String>,
    resource_dir: Option<&Path>,
) -> Result<String, BridgeError> {
    let output = run_cli_raw_with_resource_dir(config, args, resource_dir).await?;
    Ok(output.stdout)
}

async fn run_cli_json_with_resource_dir(
    config: &BridgeConfig,
    args: Vec<&str>,
    resource_dir: Option<&Path>,
) -> Result<Value, BridgeError> {
    let owned = args
        .into_iter()
        .map(ToString::to_string)
        .collect::<Vec<_>>();
    run_cli_json_owned_with_resource_dir(config, owned, resource_dir).await
}

async fn run_cli_json_owned(
    config: &BridgeConfig,
    args: Vec<String>,
) -> Result<Value, BridgeError> {
    run_cli_json_owned_with_resource_dir(config, args, None).await
}

async fn run_cli_json_owned_with_resource_dir(
    config: &BridgeConfig,
    args: Vec<String>,
    resource_dir: Option<&Path>,
) -> Result<Value, BridgeError> {
    let output = run_cli_raw_with_resource_dir(config, args, resource_dir).await?;
    parse_json_output(&output)
}

async fn run_cli_raw_with_resource_dir(
    config: &BridgeConfig,
    args: Vec<String>,
    resource_dir: Option<&Path>,
) -> Result<RawCliOutput, BridgeError> {
    let config = config.clone();
    let resolved = resolve_cli_command(&config, resource_dir)?;
    let mut command = Command::new(&resolved.program);
    command.args(&resolved.prefix_args);
    command.args(&args);
    command.stdout(Stdio::piped());
    command.stderr(Stdio::piped());
    configure_cli_env(&mut command, &config, &resolved);
    configure_cli_workdir(&mut command);

    let cmdline = format_command(&resolved.program, &resolved.prefix_args, &args);
    let timeout_ms = config.timeout_ms.unwrap_or(DEFAULT_TIMEOUT_MS);
    let output = tokio::time::timeout(Duration::from_millis(timeout_ms), command.output())
        .await
        .map_err(|_| {
            BridgeError::new(
                "TIMEOUT",
                format!("Command timed out after {timeout_ms}ms."),
                "",
                cmdline.clone(),
                true,
            )
        })?
        .map_err(|error| {
            let code = if error.kind() == std::io::ErrorKind::NotFound {
                "CLI_NOT_FOUND"
            } else {
                "CLI_FAILED"
            };
            BridgeError::new(
                code,
                error.to_string(),
                "",
                cmdline.clone(),
                code != "CLI_NOT_FOUND",
            )
        })?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();

    if !output.status.success() {
        return Err(BridgeError::new(
            "CLI_FAILED",
            format!("Command exited with status {}", output.status),
            sanitize_preview(&stderr),
            cmdline,
            false,
        ));
    }

    Ok(RawCliOutput {
        stdout,
        stderr,
        command: cmdline,
    })
}

async fn spawn_cli_background(
    config: &BridgeConfig,
    args: Vec<String>,
) -> Result<Option<u32>, BridgeError> {
    let config = config.clone();
    let resolved = resolve_cli_command(&config, None)?;
    let mut command = Command::new(&resolved.program);
    command.args(&resolved.prefix_args);
    command.args(&args);
    command.stdout(Stdio::null());
    command.stderr(Stdio::null());
    configure_cli_env(&mut command, &config, &resolved);
    configure_cli_workdir(&mut command);

    let child = command.spawn().map_err(|error| {
        let code = if error.kind() == std::io::ErrorKind::NotFound {
            "CLI_NOT_FOUND"
        } else {
            "CLI_FAILED"
        };
        BridgeError::new(
            code,
            error.to_string(),
            "",
            format_command(&resolved.program, &resolved.prefix_args, &args),
            code != "CLI_NOT_FOUND",
        )
    })?;
    Ok(child.id())
}

fn parse_json_output(output: &RawCliOutput) -> Result<Value, BridgeError> {
    let body = output.stdout.trim();
    serde_json::from_str(body).map_err(|error| {
        let stdout_preview = sanitize_preview(body);
        let stderr_preview = if output.stderr.trim().is_empty() {
            stdout_preview
        } else {
            sanitize_preview(&output.stderr)
        };
        BridgeError::new(
            "PARSE_FAILED",
            format!("Failed to parse CLI JSON output: {error}"),
            stderr_preview,
            output.command.clone(),
            false,
        )
    })
}

fn format_command(program: &str, prefix: &[String], args: &[String]) -> String {
    let mut parts = vec![program.to_string()];
    parts.extend(prefix.iter().cloned());
    parts.extend(args.iter().cloned());
    parts.join(" ")
}

fn sanitize_preview(text: &str) -> String {
    let preview = text
        .lines()
        .take(8)
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .collect::<Vec<_>>()
        .join("\n");
    redact_sensitive_preview(&preview)
        .chars()
        .take(4 * 1024)
        .collect()
}

fn redact_sensitive_preview(text: &str) -> String {
    text.split_whitespace()
        .map(|part| {
            if part.starts_with("sk-") {
                "[redacted-secret]".to_string()
            } else if part.starts_with("ghp_") {
                "[redacted-token]".to_string()
            } else {
                part.to_string()
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

fn normalize_actor(operator_id: &str) -> Result<String, BridgeError> {
    let normalized = operator_id.trim();
    let valid = normalized.len() >= 3
        && normalized.len() <= 64
        && normalized
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '.'));
    if !valid {
        return Err(BridgeError::new(
            "INVALID_INPUT",
            "operator_id must be 3-64 chars using [a-zA-Z0-9._-]",
            "",
            "normalize actor",
            false,
        ));
    }
    Ok(format!("ui:{normalized}"))
}

fn normalize_job_id(job_id: &str) -> Result<String, BridgeError> {
    let normalized = job_id.trim();
    let valid = !normalized.is_empty()
        && normalized.len() <= 128
        && normalized
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_'));
    if !valid {
        return Err(BridgeError::new(
            "INVALID_INPUT",
            "Invalid job_id format.",
            "",
            "job_id validation",
            false,
        ));
    }
    Ok(normalized.to_string())
}

fn normalize_control_plane_id(value: &str, field: &str) -> Result<String, BridgeError> {
    let normalized = value.trim();
    let valid = !normalized.is_empty()
        && normalized.len() <= 160
        && normalized
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '.'));
    if !valid {
        return Err(BridgeError::new(
            "INVALID_INPUT",
            format!("Invalid {field} format."),
            "",
            "control-plane id validation",
            false,
        ));
    }
    Ok(normalized.to_string())
}

fn normalize_computer_use_runtime(value: Option<&str>) -> Result<Option<String>, BridgeError> {
    let Some(raw) = value else {
        return Ok(None);
    };
    let normalized = raw.trim().to_ascii_lowercase().replace('_', "-");
    if normalized.is_empty() {
        return Ok(None);
    }
    if matches!(
        normalized.as_str(),
        "legacy-pilot" | "vision-first" | "auto"
    ) {
        return Ok(Some(normalized));
    }
    Err(BridgeError::new(
        "INVALID_INPUT",
        "runtime must be legacy-pilot, vision-first, or auto",
        "",
        "computer-use run",
        false,
    ))
}

fn normalize_optional_cli_token(
    value: Option<&str>,
    field: &str,
    command: &str,
) -> Result<Option<String>, BridgeError> {
    let Some(raw) = value else {
        return Ok(None);
    };
    let normalized = raw.trim();
    if normalized.is_empty() {
        return Ok(None);
    }
    let valid = normalized.len() <= 256
        && normalized.chars().all(|ch| {
            ch.is_ascii_alphanumeric() || matches!(ch, '.' | '_' | ':' | '/' | '@' | '+' | '-')
        });
    if valid {
        return Ok(Some(normalized.to_string()));
    }
    Err(BridgeError::new(
        "INVALID_INPUT",
        format!("{field} contains unsupported characters"),
        "",
        command,
        false,
    ))
}

fn resolve_root_dir(root_dir: &str) -> Result<PathBuf, BridgeError> {
    let normalized = root_dir.trim();
    if normalized.is_empty() {
        return Err(BridgeError::new(
            "INVALID_INPUT",
            "root_dir is required",
            "",
            "root_dir",
            false,
        ));
    }

    let root = fs::canonicalize(normalized).map_err(|error| {
        BridgeError::new(
            "INVALID_INPUT",
            format!("Unable to resolve root_dir: {error}"),
            "",
            "root_dir",
            false,
        )
    })?;
    reject_symlink_segments(&root)?;
    Ok(root)
}

fn reject_symlink_segments(path: &Path) -> Result<(), BridgeError> {
    let mut current = PathBuf::new();
    for component in path.components() {
        match component {
            Component::Prefix(prefix) => current.push(prefix.as_os_str()),
            Component::RootDir => current.push(Path::new("/")),
            Component::CurDir => continue,
            Component::ParentDir => {
                return Err(BridgeError::new(
                    "PATH_VIOLATION",
                    "Parent directory segments are not allowed.",
                    "",
                    path.display().to_string(),
                    false,
                ));
            }
            Component::Normal(value) => current.push(value),
        }

        if let Ok(meta) = fs::symlink_metadata(&current) {
            if meta.file_type().is_symlink() {
                return Err(BridgeError::new(
                    "PATH_VIOLATION",
                    format!("Symlink segment is not allowed: {}", current.display()),
                    "",
                    current.display().to_string(),
                    false,
                ));
            }
        }
    }
    Ok(())
}

fn safe_artifact_path(
    root_dir: &str,
    job_id: &str,
    artifact_name: &str,
) -> Result<PathBuf, BridgeError> {
    let root = resolve_root_dir(root_dir)?;
    let normalized_job_id = normalize_job_id(job_id)?;

    if !ARTIFACT_ALLOWLIST.contains(&artifact_name) {
        return Err(BridgeError::new(
            "INVALID_INPUT",
            "Artifact is not allowlisted.",
            "",
            artifact_name,
            false,
        ));
    }

    let job_dir = root.join(normalized_job_id);
    reject_symlink_segments(&job_dir)?;

    let logical_path = job_dir.join(artifact_name);
    reject_symlink_segments(&logical_path)?;

    let canonical_before = fs::canonicalize(&logical_path).map_err(|error| {
        BridgeError::new(
            "INVALID_INPUT",
            format!("Artifact not found: {error}"),
            "",
            logical_path.display().to_string(),
            false,
        )
    })?;

    if !canonical_before.starts_with(&root) {
        return Err(BridgeError::new(
            "PATH_VIOLATION",
            "Artifact path escapes root_dir.",
            "",
            canonical_before.display().to_string(),
            false,
        ));
    }

    reject_symlink_segments(&canonical_before)?;

    let canonical_after = fs::canonicalize(&logical_path).map_err(|error| {
        BridgeError::new(
            "PATH_VIOLATION",
            format!("Artifact changed during validation: {error}"),
            "",
            logical_path.display().to_string(),
            false,
        )
    })?;

    if canonical_before != canonical_after {
        return Err(BridgeError::new(
            "PATH_VIOLATION",
            "Artifact changed during open (TOCTOU guard).",
            "",
            logical_path.display().to_string(),
            false,
        ));
    }

    Ok(canonical_before)
}

fn read_artifact_impl(
    root_dir: &str,
    job_id: &str,
    artifact_name: &str,
    max_bytes: Option<usize>,
) -> Result<ReadArtifactPayload, BridgeError> {
    let path = safe_artifact_path(root_dir, job_id, artifact_name)?;
    let max = max_bytes.unwrap_or(DEFAULT_MAX_BYTES);
    let (bytes, truncated) = read_file_bounded(&path, max)?;
    let parsed = serde_json::from_slice::<Value>(&bytes).map_err(|error| {
        BridgeError::new(
            "PARSE_FAILED",
            format!("Failed to parse artifact JSON: {error}"),
            sanitize_preview(&String::from_utf8_lossy(&bytes)),
            path.display().to_string(),
            false,
        )
    })?;

    Ok(ReadArtifactPayload {
        contract_version: CONTRACT_VERSION.to_string(),
        artifact_name: artifact_name.to_string(),
        payload: parsed,
        truncated,
        bytes_read: bytes.len(),
    })
}

fn read_file_bounded(path: &Path, max_bytes: usize) -> Result<(Vec<u8>, bool), BridgeError> {
    let mut file = File::open(path).map_err(|error| {
        BridgeError::new(
            "INVALID_INPUT",
            format!("Failed to open file: {error}"),
            "",
            path.display().to_string(),
            false,
        )
    })?;

    let mut take = file.by_ref().take((max_bytes as u64) + 1);
    let mut buffer = Vec::new();
    take.read_to_end(&mut buffer).map_err(|error| {
        BridgeError::new(
            "CLI_FAILED",
            format!("Failed to read file: {error}"),
            "",
            path.display().to_string(),
            true,
        )
    })?;

    let truncated = buffer.len() > max_bytes;
    if truncated {
        buffer.truncate(max_bytes);
    }

    Ok((buffer, truncated))
}

fn tail_events_impl(
    root_dir: &str,
    job_id: &str,
    cursor: u64,
    max_bytes: usize,
    max_lines: usize,
) -> Result<TailOutcome, BridgeError> {
    let path = safe_artifact_path(root_dir, job_id, "events.jsonl")?;
    let mut file = File::open(&path).map_err(|error| {
        BridgeError::new(
            "INVALID_INPUT",
            format!("Failed to open events file: {error}"),
            "",
            path.display().to_string(),
            false,
        )
    })?;

    let metadata_len = file
        .metadata()
        .map_err(|error| {
            BridgeError::new(
                "CLI_FAILED",
                format!("Failed to inspect events file: {error}"),
                "",
                path.display().to_string(),
                true,
            )
        })?
        .len();

    let mut effective_cursor = cursor;
    let mut reset = false;
    if cursor > metadata_len {
        effective_cursor = 0;
        reset = true;
    }

    file.seek(SeekFrom::Start(effective_cursor))
        .map_err(|error| {
            BridgeError::new(
                "CLI_FAILED",
                format!("Failed to seek events file: {error}"),
                "",
                path.display().to_string(),
                true,
            )
        })?;

    let mut reader = StdBufReader::new(file);
    let mut events = Vec::new();
    let mut bytes_used = 0usize;
    let mut lines_used = 0usize;
    let mut next_cursor = effective_cursor;
    let mut truncated = false;
    let mut bad_line_count = 0u64;

    loop {
        let line_start = reader.stream_position().map_err(|error| {
            BridgeError::new(
                "CLI_FAILED",
                format!("Failed to read stream position: {error}"),
                "",
                path.display().to_string(),
                true,
            )
        })?;

        let mut buffer = Vec::new();
        let bytes = reader.read_until(b'\n', &mut buffer).map_err(|error| {
            BridgeError::new(
                "CLI_FAILED",
                format!("Failed to read events file: {error}"),
                "",
                path.display().to_string(),
                true,
            )
        })?;

        if bytes == 0 {
            break;
        }

        if !buffer.ends_with(b"\n") {
            reader.seek(SeekFrom::Start(line_start)).map_err(|error| {
                BridgeError::new(
                    "CLI_FAILED",
                    format!("Failed to rewind partial line: {error}"),
                    "",
                    path.display().to_string(),
                    true,
                )
            })?;
            break;
        }

        if lines_used >= max_lines || (bytes_used + bytes) > max_bytes {
            truncated = true;
            reader.seek(SeekFrom::Start(line_start)).map_err(|error| {
                BridgeError::new(
                    "CLI_FAILED",
                    format!("Failed to rewind bounded read: {error}"),
                    "",
                    path.display().to_string(),
                    true,
                )
            })?;
            break;
        }

        lines_used += 1;
        bytes_used += bytes;
        next_cursor = line_start + (bytes as u64);

        match serde_json::from_slice::<Value>(&buffer) {
            Ok(value) => events.push(value),
            Err(_) => {
                bad_line_count += 1;
                truncated = true;
            }
        }
    }

    Ok(TailOutcome {
        events,
        next_cursor,
        reset,
        truncated,
        bad_line_count,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use sha2::{Digest, Sha256};
    use std::collections::HashMap;
    use std::io::Write;
    #[cfg(unix)]
    use std::os::unix::fs::PermissionsExt;
    use std::sync::{Arc, Mutex as StdMutex};

    #[test]
    fn normalize_actor_requires_expected_format() {
        assert!(normalize_actor("ops-1").is_ok());
        assert!(normalize_actor(" ").is_err());
        assert!(normalize_actor("a*").is_err());
    }

    #[test]
    fn normalize_computer_use_runtime_allows_only_supported_values() {
        assert_eq!(
            normalize_computer_use_runtime(Some("vision_first")).expect("runtime"),
            Some("vision-first".to_string())
        );
        assert_eq!(
            normalize_computer_use_runtime(Some("legacy-pilot")).expect("runtime"),
            Some("legacy-pilot".to_string())
        );
        assert_eq!(
            normalize_computer_use_runtime(Some("auto")).expect("runtime"),
            Some("auto".to_string())
        );
        assert_eq!(
            normalize_computer_use_runtime(Some(" ")).expect("empty"),
            None
        );
        assert!(normalize_computer_use_runtime(Some("unsafe-live")).is_err());
    }

    #[test]
    fn normalize_assistant_prompt_rejects_empty_and_too_large() {
        assert!(normalize_assistant_prompt("hello", 10, "user_message").is_ok());
        assert!(normalize_assistant_prompt(" ", 10, "user_message").is_err());
        assert!(normalize_assistant_prompt("12345678901", 10, "user_message").is_err());
    }

    #[test]
    fn normalize_optional_cli_token_accepts_model_ids_and_rejects_unsafe_text() {
        assert_eq!(
            normalize_optional_cli_token(Some(" qwen3.5:4b "), "model", "assistant start")
                .expect("model"),
            Some("qwen3.5:4b".to_string())
        );
        assert_eq!(
            normalize_optional_cli_token(
                Some("Qwen/Qwen2.5-Instruct@q4"),
                "hf_model_id",
                "assistant start"
            )
            .expect("hf model"),
            Some("Qwen/Qwen2.5-Instruct@q4".to_string())
        );
        assert_eq!(
            normalize_optional_cli_token(Some(" "), "model", "assistant start").expect("blank"),
            None
        );
        let invalid =
            normalize_optional_cli_token(Some("qwen3.5:4b --unsafe"), "model", "assistant start")
                .expect_err("invalid");
        assert_eq!(invalid.code, "INVALID_INPUT");
        assert!(!invalid.retryable);
    }

    #[test]
    fn operator_panel_contract_version_is_3_0() {
        assert_eq!(CONTRACT_VERSION, "3.0");
    }

    #[test]
    fn project_folder_ticket_is_opaque_and_consumed_when_bound_to_a_root_ref() {
        let selected = tempfile::tempdir().expect("temporary folder");
        let selected_path = selected
            .path()
            .canonicalize()
            .expect("canonical selected folder");
        let state = ProductFolderTicketState::default();

        let (ticket, display_name) =
            tauri::async_runtime::block_on(state.issue(selected_path.clone()))
                .expect("folder ticket");
        assert!(ticket.starts_with("folder-"));
        assert!(!ticket.contains(&selected_path.display().to_string()));
        assert!(!display_name.is_empty());

        tauri::async_runtime::block_on(state.bind_in_memory(&ticket, "root-release"))
            .expect("bind ticket to durable root ref");
        assert!(!tauri::async_runtime::block_on(state.tickets.lock()).contains_key(&ticket));
        assert_eq!(
            tauri::async_runtime::block_on(state.roots.lock()).get("root-release"),
            Some(&selected_path)
        );
        assert_eq!(
            tauri::async_runtime::block_on(state.resolve_registered_root("root-release"))
                .expect("registered root resolves natively"),
            selected_path
        );
        assert!(
            tauri::async_runtime::block_on(state.resolve_registered_root("root-missing")).is_err()
        );
    }

    #[test]
    fn parse_assistant_json_line_valid_token() {
        let payload = parse_assistant_json_line(
            r#"{"event":"token","data":{"text":"Hello"}}"#,
            "turn-1",
            "session-1",
            7,
        )
        .expect("payload");
        let json = serde_json::to_value(payload).expect("serialize");

        assert_eq!(json["contractVersion"], CONTRACT_VERSION);
        assert_eq!(json["assistantTurnId"], "turn-1");
        assert_eq!(json["event"], "token");
        assert_eq!(json["sequence"], 7);
        assert_eq!(json["data"]["text"], "Hello");
    }

    #[test]
    fn parse_assistant_json_line_valid_final() {
        let payload = parse_assistant_json_line(
            r#"{"event":"final","data":{"final_text":"Done","trace_id":"trace_1"}}"#,
            "turn-1",
            "session-1",
            8,
        )
        .expect("payload");

        assert_eq!(payload.event, "final");
        assert_eq!(payload.data["final_text"], "Done");
    }

    #[test]
    fn parse_assistant_json_line_rejects_invalid_json_with_warning_path() {
        let error = parse_assistant_json_line("not-json", "turn-1", "session-1", 1)
            .expect_err("invalid json");

        assert_eq!(error.code, "PARSE_FAILED");
        assert!(error.stderr_preview.contains("not-json"));
    }

    #[test]
    fn assistant_command_args_include_stdio_json_stream_once() {
        let config = BridgeConfig {
            mode: Some("external".to_string()),
            cli_path: Some("imperaos".to_string()),
            bundled_python_path: None,
            profile: Some("balanced".to_string()),
            root_dir: None,
            env: HashMap::new(),
            timeout_ms: None,
        };
        let args = build_assistant_chat_args(
            &config,
            "Benim için bir standart sapma fonksiyonu yazar mısın?",
            "session-1",
            Some("ollama"),
            Some("local-ollama"),
            Some("transformers"),
            Some("local-transformers"),
            Some("qwen3.5:4b"),
            Some("Qwen/Qwen2.5"),
        );

        assert!(args.windows(2).any(|pair| pair[0] == "--once"
            && pair[1] == "Benim için bir standart sapma fonksiyonu yazar mısın?"));
        assert!(args.contains(&"--stdio-json".to_string()));
        assert!(args.contains(&"--stream".to_string()));
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--session-id" && pair[1] == "session-1"));
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--provider" && pair[1] == "ollama"));
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--provider-id" && pair[1] == "local-ollama"));
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--fallback-provider" && pair[1] == "transformers"));
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--fallback-provider-id" && pair[1] == "local-transformers"));
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--model" && pair[1] == "qwen3.5:4b"));
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--hf-model-id" && pair[1] == "Qwen/Qwen2.5"));
    }

    #[test]
    fn assistant_command_preview_redacts_user_message() {
        let preview = format_assistant_command_preview(
            "imperaos",
            &[],
            &[
                "chat".to_string(),
                "--once".to_string(),
                "secret prompt body".to_string(),
                "--stdio-json".to_string(),
            ],
        );

        assert!(preview.contains("[user_message]"));
        assert!(!preview.contains("secret prompt body"));
    }

    #[test]
    fn governed_assistant_args_use_compiled_prompt_file_and_trusted_identity() {
        let config = BridgeConfig {
            mode: Some("external".to_string()),
            cli_path: Some("imperaos".to_string()),
            bundled_python_path: None,
            profile: Some("balanced".to_string()),
            root_dir: None,
            env: HashMap::new(),
            timeout_ms: None,
        };
        let identity = TrustedArtifactIdentity::new(
            "workspace-1",
            "user-1",
            "user",
            vec!["artifact_admin".to_string()],
        )
        .expect("identity");
        let trusted_config = trusted_artifact_command_config(&config);
        let args = build_assistant_turn_args(
            &trusted_config,
            Path::new("C:/tmp/compiled-prompt.md"),
            "turn-1",
            "session-1",
            Some("ollama"),
            Some("local-ollama"),
            None,
            None,
            None,
            None,
            "high",
            "fast",
            "always_ask",
            Path::new("C:/tmp/artifacts"),
            &identity,
        );

        assert_eq!(&args[..2], &["assistant", "turn"]);
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--prompt-file" && pair[1] == "C:/tmp/compiled-prompt.md"));
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--artifact-workspace-id" && pair[1] == "workspace-1"));
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--artifact-principal-id" && pair[1] == "user-1"));
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--artifact-role" && pair[1] == "artifact_admin"));
        assert!(args
            .windows(2)
            .any(|pair| { pair[0] == "--artifact-prompt-data-class" && pair[1] == "regulated" }));
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--profile" && pair[1] == "enterprise"));
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--reasoning-effort" && pair[1] == "high"));
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--speed-profile" && pair[1] == "fast"));
        assert!(args
            .windows(2)
            .any(|pair| pair[0] == "--approval-profile" && pair[1] == "always_ask"));

        let preview = format_assistant_command_preview("imperaos", &[], &args);
        assert!(preview.contains("[compiled_prompt_file]"));
        assert!(preview.contains("[artifact_root]"));
        assert!(preview.contains("[artifact_principal]"));
        assert!(!preview.contains("C:/tmp"));
        assert!(!preview.contains("user-1"));
    }

    #[test]
    fn governed_artifact_config_drops_renderer_authority_overrides() {
        let config = BridgeConfig {
            mode: Some("external".to_string()),
            cli_path: Some("renderer-controlled.exe".to_string()),
            bundled_python_path: Some("renderer-python.exe".to_string()),
            profile: Some("balanced".to_string()),
            root_dir: Some("renderer-root".to_string()),
            env: HashMap::from([
                (
                    "IMPERAOS_GOVERNANCE_APPROVAL_STORE_PATH".to_string(),
                    "renderer-controlled.sqlite3".to_string(),
                ),
                (
                    "IMPERAOS_CONFIG_ROOT".to_string(),
                    "renderer-controlled-config".to_string(),
                ),
                ("OPENAI_API_KEY".to_string(), "provider-key".to_string()),
            ]),
            timeout_ms: None,
        };

        let trusted = trusted_artifact_command_config(&config);

        assert_eq!(trusted.profile(), trusted_artifact_profile());
        assert_eq!(trusted.mode.as_deref(), Some("auto"));
        assert!(trusted.cli_path.is_none());
        assert!(trusted.bundled_python_path.is_none());
        assert!(trusted.root_dir.is_none());
        assert!(trusted.env.is_empty());
    }

    #[test]
    fn assistant_prompt_guard_removes_prompt_on_every_drop_path() {
        let dir = tempfile::tempdir().expect("tempdir");
        let prompt = dir.path().join("prompt.md");
        fs::write(&prompt, "classified prompt").expect("write prompt");

        {
            let _guard = AssistantPromptFileGuard(prompt.clone());
            assert!(prompt.exists());
        }

        assert!(!prompt.exists());
    }

    #[test]
    fn assistant_prompt_partial_write_failure_removes_created_file() {
        let dir = tempfile::tempdir().expect("tempdir");
        let prompt = dir.path().join("partial.md");
        let result = create_assistant_prompt_file_with_writer(&prompt, |file| {
            std::io::Write::write_all(file, b"classified prefix")?;
            Err(std::io::Error::other("simulated disk failure"))
        });

        assert!(result.is_err());
        assert!(!prompt.exists());
    }

    #[test]
    fn assistant_prompt_startup_cleanup_removes_only_stale_prompt_files() {
        let dir = tempfile::tempdir().expect("tempdir");
        let stale = dir.path().join("stale.md");
        let unrelated = dir.path().join("keep.json");
        fs::write(&stale, "stale prompt").expect("write stale");
        fs::write(&unrelated, "keep").expect("write unrelated");

        cleanup_stale_assistant_prompt_files(dir.path(), Duration::ZERO);

        assert!(!stale.exists());
        assert!(unrelated.exists());
    }

    #[test]
    fn assistant_stdio_json_smoke_parses_token_and_final_events() {
        let token = parse_assistant_json_line(
            r#"{"event":"token","data":{"text":"Hi"}}"#,
            "turn-smoke",
            "session-smoke",
            1,
        )
        .expect("token");
        let final_event = parse_assistant_json_line(
            r#"{"event":"final","data":{"final_text":"Done"}}"#,
            "turn-smoke",
            "session-smoke",
            2,
        )
        .expect("final");

        assert_eq!(token.event, "token");
        assert_eq!(token.data["text"], "Hi");
        assert_eq!(final_event.event, "final");
        assert_eq!(final_event.data["final_text"], "Done");
    }

    #[test]
    fn assistant_runtime_v3_golden_events_parse_through_the_tauri_bridge() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../../../contracts/operator_panel/fixtures/assistant_runtime_v3_golden.json"
        ))
        .expect("assistant runtime golden fixture");
        let scenarios = fixture["scenarios"].as_array().expect("scenarios");

        for scenario in scenarios {
            let events = scenario["events"].as_array().expect("events");
            for (index, event) in events.iter().enumerate() {
                let line = serde_json::to_string(&json!({
                    "event": event["event"],
                    "data": event["data"],
                }))
                .expect("json line");
                let parsed = parse_assistant_json_line(
                    &line,
                    event["assistantTurnId"].as_str().expect("turn id"),
                    event["sessionId"].as_str().expect("session id"),
                    (index + 1) as u64,
                )
                .expect("parse golden event");

                assert_eq!(parsed.event, event["event"].as_str().expect("event name"));
                assert_eq!(parsed.data, event["data"]);
            }
        }
    }

    #[test]
    fn assistant_stderr_preview_is_sanitized() {
        let preview = sanitize_preview("failed sk-abc123456789 ghp_abcdefghijklmnop");

        assert!(!preview.contains("sk-abc"));
        assert!(!preview.contains("ghp_"));
        assert!(preview.contains("[redacted-secret]"));
        assert!(preview.contains("[redacted-token]"));
    }

    #[test]
    fn tail_events_buffers_partial_line() {
        let dir = tempfile::tempdir().expect("tempdir");
        let root = dir.path().join("jobs");
        let job = root.join("job-1");
        fs::create_dir_all(&job).expect("mkdir");

        let mut file = File::create(job.join("events.jsonl")).expect("events");
        file.write_all(b"{\"event\":\"ok\"}\n{\"event\":\"partial\"")
            .expect("write");

        let result =
            tail_events_impl(root.to_string_lossy().as_ref(), "job-1", 0, 4096, 50).expect("tail");

        assert_eq!(result.events.len(), 1);
        assert_eq!(result.bad_line_count, 0);
        assert!(!result.truncated);
    }

    #[test]
    fn tail_events_resets_cursor_when_file_shrinks() {
        let dir = tempfile::tempdir().expect("tempdir");
        let root = dir.path().join("jobs");
        let job = root.join("job-2");
        fs::create_dir_all(&job).expect("mkdir");

        let mut file = File::create(job.join("events.jsonl")).expect("events");
        file.write_all(b"{\"event\":\"one\"}\n").expect("write");

        let result = tail_events_impl(root.to_string_lossy().as_ref(), "job-2", 999, 4096, 50)
            .expect("tail");

        assert!(result.reset);
        assert_eq!(result.events.len(), 1);
    }

    #[test]
    fn safe_artifact_path_rejects_traversal_job_id() {
        let dir = tempfile::tempdir().expect("tempdir");
        let root = dir.path().join("jobs");
        fs::create_dir_all(&root).expect("mkdir");

        let result = safe_artifact_path(root.to_string_lossy().as_ref(), "../evil", "status.json");
        assert!(result.is_err());
    }

    #[test]
    fn read_artifact_payload_serializes_contract_version() {
        let dir = tempfile::tempdir().expect("tempdir");
        let root = dir.path().join("jobs");
        let job = root.join("job-3");
        fs::create_dir_all(&job).expect("mkdir");
        fs::write(job.join("status.json"), "{\"job\":{\"job_id\":\"job-3\"}}").expect("write");

        let payload = read_artifact_impl(
            root.to_string_lossy().as_ref(),
            "job-3",
            "status.json",
            None,
        )
        .expect("artifact");
        let json = serde_json::to_value(payload).expect("serialize");

        assert_eq!(json["contractVersion"], CONTRACT_VERSION);
        assert_eq!(json["artifactName"], "status.json");
    }

    #[test]
    fn spawned_run_payload_serializes_contract_version() {
        let payload = SpawnedRunPayload {
            contract_version: CONTRACT_VERSION.to_string(),
            job_id: "job-4".to_string(),
            profile: "balanced".to_string(),
            root_dir: ".imperaos/team/jobs".to_string(),
            process_id: Some(4242),
        };
        let json = serde_json::to_value(payload).expect("serialize");

        assert_eq!(json["contractVersion"], CONTRACT_VERSION);
        assert_eq!(json["jobId"], "job-4");
    }

    #[test]
    fn bundled_python_relative_path_matches_platform() {
        let path = bundled_python_relative_path();
        if cfg!(windows) {
            assert_eq!(path, "imperaos-runtime/python/Scripts/python.exe");
        } else {
            assert_eq!(path, "imperaos-runtime/python/bin/python");
        }
    }

    #[test]
    fn resolve_bundled_python_from_resource_dir_detects_runtime() {
        let dir = tempfile::tempdir().expect("tempdir");
        let resource_dir = dir.path();
        let python = resource_dir.join(bundled_python_relative_path());
        fs::create_dir_all(python.parent().expect("parent")).expect("mkdir");
        fs::write(&python, "placeholder").expect("python");

        let resolved = resolve_bundled_python_from_resource_dir(resource_dir).expect("runtime");

        assert_eq!(resolved, python);
    }

    #[test]
    fn resolve_bundled_python_from_resource_dir_detects_tauri_nested_runtime() {
        let dir = tempfile::tempdir().expect("tempdir");
        let resource_dir = dir.path();
        let python = resource_dir
            .join("resources")
            .join(bundled_python_relative_path());
        fs::create_dir_all(python.parent().expect("parent")).expect("mkdir");
        fs::write(&python, "placeholder").expect("python");

        let resolved = resolve_bundled_python_from_resource_dir(resource_dir).expect("runtime");

        assert_eq!(resolved, python);
    }

    #[test]
    fn resolve_cli_command_auto_prefers_cli_path_then_bundled() {
        let dir = tempfile::tempdir().expect("tempdir");
        let bundled = dir.path().join("python");
        fs::write(&bundled, "placeholder").expect("python");
        let config = BridgeConfig {
            mode: Some("auto".to_string()),
            cli_path: Some("imperaos-custom".to_string()),
            bundled_python_path: Some(bundled.to_string_lossy().to_string()),
            profile: Some("balanced".to_string()),
            root_dir: None,
            env: HashMap::new(),
            timeout_ms: None,
        };

        let external = resolve_cli_command(&config, None).expect("external");
        assert_eq!(external.mode, CoreMode::External);
        assert_eq!(external.program, "imperaos-custom");

        let bundled_config = BridgeConfig {
            cli_path: None,
            ..config
        };
        let bundled = resolve_cli_command(&bundled_config, None).expect("bundled");
        assert_eq!(bundled.mode, CoreMode::Bundled);
        assert_eq!(bundled.prefix_args, vec!["-m", "imperaos"]);
    }

    #[test]
    fn resolve_cli_command_auto_prefers_cli_path_over_resource_runtime() {
        let dir = tempfile::tempdir().expect("tempdir");
        let resource_dir = dir.path().join("resources");
        let python = resource_dir.join(bundled_python_relative_path());
        fs::create_dir_all(python.parent().expect("parent")).expect("mkdir");
        fs::write(&python, "placeholder").expect("python");
        let config = BridgeConfig {
            mode: Some("auto".to_string()),
            cli_path: Some("imperaos-custom".to_string()),
            bundled_python_path: None,
            profile: Some("balanced".to_string()),
            root_dir: None,
            env: HashMap::new(),
            timeout_ms: None,
        };

        let resolved = resolve_cli_command(&config, Some(&resource_dir)).expect("external");

        assert_eq!(resolved.mode, CoreMode::External);
        assert_eq!(resolved.program, "imperaos-custom");
    }

    #[test]
    fn resolve_cli_command_auto_uses_resource_runtime_when_cli_absent() {
        let dir = tempfile::tempdir().expect("tempdir");
        let resource_dir = dir.path().join("resources");
        let python = resource_dir.join(bundled_python_relative_path());
        fs::create_dir_all(python.parent().expect("parent")).expect("mkdir");
        fs::write(&python, "placeholder").expect("python");
        let config = BridgeConfig {
            mode: Some("auto".to_string()),
            cli_path: None,
            bundled_python_path: None,
            profile: Some("balanced".to_string()),
            root_dir: None,
            env: HashMap::new(),
            timeout_ms: None,
        };

        let resolved = resolve_cli_command(&config, Some(&resource_dir)).expect("bundled");

        assert_eq!(resolved.mode, CoreMode::Bundled);
        assert_eq!(resolved.program, python.to_string_lossy());
        assert_eq!(resolved.prefix_args, vec!["-m", "imperaos"]);
    }

    #[test]
    fn resolve_cli_command_auto_uses_tauri_nested_resource_runtime_when_cli_absent() {
        let dir = tempfile::tempdir().expect("tempdir");
        let resource_dir = dir.path().join("Resources");
        let python = resource_dir
            .join("resources")
            .join(bundled_python_relative_path());
        fs::create_dir_all(python.parent().expect("parent")).expect("mkdir");
        fs::write(&python, "placeholder").expect("python");
        let config = BridgeConfig {
            mode: Some("auto".to_string()),
            cli_path: None,
            bundled_python_path: None,
            profile: Some("balanced".to_string()),
            root_dir: None,
            env: HashMap::new(),
            timeout_ms: None,
        };

        let resolved = resolve_cli_command(&config, Some(&resource_dir)).expect("bundled");

        assert_eq!(resolved.mode, CoreMode::Bundled);
        assert_eq!(resolved.program, python.to_string_lossy());
        assert_eq!(resolved.prefix_args, vec!["-m", "imperaos"]);
    }

    #[test]
    fn resolve_cli_command_external_fallback_uses_imperaos() {
        let config = BridgeConfig {
            mode: Some("external".to_string()),
            cli_path: None,
            bundled_python_path: None,
            profile: Some("balanced".to_string()),
            root_dir: None,
            env: HashMap::new(),
            timeout_ms: None,
        };

        let resolved = resolve_cli_command(&config, None).expect("external fallback");
        assert_eq!(resolved.mode, CoreMode::External);
        assert_eq!(resolved.program, "imperaos");
        assert!(resolved.prefix_args.is_empty());
    }

    #[test]
    fn desktop_runtime_workdirs_use_only_imperaos_identity() {
        let base = Path::new("data-root");

        assert_eq!(
            macos_runtime_workdir(base),
            base.join("com.imperaos.operatorpanel").join("runtime")
        );
        assert_eq!(
            windows_runtime_workdir(base),
            base.join("ImperaOS Operator Panel").join("runtime")
        );
        assert_eq!(
            unix_runtime_workdir(base),
            base.join("imperaos-operator-panel").join("runtime")
        );
    }

    #[test]
    fn path_separator_matches_platform() {
        if cfg!(windows) {
            assert_eq!(path_separator(), ";");
        } else {
            assert_eq!(path_separator(), ":");
        }
    }

    #[test]
    fn cli_env_allowlist_uses_only_canonical_project_prefix() {
        let legacy_product_key = format!("{}_MODEL_NAME", ["BIN", "LIQUID"].concat());
        let former_product_key = format!("{}_MODEL_NAME", ["AE", "GIS", "OS"].concat());

        assert!(is_allowed_cli_env_key("IMPERAOS_MODEL_NAME"));
        assert!(is_allowed_cli_env_key("OPENAI_API_KEY"));
        assert!(is_allowed_cli_env_key("DEEPSEEK_API_KEY"));
        assert!(is_allowed_cli_env_key("ANTHROPIC_API_KEY"));
        assert!(is_allowed_cli_env_key("COMPANY_LLM_API_KEY"));
        assert!(!is_allowed_cli_env_key(&legacy_product_key));
        assert!(!is_allowed_cli_env_key(&former_product_key));
        assert!(!is_allowed_cli_env_key("PYTHONPATH"));
    }

    #[test]
    fn spawn_cli_background_returns_pid_for_external_script() {
        let dir = tempfile::tempdir().expect("tempdir");
        let root = dir.path().join("jobs");
        fs::create_dir_all(&root).expect("mkdir");
        let script = if cfg!(windows) {
            let path = dir.path().join("fake-imperaos.cmd");
            fs::write(&path, "@echo off\r\nping -n 2 127.0.0.1 >nul\r\n").expect("script");
            path
        } else {
            let path = dir.path().join("fake-imperaos.sh");
            fs::write(&path, "#!/bin/sh\nsleep 1\n").expect("script");
            path
        };
        #[cfg(unix)]
        fs::set_permissions(&script, fs::Permissions::from_mode(0o755)).expect("chmod");

        let config = BridgeConfig {
            mode: Some("external".to_string()),
            cli_path: Some(script.to_string_lossy().to_string()),
            bundled_python_path: None,
            profile: Some("balanced".to_string()),
            root_dir: Some(root.to_string_lossy().to_string()),
            env: HashMap::new(),
            timeout_ms: Some(1_000),
        };

        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        let pid = runtime
            .block_on(spawn_cli_background(&config, vec!["noop".to_string()]))
            .expect("spawn");

        assert!(pid.is_some());
    }

    #[test]
    fn export_reconciliation_retains_receipt_until_idempotent_authority_ack() {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let root = tempfile::tempdir().expect("tempdir");
            let state = ArtifactExportState::new(root.path().join("journal"));
            let actor = ExportBinding::new("workspace-1", "user-1").expect("actor");
            let exact = ExportBinding::authorized(
                "workspace-1",
                "user-1",
                "user",
                "export-reconcile-1",
                "artifact-1",
                "revision-1",
                "json",
            )
            .expect("binding");
            let target = root.path().join("report.json");
            let bytes = br#"{"status":"ok"}"#.to_vec();
            let digest = format!("{:x}", Sha256::digest(&bytes));
            let issued = state
                .issue_ticket(target, exact, 1024, Duration::from_secs(60))
                .await
                .expect("ticket");
            let preflight = state
                .preflight(&issued.ticket, &actor, &bytes, &digest)
                .await
                .expect("preflight");
            state
                .prepare_reconciliation(&issued.ticket, &actor, &preflight)
                .await
                .expect("receipt");
            state
                .commit(&issued.ticket, &actor, bytes, &digest)
                .await
                .expect("write");

            let unavailable = reconcile_export_actions_with(
                &state,
                state.reconciliation_actions(&actor).await.expect("actions"),
                |_action| async {
                    Err(BridgeError::new(
                        "ARTIFACT_RPC_UNAVAILABLE",
                        "unavailable",
                        "",
                        "artifact export reconciliation",
                        true,
                    ))
                },
            )
            .await
            .expect_err("authority failure");
            assert!(unavailable.retryable);
            assert_eq!(
                state
                    .reconciliation_actions(&actor)
                    .await
                    .expect("retained")
                    .len(),
                1
            );

            let requests = Arc::new(StdMutex::new(Vec::new()));
            let observed = requests.clone();
            reconcile_export_actions_with(
                &state,
                state
                    .reconciliation_actions(&actor)
                    .await
                    .expect("retry actions"),
                move |action| {
                    let observed = observed.clone();
                    async move {
                        let (method, payload) = export_reconciliation_terminal_request(&action);
                        observed
                            .lock()
                            .expect("requests")
                            .push((method, payload.params));
                        Ok(())
                    }
                },
            )
            .await
            .expect("authority ack");

            let requests = requests.lock().expect("requests");
            assert_eq!(requests.len(), 1);
            assert_eq!(requests[0].0, "artifact.export.commit");
            assert_eq!(requests[0].1["idempotencyKey"], "commit-export-reconcile-1");
            assert!(state
                .reconciliation_actions(&actor)
                .await
                .expect("cleared")
                .is_empty());
        });
    }

    #[test]
    fn missing_export_reconciliation_uses_idempotent_native_write_failed_cancel() {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let root = tempfile::tempdir().expect("tempdir");
            let state = ArtifactExportState::new(root.path().join("journal"));
            let actor = ExportBinding::new("workspace-1", "user-1").expect("actor");
            let bytes = b"safe export".to_vec();
            let digest = format!("{:x}", Sha256::digest(&bytes));
            let issued = state
                .issue_ticket(
                    root.path().join("missing.json"),
                    ExportBinding::authorized(
                        "workspace-1",
                        "user-1",
                        "user",
                        "export-cancel-1",
                        "artifact-1",
                        "revision-1",
                        "json",
                    )
                    .expect("binding"),
                    1024,
                    Duration::from_secs(60),
                )
                .await
                .expect("ticket");
            let preflight = state
                .preflight(&issued.ticket, &actor, &bytes, &digest)
                .await
                .expect("preflight");
            state
                .prepare_reconciliation(&issued.ticket, &actor, &preflight)
                .await
                .expect("receipt");

            let actions = state.reconciliation_actions(&actor).await.expect("actions");
            let (method, payload) = export_reconciliation_terminal_request(&actions[0]);
            assert_eq!(method, "artifact.export.cancel");
            assert_eq!(payload.params["reason"], "native_write_failed");
            assert_eq!(
                payload.params["idempotencyKey"],
                "cancel-export-cancel-1-native_write_failed"
            );
            assert_eq!(
                payload.idempotency_key.as_deref(),
                Some("cancel-export-cancel-1-native_write_failed")
            );
        });
    }
}
