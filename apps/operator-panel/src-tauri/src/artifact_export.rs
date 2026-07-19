use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};
use tokio::sync::Mutex;
use uuid::Uuid;

pub const DEFAULT_MAX_EXPORT_BYTES: usize = 100 * 1024 * 1024;
pub const DEFAULT_TICKET_TTL: Duration = Duration::from_secs(5 * 60);
const MAX_TICKET_TTL: Duration = Duration::from_secs(15 * 60);
const RECONCILIATION_RECEIPT_VERSION: u8 = 1;
const MAX_RECONCILIATION_RECEIPT_BYTES: u64 = 64 * 1024;
const MAX_RECONCILIATION_RECEIPTS: usize = 1_024;

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ExportBinding {
    workspace_id: String,
    principal_id: String,
    principal_type: String,
    export_id: String,
    artifact_id: String,
    revision_id: String,
    format: String,
}

impl ExportBinding {
    pub fn new(
        workspace_id: impl Into<String>,
        principal_id: impl Into<String>,
    ) -> Result<Self, ExportBoundaryError> {
        let binding = Self {
            workspace_id: workspace_id.into(),
            principal_id: principal_id.into(),
            principal_type: "user".to_string(),
            export_id: "legacy-export".to_string(),
            artifact_id: "legacy-artifact".to_string(),
            revision_id: "legacy-revision".to_string(),
            format: "json".to_string(),
        };
        if !is_bounded_id(&binding.workspace_id) || !is_bounded_id(&binding.principal_id) {
            return Err(ExportBoundaryError::permission_denied());
        }
        Ok(binding)
    }

    pub fn authorized(
        workspace_id: impl Into<String>,
        principal_id: impl Into<String>,
        principal_type: impl Into<String>,
        export_id: impl Into<String>,
        artifact_id: impl Into<String>,
        revision_id: impl Into<String>,
        format: impl Into<String>,
    ) -> Result<Self, ExportBoundaryError> {
        let binding = Self {
            workspace_id: workspace_id.into(),
            principal_id: principal_id.into(),
            principal_type: principal_type.into(),
            export_id: export_id.into(),
            artifact_id: artifact_id.into(),
            revision_id: revision_id.into(),
            format: format.into(),
        };
        if !is_bounded_id(&binding.workspace_id)
            || !is_bounded_id(&binding.principal_id)
            || binding.principal_type != "user"
            || !is_bounded_id(&binding.export_id)
            || !is_bounded_id(&binding.artifact_id)
            || !is_bounded_id(&binding.revision_id)
            || binding.format.is_empty()
            || binding.format.len() > 32
        {
            return Err(ExportBoundaryError::permission_denied());
        }
        Ok(binding)
    }

    pub fn export_id(&self) -> &str {
        &self.export_id
    }

    fn same_actor(&self, other: &Self) -> bool {
        self.workspace_id == other.workspace_id && self.principal_id == other.principal_id
    }
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ExportReconciliationReceipt {
    version: u8,
    ticket: String,
    target: PathBuf,
    binding: ExportBinding,
    basename: String,
    sha256: String,
    size_bytes: usize,
}

impl ExportReconciliationReceipt {
    pub(crate) fn export_id(&self) -> &str {
        self.binding.export_id()
    }

    pub(crate) fn basename(&self) -> &str {
        &self.basename
    }

    pub(crate) fn sha256(&self) -> &str {
        &self.sha256
    }

    pub(crate) fn size_bytes(&self) -> usize {
        self.size_bytes
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ExportReconciliationAction {
    Commit(ExportReconciliationReceipt),
    CancelNativeWriteFailed(ExportReconciliationReceipt),
}

impl ExportReconciliationAction {
    pub(crate) fn receipt(&self) -> &ExportReconciliationReceipt {
        match self {
            Self::Commit(receipt) | Self::CancelNativeWriteFailed(receipt) => receipt,
        }
    }
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct IssuedExportTicket {
    pub ticket: String,
    pub expires_in_ms: u64,
    pub max_bytes: usize,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct ArtifactExportResult {
    pub basename: String,
    pub sha256: String,
    pub size_bytes: usize,
    #[serde(skip_serializing)]
    pub binding: ExportBinding,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct ArtifactExportCancelResult {
    pub cancelled: bool,
    #[serde(skip_serializing)]
    pub binding: ExportBinding,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct ExportBoundaryError {
    pub code: String,
    pub message: String,
    pub retryable: bool,
    #[serde(skip)]
    reconciliation_required: bool,
}

impl ExportBoundaryError {
    fn new(code: &str, message: &str, retryable: bool) -> Self {
        Self {
            code: code.to_string(),
            message: message.to_string(),
            retryable,
            reconciliation_required: false,
        }
    }

    fn permission_denied() -> Self {
        Self::new(
            "ARTIFACT_PERMISSION_DENIED",
            "artifact export ticket binding is invalid",
            false,
        )
    }

    fn cancelled() -> Self {
        Self::new(
            "ARTIFACT_EXPORT_CANCELLED",
            "artifact export ticket is missing, expired, or already consumed",
            false,
        )
    }

    fn failed(message: &str, retryable: bool) -> Self {
        Self::new("ARTIFACT_EXPORT_FAILED", message, retryable)
    }

    fn post_rename_durability_uncertain() -> Self {
        let mut error = Self::failed(
            "artifact export was renamed but directory durability is uncertain",
            true,
        );
        error.reconciliation_required = true;
        error
    }

    pub(crate) fn requires_reconciliation(&self) -> bool {
        self.reconciliation_required
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum AtomicWriteFailure {
    BeforeRename,
    #[cfg_attr(windows, allow(dead_code))]
    AfterRename,
}

type AtomicWriter = fn(&Path, &str, &[u8]) -> Result<(), AtomicWriteFailure>;

#[derive(Clone)]
enum ExportTicketPhase {
    Issued,
    Writing,
    Written {
        basename: String,
        sha256: String,
        size_bytes: usize,
    },
}

#[derive(Clone)]
struct ExportTicketRecord {
    target: PathBuf,
    binding: ExportBinding,
    max_bytes: usize,
    expires_at: Instant,
    phase: ExportTicketPhase,
}

pub struct ArtifactExportState {
    tickets: Mutex<HashMap<String, ExportTicketRecord>>,
    journal_root: PathBuf,
    reconciliation_lock: Mutex<()>,
}

impl Default for ArtifactExportState {
    fn default() -> Self {
        Self::new(PathBuf::new())
    }
}

impl ArtifactExportState {
    pub fn new(journal_root: PathBuf) -> Self {
        Self {
            tickets: Mutex::new(HashMap::new()),
            journal_root,
            reconciliation_lock: Mutex::new(()),
        }
    }

    pub async fn preflight(
        &self,
        ticket: &str,
        binding: &ExportBinding,
        bytes: &[u8],
        expected_sha256: &str,
    ) -> Result<ArtifactExportResult, ExportBoundaryError> {
        let mut tickets = self.tickets.lock().await;
        let record = tickets
            .get(ticket)
            .ok_or_else(ExportBoundaryError::cancelled)?;
        if !record.binding.same_actor(binding) {
            return Err(ExportBoundaryError::permission_denied());
        }
        if record.expires_at <= Instant::now() {
            tickets.remove(ticket);
            return Err(ExportBoundaryError::cancelled());
        }
        if bytes.len() > record.max_bytes {
            return Err(ExportBoundaryError::failed(
                "artifact export exceeds its ticket size boundary",
                false,
            ));
        }
        let observed_sha256 = format!("{:x}", Sha256::digest(bytes));
        if observed_sha256 != expected_sha256 {
            return Err(ExportBoundaryError::failed(
                "artifact export hash does not match",
                false,
            ));
        }
        let basename = record
            .target
            .file_name()
            .and_then(|value| value.to_str())
            .ok_or_else(|| ExportBoundaryError::failed("export basename is invalid", false))?
            .to_string();
        Ok(ArtifactExportResult {
            basename,
            sha256: observed_sha256,
            size_bytes: bytes.len(),
            binding: record.binding.clone(),
        })
    }

    pub async fn binding_for_ticket(
        &self,
        ticket: &str,
        binding: &ExportBinding,
    ) -> Result<ExportBinding, ExportBoundaryError> {
        let mut tickets = self.tickets.lock().await;
        let record = tickets
            .get(ticket)
            .ok_or_else(ExportBoundaryError::cancelled)?;
        if !record.binding.same_actor(binding) {
            return Err(ExportBoundaryError::permission_denied());
        }
        if record.expires_at <= Instant::now() {
            tickets.remove(ticket);
            return Err(ExportBoundaryError::cancelled());
        }
        Ok(record.binding.clone())
    }

    pub async fn issue_ticket(
        &self,
        target: PathBuf,
        binding: ExportBinding,
        max_bytes: usize,
        ttl: Duration,
    ) -> Result<IssuedExportTicket, ExportBoundaryError> {
        if max_bytes == 0
            || max_bytes > DEFAULT_MAX_EXPORT_BYTES
            || ttl.is_zero()
            || ttl > MAX_TICKET_TTL
            || target.file_name().is_none()
            || !matches!(target.parent(), Some(parent) if parent.is_dir())
        {
            return Err(ExportBoundaryError::failed(
                "artifact export target or boundary is invalid",
                false,
            ));
        }
        let ticket = format!("export-{}", Uuid::new_v4().simple());
        self.tickets.lock().await.insert(
            ticket.clone(),
            ExportTicketRecord {
                target,
                binding,
                max_bytes,
                expires_at: Instant::now() + ttl,
                phase: ExportTicketPhase::Issued,
            },
        );
        Ok(IssuedExportTicket {
            ticket,
            expires_in_ms: ttl.as_millis() as u64,
            max_bytes,
        })
    }

    pub async fn commit(
        &self,
        ticket: &str,
        binding: &ExportBinding,
        bytes: Vec<u8>,
        expected_sha256: &str,
    ) -> Result<ArtifactExportResult, ExportBoundaryError> {
        self.commit_with_writer(ticket, binding, bytes, expected_sha256, atomic_write)
            .await
    }

    async fn commit_with_writer(
        &self,
        ticket: &str,
        binding: &ExportBinding,
        bytes: Vec<u8>,
        expected_sha256: &str,
        writer: AtomicWriter,
    ) -> Result<ArtifactExportResult, ExportBoundaryError> {
        let record = self.record_for_ticket(ticket, binding).await?;
        if bytes.len() > record.max_bytes {
            return Err(ExportBoundaryError::failed(
                "artifact export exceeds its ticket size boundary",
                false,
            ));
        }
        if expected_sha256.len() != 64
            || !expected_sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            return Err(ExportBoundaryError::failed(
                "artifact export hash is invalid",
                false,
            ));
        }
        let observed_sha256 = format!("{:x}", Sha256::digest(&bytes));
        if observed_sha256 != expected_sha256 {
            return Err(ExportBoundaryError::failed(
                "artifact export hash does not match",
                false,
            ));
        }
        let target = record.target;
        let result_binding = record.binding;
        let basename = target
            .file_name()
            .and_then(|value| value.to_str())
            .ok_or_else(|| ExportBoundaryError::failed("export basename is invalid", false))?
            .to_string();
        let ticket_owned = ticket.to_string();
        let size_bytes = bytes.len();
        {
            let mut tickets = self.tickets.lock().await;
            let current = tickets
                .get_mut(ticket)
                .ok_or_else(ExportBoundaryError::cancelled)?;
            match &current.phase {
                ExportTicketPhase::Issued => current.phase = ExportTicketPhase::Writing,
                ExportTicketPhase::Writing => {
                    return Err(ExportBoundaryError::failed(
                        "artifact export write is already in progress",
                        true,
                    ));
                }
                ExportTicketPhase::Written {
                    basename,
                    sha256,
                    size_bytes,
                } => {
                    if sha256 != &observed_sha256 || *size_bytes != bytes.len() {
                        return Err(ExportBoundaryError::failed(
                            "written artifact export retry does not match",
                            false,
                        ));
                    }
                    return Ok(ArtifactExportResult {
                        basename: basename.clone(),
                        sha256: sha256.clone(),
                        size_bytes: *size_bytes,
                        binding: current.binding.clone(),
                    });
                }
            }
        }
        let write_result =
            match tokio::task::spawn_blocking(move || writer(&target, &ticket_owned, &bytes)).await
            {
                Ok(result) => result,
                Err(_) => {
                    if let Some(current) = self.tickets.lock().await.get_mut(ticket) {
                        current.phase = ExportTicketPhase::Issued;
                    }
                    return Err(ExportBoundaryError::failed(
                        "artifact export write task failed",
                        true,
                    ));
                }
            };
        if let Err(failure) = write_result {
            let mut tickets = self.tickets.lock().await;
            if let Some(current) = tickets.get_mut(ticket) {
                match failure {
                    AtomicWriteFailure::BeforeRename => {
                        current.phase = ExportTicketPhase::Issued;
                    }
                    AtomicWriteFailure::AfterRename => {
                        current.phase = ExportTicketPhase::Written {
                            basename,
                            sha256: observed_sha256,
                            size_bytes,
                        };
                        return Err(ExportBoundaryError::post_rename_durability_uncertain());
                    }
                }
            }
            return Err(ExportBoundaryError::failed(
                "artifact export could not be committed atomically",
                true,
            ));
        }
        if let Some(current) = self.tickets.lock().await.get_mut(ticket) {
            current.phase = ExportTicketPhase::Written {
                basename: basename.clone(),
                sha256: observed_sha256.clone(),
                size_bytes,
            };
        } else {
            return Err(ExportBoundaryError::cancelled());
        }
        Ok(ArtifactExportResult {
            basename,
            sha256: observed_sha256,
            size_bytes,
            binding: result_binding,
        })
    }

    pub(crate) async fn prepare_reconciliation(
        &self,
        ticket: &str,
        binding: &ExportBinding,
        result: &ArtifactExportResult,
    ) -> Result<(), ExportBoundaryError> {
        let record = self.record_for_ticket(ticket, binding).await?;
        if record.binding != result.binding {
            return Err(ExportBoundaryError::permission_denied());
        }
        let target = record.target;
        let basename = target
            .file_name()
            .and_then(|value| value.to_str())
            .ok_or_else(|| ExportBoundaryError::failed("export basename is invalid", false))?
            .to_string();
        if basename != result.basename
            || result.sha256.len() != 64
            || !result
                .sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            || result.size_bytes > record.max_bytes
        {
            return Err(ExportBoundaryError::failed(
                "artifact export reconciliation receipt is invalid",
                false,
            ));
        }
        let receipt = ExportReconciliationReceipt {
            version: RECONCILIATION_RECEIPT_VERSION,
            ticket: ticket.to_string(),
            target,
            binding: record.binding,
            basename,
            sha256: result.sha256.clone(),
            size_bytes: result.size_bytes,
        };
        self.persist_reconciliation(receipt).await
    }

    pub(crate) async fn reconciliation_actions(
        &self,
        binding: &ExportBinding,
    ) -> Result<Vec<ExportReconciliationAction>, ExportBoundaryError> {
        let _guard = self.reconciliation_lock.lock().await;
        let receipts = self.load_reconciliations()?;
        let mut actions = Vec::new();
        for receipt in receipts {
            if !receipt.binding.same_actor(binding) {
                continue;
            }
            let observed = receipt.clone();
            let matches = tokio::task::spawn_blocking(move || target_matches_receipt(&observed))
                .await
                .map_err(|_| {
                    ExportBoundaryError::failed("artifact export reconciliation task failed", true)
                })??;
            actions.push(if matches {
                ExportReconciliationAction::Commit(receipt)
            } else {
                ExportReconciliationAction::CancelNativeWriteFailed(receipt)
            });
        }
        Ok(actions)
    }

    pub(crate) async fn acknowledge_reconciliation(
        &self,
        export_id: &str,
    ) -> Result<(), ExportBoundaryError> {
        if self.journal_root.as_os_str().is_empty() {
            return Ok(());
        }
        if !is_bounded_id(export_id) {
            return Err(ExportBoundaryError::failed(
                "artifact export reconciliation ID is invalid",
                false,
            ));
        }
        let path = self.journal_root.join(format!("{export_id}.json"));
        tokio::task::spawn_blocking(move || match fs::remove_file(path) {
            Ok(()) => Ok(()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(_) => Err(ExportBoundaryError::failed(
                "artifact export reconciliation receipt could not be removed",
                true,
            )),
        })
        .await
        .map_err(|_| {
            ExportBoundaryError::failed("artifact export reconciliation task failed", true)
        })?
    }

    pub async fn finalize(
        &self,
        ticket: &str,
        binding: &ExportBinding,
    ) -> Result<(), ExportBoundaryError> {
        let record = self.take_ticket(ticket, binding).await?;
        self.acknowledge_reconciliation(record.binding.export_id())
            .await
    }

    pub async fn cancel(
        &self,
        ticket: &str,
        binding: &ExportBinding,
    ) -> Result<ArtifactExportCancelResult, ExportBoundaryError> {
        self.require_cancellable(ticket, binding).await?;
        let record = self.take_ticket(ticket, binding).await?;
        self.acknowledge_reconciliation(record.binding.export_id())
            .await?;
        Ok(ArtifactExportCancelResult {
            cancelled: true,
            binding: record.binding,
        })
    }

    pub async fn require_cancellable(
        &self,
        ticket: &str,
        binding: &ExportBinding,
    ) -> Result<(), ExportBoundaryError> {
        let record = self.record_for_ticket(ticket, binding).await?;
        match record.phase {
            ExportTicketPhase::Issued => Ok(()),
            ExportTicketPhase::Writing | ExportTicketPhase::Written { .. } => {
                Err(ExportBoundaryError::failed(
                    "written artifact export requires terminal completion",
                    true,
                ))
            }
        }
    }

    async fn take_ticket(
        &self,
        ticket: &str,
        binding: &ExportBinding,
    ) -> Result<ExportTicketRecord, ExportBoundaryError> {
        let mut tickets = self.tickets.lock().await;
        let record = tickets
            .get(ticket)
            .ok_or_else(ExportBoundaryError::cancelled)?;
        if !record.binding.same_actor(binding) {
            return Err(ExportBoundaryError::permission_denied());
        }
        if record.expires_at <= Instant::now() {
            tickets.remove(ticket);
            return Err(ExportBoundaryError::cancelled());
        }
        tickets
            .remove(ticket)
            .ok_or_else(ExportBoundaryError::cancelled)
    }

    async fn record_for_ticket(
        &self,
        ticket: &str,
        binding: &ExportBinding,
    ) -> Result<ExportTicketRecord, ExportBoundaryError> {
        let mut tickets = self.tickets.lock().await;
        let record = tickets
            .get(ticket)
            .ok_or_else(ExportBoundaryError::cancelled)?;
        if !record.binding.same_actor(binding) {
            return Err(ExportBoundaryError::permission_denied());
        }
        if record.expires_at <= Instant::now() {
            tickets.remove(ticket);
            return Err(ExportBoundaryError::cancelled());
        }
        Ok(record.clone())
    }

    async fn persist_reconciliation(
        &self,
        receipt: ExportReconciliationReceipt,
    ) -> Result<(), ExportBoundaryError> {
        if self.journal_root.as_os_str().is_empty() {
            return Err(ExportBoundaryError::failed(
                "artifact export reconciliation root is unavailable",
                true,
            ));
        }
        let bytes = serde_json::to_vec(&receipt).map_err(|_| {
            ExportBoundaryError::failed(
                "artifact export reconciliation receipt could not be encoded",
                false,
            )
        })?;
        if bytes.len() as u64 > MAX_RECONCILIATION_RECEIPT_BYTES {
            return Err(ExportBoundaryError::failed(
                "artifact export reconciliation receipt exceeds its size boundary",
                false,
            ));
        }
        let root = self.journal_root.clone();
        let target = root.join(format!("{}.json", receipt.export_id()));
        let ticket = receipt.ticket.clone();
        tokio::task::spawn_blocking(move || {
            fs::create_dir_all(&root).map_err(|_| {
                ExportBoundaryError::failed(
                    "artifact export reconciliation root could not be created",
                    true,
                )
            })?;
            atomic_write(&target, &ticket, &bytes).map_err(|_| {
                ExportBoundaryError::failed(
                    "artifact export reconciliation receipt could not be persisted",
                    true,
                )
            })
        })
        .await
        .map_err(|_| {
            ExportBoundaryError::failed("artifact export reconciliation task failed", true)
        })?
    }

    fn load_reconciliations(
        &self,
    ) -> Result<Vec<ExportReconciliationReceipt>, ExportBoundaryError> {
        if self.journal_root.as_os_str().is_empty() || !self.journal_root.exists() {
            return Ok(Vec::new());
        }
        let mut paths = fs::read_dir(&self.journal_root)
            .map_err(|_| {
                ExportBoundaryError::failed(
                    "artifact export reconciliation root could not be read",
                    true,
                )
            })?
            .filter_map(Result::ok)
            .map(|entry| entry.path())
            .filter(|path| path.extension().and_then(|value| value.to_str()) == Some("json"))
            .collect::<Vec<_>>();
        paths.sort();
        if paths.len() > MAX_RECONCILIATION_RECEIPTS {
            return Err(ExportBoundaryError::failed(
                "artifact export reconciliation receipt count exceeds its boundary",
                false,
            ));
        }
        paths
            .into_iter()
            .map(|path| load_reconciliation_receipt(&path))
            .collect()
    }
}

fn load_reconciliation_receipt(
    path: &Path,
) -> Result<ExportReconciliationReceipt, ExportBoundaryError> {
    let metadata = fs::symlink_metadata(path).map_err(|_| {
        ExportBoundaryError::failed(
            "artifact export reconciliation receipt is unavailable",
            true,
        )
    })?;
    if !metadata.file_type().is_file() || metadata.len() > MAX_RECONCILIATION_RECEIPT_BYTES {
        return Err(ExportBoundaryError::failed(
            "artifact export reconciliation receipt is invalid",
            false,
        ));
    }
    let bytes = fs::read(path).map_err(|_| {
        ExportBoundaryError::failed(
            "artifact export reconciliation receipt could not be read",
            true,
        )
    })?;
    let receipt: ExportReconciliationReceipt = serde_json::from_slice(&bytes).map_err(|_| {
        ExportBoundaryError::failed("artifact export reconciliation receipt is invalid", false)
    })?;
    let expected_name = format!("{}.json", receipt.export_id());
    if receipt.version != RECONCILIATION_RECEIPT_VERSION
        || receipt.ticket.is_empty()
        || receipt.ticket.len() > 128
        || !receipt.ticket.starts_with("export-")
        || !is_valid_binding(&receipt.binding)
        || receipt.basename.is_empty()
        || receipt.basename.len() > 255
        || receipt.target.file_name().and_then(|value| value.to_str())
            != Some(receipt.basename.as_str())
        || receipt.sha256.len() != 64
        || !receipt
            .sha256
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        || receipt.size_bytes > DEFAULT_MAX_EXPORT_BYTES
        || path.file_name().and_then(|value| value.to_str()) != Some(expected_name.as_str())
    {
        return Err(ExportBoundaryError::failed(
            "artifact export reconciliation receipt is invalid",
            false,
        ));
    }
    Ok(receipt)
}

fn target_matches_receipt(
    receipt: &ExportReconciliationReceipt,
) -> Result<bool, ExportBoundaryError> {
    let metadata = match fs::symlink_metadata(&receipt.target) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(_) => {
            return Err(ExportBoundaryError::failed(
                "artifact export reconciliation target could not be inspected",
                true,
            ))
        }
    };
    if !metadata.file_type().is_file() || metadata.len() != receipt.size_bytes as u64 {
        return Ok(false);
    }
    let mut file = File::open(&receipt.target).map_err(|_| {
        ExportBoundaryError::failed(
            "artifact export reconciliation target could not be read",
            true,
        )
    })?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let count = file.read(&mut buffer).map_err(|_| {
            ExportBoundaryError::failed(
                "artifact export reconciliation target could not be read",
                true,
            )
        })?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hasher.finalize()) == receipt.sha256)
}

fn is_valid_binding(binding: &ExportBinding) -> bool {
    is_bounded_id(&binding.workspace_id)
        && is_bounded_id(&binding.principal_id)
        && binding.principal_type == "user"
        && is_bounded_id(&binding.export_id)
        && is_bounded_id(&binding.artifact_id)
        && is_bounded_id(&binding.revision_id)
        && !binding.format.is_empty()
        && binding.format.len() <= 32
}

fn atomic_write(target: &Path, ticket: &str, bytes: &[u8]) -> Result<(), AtomicWriteFailure> {
    let basename = target
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or(AtomicWriteFailure::BeforeRename)?;
    let temp_path = target.with_file_name(format!(".{basename}.{ticket}.tmp"));
    let mut created_by_us = false;
    let write_result = (|| -> Result<(), AtomicWriteFailure> {
        let mut temp = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&temp_path)
            .map_err(|_| AtomicWriteFailure::BeforeRename)?;
        created_by_us = true;
        temp.write_all(bytes)
            .map_err(|_| AtomicWriteFailure::BeforeRename)?;
        temp.sync_all()
            .map_err(|_| AtomicWriteFailure::BeforeRename)?;
        drop(temp);
        atomic_replace(&temp_path, target)
    })();
    if matches!(write_result, Err(AtomicWriteFailure::BeforeRename)) {
        if created_by_us {
            let _ = fs::remove_file(&temp_path);
        }
    }
    write_result
}

#[cfg(not(windows))]
fn atomic_replace(temp_path: &Path, target: &Path) -> Result<(), AtomicWriteFailure> {
    fs::rename(temp_path, target).map_err(|_| AtomicWriteFailure::BeforeRename)?;
    if let Some(parent) = target.parent() {
        File::open(parent)
            .and_then(|directory| directory.sync_all())
            .map_err(|_| AtomicWriteFailure::AfterRename)?;
    }
    Ok(())
}

#[cfg(windows)]
fn atomic_replace(temp_path: &Path, target: &Path) -> Result<(), AtomicWriteFailure> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH,
    };

    let from = temp_path
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let to = target
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    // SAFETY: both buffers are owned, NUL-terminated UTF-16 paths and remain
    // alive for the duration of the synchronous Windows API call.
    let result = unsafe {
        MoveFileExW(
            from.as_ptr(),
            to.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if result == 0 {
        return Err(AtomicWriteFailure::BeforeRename);
    }
    Ok(())
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

#[cfg(test)]
mod tests {
    use super::*;
    use sha2::{Digest, Sha256};
    use std::time::Duration;

    fn binding(principal: &str) -> ExportBinding {
        ExportBinding::new("workspace-1", principal).expect("binding should validate")
    }

    #[test]
    fn ticket_is_principal_bound_single_use_and_path_opaque() {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let state = ArtifactExportState::default();
            let root = tempfile::tempdir().expect("tempdir");
            let issued = state
                .issue_ticket(
                    root.path().join("report.json"),
                    binding("user-1"),
                    1024,
                    Duration::from_secs(60),
                )
                .await
                .expect("ticket");
            let serialized = serde_json::to_string(&issued).expect("serialize");

            assert!(!serialized.contains(root.path().to_string_lossy().as_ref()));
            assert!(state
                .cancel(&issued.ticket, &binding("user-2"))
                .await
                .is_err());
            assert!(state
                .cancel(&issued.ticket, &binding("user-1"))
                .await
                .is_ok());
            assert!(state
                .cancel(&issued.ticket, &binding("user-1"))
                .await
                .is_err());
        });
    }

    #[test]
    fn authorized_ticket_retains_exact_revision_binding_without_renderer_leakage() {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let state = ArtifactExportState::default();
            let root = tempfile::tempdir().expect("tempdir");
            let exact = ExportBinding::authorized(
                "workspace-1",
                "user-1",
                "user",
                "export-1",
                "artifact-1",
                "revision-7",
                "source",
            )
            .expect("authorized binding");
            let issued = state
                .issue_ticket(
                    root.path().join("main.py"),
                    exact.clone(),
                    1024,
                    Duration::from_secs(60),
                )
                .await
                .expect("ticket");

            let observed = state
                .binding_for_ticket(&issued.ticket, &binding("user-1"))
                .await
                .expect("binding lookup");
            assert_eq!(observed, exact);
            let cancelled = state
                .cancel(&issued.ticket, &binding("user-1"))
                .await
                .expect("cancel");
            let serialized = serde_json::to_string(&cancelled).expect("serialize");
            assert!(!serialized.contains("revision-7"));
            assert!(!serialized.contains("export-1"));
        });
    }

    #[test]
    fn commit_checks_hash_size_and_leaves_no_partial_file() {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let state = ArtifactExportState::default();
            let root = tempfile::tempdir().expect("tempdir");
            let target = root.path().join("report.json");
            let bytes = br#"{"status":"ok"}"#.to_vec();
            let digest = format!("{:x}", Sha256::digest(&bytes));
            let issued = state
                .issue_ticket(
                    target.clone(),
                    binding("user-1"),
                    1024,
                    Duration::from_secs(60),
                )
                .await
                .expect("ticket");
            let result = state
                .commit(&issued.ticket, &binding("user-1"), bytes.clone(), &digest)
                .await
                .expect("commit");

            assert_eq!(std::fs::read(&target).expect("target"), bytes);
            assert_eq!(result.sha256, digest);
            assert_eq!(result.size_bytes, 15);
            assert!(state
                .binding_for_ticket(&issued.ticket, &binding("user-1"))
                .await
                .is_ok());
            let cancel_error = state
                .cancel(&issued.ticket, &binding("user-1"))
                .await
                .expect_err("written ticket must remain completion-only");
            assert_eq!(cancel_error.code, "ARTIFACT_EXPORT_FAILED");
            state
                .finalize(&issued.ticket, &binding("user-1"))
                .await
                .expect("terminal authority acknowledgement");
            assert!(state
                .commit(&issued.ticket, &binding("user-1"), Vec::new(), &digest)
                .await
                .is_err());
            assert_eq!(
                std::fs::read_dir(root.path()).expect("dir").count(),
                1,
                "no temp file may remain"
            );
        });
    }

    #[test]
    fn failed_create_does_not_delete_a_preexisting_temp_file() {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let state = ArtifactExportState::default();
            let root = tempfile::tempdir().expect("tempdir");
            let target = root.path().join("report.json");
            let bytes = b"safe export".to_vec();
            let digest = format!("{:x}", Sha256::digest(&bytes));
            let issued = state
                .issue_ticket(
                    target.clone(),
                    binding("user-1"),
                    1024,
                    Duration::from_secs(60),
                )
                .await
                .expect("ticket");
            let temp = root
                .path()
                .join(format!(".report.json.{}.tmp", issued.ticket));
            std::fs::write(&temp, b"not ours").expect("seed collision");

            let error = state
                .commit(&issued.ticket, &binding("user-1"), bytes, &digest)
                .await
                .expect_err("create_new collision must fail closed");

            assert_eq!(error.code, "ARTIFACT_EXPORT_FAILED");
            assert_eq!(
                std::fs::read(&temp).expect("collision survives"),
                b"not ours"
            );
            assert!(!target.exists());
        });
    }

    #[test]
    fn expired_and_oversized_tickets_fail_without_output() {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let state = ArtifactExportState::default();
            let root = tempfile::tempdir().expect("tempdir");
            let expired_target = root.path().join("expired.json");
            let expired = state
                .issue_ticket(
                    expired_target.clone(),
                    binding("user-1"),
                    16,
                    Duration::from_millis(1),
                )
                .await
                .expect("ticket");
            tokio::time::sleep(Duration::from_millis(5)).await;
            let empty_digest = format!("{:x}", Sha256::digest([]));
            let expired_error = state
                .commit(
                    &expired.ticket,
                    &binding("user-1"),
                    Vec::new(),
                    &empty_digest,
                )
                .await
                .expect_err("expired ticket");
            assert_eq!(expired_error.code, "ARTIFACT_EXPORT_CANCELLED");
            assert!(!expired_target.exists());

            let oversized_target = root.path().join("oversized.json");
            let oversized = state
                .issue_ticket(
                    oversized_target.clone(),
                    binding("user-1"),
                    3,
                    Duration::from_secs(60),
                )
                .await
                .expect("ticket");
            let bytes = b"four".to_vec();
            let digest = format!("{:x}", Sha256::digest(&bytes));
            let size_error = state
                .commit(&oversized.ticket, &binding("user-1"), bytes, &digest)
                .await
                .expect_err("size boundary");
            assert_eq!(size_error.code, "ARTIFACT_EXPORT_FAILED");
            assert!(!oversized_target.exists());
        });
    }

    #[test]
    fn reconciliation_receipt_survives_restart_and_matches_written_bytes() {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let root = tempfile::tempdir().expect("tempdir");
            let journal_root = root.path().join("journal");
            let target = root.path().join("report.json");
            let bytes = br#"{"status":"ok"}"#.to_vec();
            let digest = format!("{:x}", Sha256::digest(&bytes));
            let exact = ExportBinding::authorized(
                "workspace-1",
                "user-1",
                "user",
                "export-restart-1",
                "artifact-1",
                "revision-1",
                "json",
            )
            .expect("binding");
            let state = ArtifactExportState::new(journal_root.clone());
            let issued = state
                .issue_ticket(target.clone(), exact.clone(), 1024, Duration::from_secs(60))
                .await
                .expect("ticket");
            let preflight = state
                .preflight(&issued.ticket, &binding("user-1"), &bytes, &digest)
                .await
                .expect("preflight");
            state
                .prepare_reconciliation(&issued.ticket, &binding("user-1"), &preflight)
                .await
                .expect("durable receipt");
            state
                .commit(&issued.ticket, &binding("user-1"), bytes, &digest)
                .await
                .expect("native write");
            drop(state);

            let restarted = ArtifactExportState::new(journal_root);
            let actions = restarted
                .reconciliation_actions(&binding("user-1"))
                .await
                .expect("recovery actions");

            assert_eq!(actions.len(), 1);
            match &actions[0] {
                ExportReconciliationAction::Commit(receipt) => {
                    assert_eq!(receipt.export_id(), "export-restart-1");
                    assert_eq!(receipt.basename(), "report.json");
                    assert_eq!(receipt.sha256(), digest);
                    assert_eq!(receipt.size_bytes(), 15);
                }
                ExportReconciliationAction::CancelNativeWriteFailed(_) => {
                    panic!("matching written bytes must replay commit")
                }
            }
        });
    }

    #[test]
    fn missing_target_reconciles_as_native_write_failure_until_acknowledged() {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let root = tempfile::tempdir().expect("tempdir");
            let journal_root = root.path().join("journal");
            let bytes = b"safe export".to_vec();
            let digest = format!("{:x}", Sha256::digest(&bytes));
            let state = ArtifactExportState::new(journal_root.clone());
            let issued = state
                .issue_ticket(
                    root.path().join("missing.json"),
                    ExportBinding::authorized(
                        "workspace-1",
                        "user-1",
                        "user",
                        "export-missing-1",
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
                .preflight(&issued.ticket, &binding("user-1"), &bytes, &digest)
                .await
                .expect("preflight");
            state
                .prepare_reconciliation(&issued.ticket, &binding("user-1"), &preflight)
                .await
                .expect("durable receipt");
            drop(state);

            let restarted = ArtifactExportState::new(journal_root.clone());
            let actions = restarted
                .reconciliation_actions(&binding("user-1"))
                .await
                .expect("recovery actions");
            assert!(matches!(
                actions.as_slice(),
                [ExportReconciliationAction::CancelNativeWriteFailed(receipt)]
                    if receipt.export_id() == "export-missing-1"
            ));

            drop(restarted);
            let still_pending = ArtifactExportState::new(journal_root.clone())
                .reconciliation_actions(&binding("user-1"))
                .await
                .expect("unacknowledged receipt");
            assert_eq!(
                still_pending.len(),
                1,
                "authority failure must retain receipt"
            );

            let acknowledged = ArtifactExportState::new(journal_root.clone());
            acknowledged
                .acknowledge_reconciliation("export-missing-1")
                .await
                .expect("terminal acknowledgement");
            assert!(ArtifactExportState::new(journal_root)
                .reconciliation_actions(&binding("user-1"))
                .await
                .expect("cleared journal")
                .is_empty());
        });
    }

    #[test]
    fn mismatched_target_reconciles_as_native_write_failure() {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let root = tempfile::tempdir().expect("tempdir");
            let journal_root = root.path().join("journal");
            let target = root.path().join("report.json");
            let expected = b"safe export".to_vec();
            let digest = format!("{:x}", Sha256::digest(&expected));
            let actor = binding("user-1");
            let state = ArtifactExportState::new(journal_root.clone());
            let issued = state
                .issue_ticket(
                    target.clone(),
                    ExportBinding::authorized(
                        "workspace-1",
                        "user-1",
                        "user",
                        "export-mismatch-1",
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
                .preflight(&issued.ticket, &actor, &expected, &digest)
                .await
                .expect("preflight");
            state
                .prepare_reconciliation(&issued.ticket, &actor, &preflight)
                .await
                .expect("durable receipt");
            fs::write(&target, b"tampered!!!").expect("same-size mismatched target");
            drop(state);

            let actions = ArtifactExportState::new(journal_root)
                .reconciliation_actions(&actor)
                .await
                .expect("recovery actions");
            assert!(matches!(
                actions.as_slice(),
                [ExportReconciliationAction::CancelNativeWriteFailed(receipt)]
                    if receipt.export_id() == "export-mismatch-1"
            ));
        });
    }

    #[test]
    fn post_rename_parent_sync_failure_retains_receipt_for_commit_reconciliation() {
        fn write_then_report_parent_sync_failure(
            target: &Path,
            _ticket: &str,
            bytes: &[u8],
        ) -> Result<(), AtomicWriteFailure> {
            fs::write(target, bytes).expect("simulate completed atomic rename");
            Err(AtomicWriteFailure::AfterRename)
        }

        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let root = tempfile::tempdir().expect("tempdir");
            let journal_root = root.path().join("journal");
            let target = root.path().join("report.json");
            let bytes = br#"{"status":"ok"}"#.to_vec();
            let digest = format!("{:x}", Sha256::digest(&bytes));
            let actor = binding("user-1");
            let exact = ExportBinding::authorized(
                "workspace-1",
                "user-1",
                "user",
                "export-post-rename-1",
                "artifact-1",
                "revision-1",
                "json",
            )
            .expect("binding");
            let state = ArtifactExportState::new(journal_root);
            let issued = state
                .issue_ticket(target.clone(), exact, 1024, Duration::from_secs(60))
                .await
                .expect("ticket");
            let preflight = state
                .preflight(&issued.ticket, &actor, &bytes, &digest)
                .await
                .expect("preflight");
            state
                .prepare_reconciliation(&issued.ticket, &actor, &preflight)
                .await
                .expect("durable receipt");

            let error = state
                .commit_with_writer(
                    &issued.ticket,
                    &actor,
                    bytes.clone(),
                    &digest,
                    write_then_report_parent_sync_failure,
                )
                .await
                .expect_err("directory sync uncertainty must be reconciled");

            assert!(error.requires_reconciliation());
            assert_eq!(fs::read(&target).expect("renamed target"), bytes);
            assert!(state
                .require_cancellable(&issued.ticket, &actor)
                .await
                .is_err());
            let actions = state
                .reconciliation_actions(&actor)
                .await
                .expect("reconciliation action");
            assert!(matches!(
                actions.as_slice(),
                [ExportReconciliationAction::Commit(receipt)]
                    if receipt.export_id() == "export-post-rename-1"
                        && receipt.sha256() == digest
                        && receipt.size_bytes() == bytes.len()
            ));
        });
    }
}
