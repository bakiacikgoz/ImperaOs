use std::collections::HashMap;
use std::fs::{self, File, OpenOptions};
use std::io::Read;
use std::path::PathBuf;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;
use uuid::Uuid;

pub const DEFAULT_MAX_ASSET_BYTES: usize = 20 * 1024 * 1024;
pub const DEFAULT_ASSET_TICKET_TTL: Duration = Duration::from_secs(120);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AssetBinding {
    workspace_id: String,
    principal_id: String,
}

impl AssetBinding {
    pub fn new(workspace_id: &str, principal_id: &str) -> Result<Self, &'static str> {
        if workspace_id.trim().is_empty() || principal_id.trim().is_empty() {
            return Err("asset ticket binding is invalid");
        }
        Ok(Self {
            workspace_id: workspace_id.to_string(),
            principal_id: principal_id.to_string(),
        })
    }
}

struct AssetTicketRecord {
    path: PathBuf,
    file_name: String,
    expected_size: u64,
    expected_sha256: [u8; 32],
    binding: AssetBinding,
    expires_at: Instant,
}

pub struct IssuedAssetTicket {
    pub ticket: String,
    pub file_name: String,
    pub expires_in_ms: u64,
    pub max_bytes: usize,
}

pub struct ConsumedAsset {
    pub file_name: String,
    pub bytes: Vec<u8>,
}

#[derive(Default)]
pub struct ArtifactAssetState {
    tickets: Mutex<HashMap<String, AssetTicketRecord>>,
}

impl ArtifactAssetState {
    pub async fn issue_ticket(
        &self,
        path: PathBuf,
        binding: AssetBinding,
        ttl: Duration,
    ) -> Result<IssuedAssetTicket, &'static str> {
        let mut selected_file =
            open_asset_no_follow(&path).map_err(|_| "asset selection is unavailable")?;
        let metadata = selected_file
            .metadata()
            .map_err(|_| "asset selection is unavailable")?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err("asset selection must be a regular local file");
        }
        let size = metadata.len();
        if size == 0 || size > DEFAULT_MAX_ASSET_BYTES as u64 {
            return Err("asset selection exceeds the governed size boundary");
        }
        let mut selected_bytes = Vec::with_capacity(size as usize);
        selected_file
            .read_to_end(&mut selected_bytes)
            .map_err(|_| "asset selection could not be read")?;
        if selected_bytes.len() != size as usize {
            return Err("asset selection changed while being authorized");
        }
        let expected_sha256: [u8; 32] = Sha256::digest(&selected_bytes).into();
        let canonical = fs::canonicalize(&path).map_err(|_| "asset selection is unavailable")?;
        let file_name = canonical
            .file_name()
            .and_then(|value| value.to_str())
            .filter(|value| !value.is_empty())
            .ok_or("asset filename is invalid")?
            .to_string();
        let ticket = format!("asset-ticket-{}", Uuid::new_v4());
        self.tickets.lock().await.insert(
            ticket.clone(),
            AssetTicketRecord {
                path: canonical,
                file_name: file_name.clone(),
                expected_size: size,
                expected_sha256,
                binding,
                expires_at: Instant::now() + ttl,
            },
        );
        Ok(IssuedAssetTicket {
            ticket,
            file_name,
            expires_in_ms: ttl.as_millis().min(u64::MAX as u128) as u64,
            max_bytes: DEFAULT_MAX_ASSET_BYTES,
        })
    }

    pub async fn consume(
        &self,
        ticket: &str,
        binding: &AssetBinding,
    ) -> Result<ConsumedAsset, &'static str> {
        let record = self
            .tickets
            .lock()
            .await
            .remove(ticket)
            .ok_or("asset ticket is invalid or already used")?;
        if record.binding != *binding || Instant::now() > record.expires_at {
            return Err("asset ticket is invalid or expired");
        }
        let mut file = open_asset_no_follow(&record.path)
            .map_err(|_| "selected asset is no longer available")?;
        let metadata = file
            .metadata()
            .map_err(|_| "selected asset is no longer available")?;
        if metadata.file_type().is_symlink()
            || !metadata.is_file()
            || metadata.len() != record.expected_size
            || metadata.len() > DEFAULT_MAX_ASSET_BYTES as u64
        {
            return Err("selected asset changed after authorization");
        }
        let mut bytes = Vec::with_capacity(record.expected_size as usize);
        file.read_to_end(&mut bytes)
            .map_err(|_| "selected asset could not be read")?;
        if bytes.len() != record.expected_size as usize {
            return Err("selected asset changed while being read");
        }
        if <[u8; 32]>::from(Sha256::digest(&bytes)) != record.expected_sha256 {
            return Err("selected asset changed after authorization");
        }
        Ok(ConsumedAsset {
            file_name: record.file_name,
            bytes,
        })
    }
}

fn open_asset_no_follow(path: &PathBuf) -> std::io::Result<File> {
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        const FILE_FLAG_OPEN_REPARSE_POINT: u32 = 0x0020_0000;
        options.custom_flags(FILE_FLAG_OPEN_REPARSE_POINT);
    }
    #[cfg(target_os = "macos")]
    {
        use std::os::unix::fs::OpenOptionsExt;
        const O_NOFOLLOW: i32 = 0x0000_0100;
        options.custom_flags(O_NOFOLLOW);
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        use std::os::unix::fs::OpenOptionsExt;
        const O_NOFOLLOW: i32 = 0x0002_0000;
        options.custom_flags(O_NOFOLLOW);
    }
    options.open(path)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ticket_is_principal_bound_single_use_and_path_opaque() {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime");
        runtime.block_on(async {
            let root = tempfile::tempdir().expect("tempdir");
            let path = root.path().join("image.png");
            fs::write(&path, b"safe bytes").expect("fixture");
            let state = ArtifactAssetState::default();
            let owner = AssetBinding::new("workspace-1", "user-1").expect("binding");
            let other = AssetBinding::new("workspace-1", "user-2").expect("binding");

            let denied = state
                .issue_ticket(path.clone(), owner.clone(), Duration::from_secs(60))
                .await
                .expect("ticket");
            assert!(state.consume(&denied.ticket, &other).await.is_err());

            let issued = state
                .issue_ticket(path, owner.clone(), Duration::from_secs(60))
                .await
                .expect("ticket");
            assert!(!issued
                .ticket
                .contains(root.path().to_string_lossy().as_ref()));
            assert_eq!(
                state
                    .consume(&issued.ticket, &owner)
                    .await
                    .expect("asset")
                    .bytes,
                b"safe bytes"
            );
            assert!(state.consume(&issued.ticket, &owner).await.is_err());

            let changed_path = root.path().join("changed.png");
            fs::write(&changed_path, b"first bytes").expect("fixture");
            let changed = state
                .issue_ticket(changed_path.clone(), owner.clone(), Duration::from_secs(60))
                .await
                .expect("ticket");
            fs::write(changed_path, b"other bytes").expect("replace fixture");
            assert!(state.consume(&changed.ticket, &owner).await.is_err());
        });
    }
}
use sha2::{Digest, Sha256};
