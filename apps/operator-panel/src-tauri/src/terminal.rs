use crate::bridge::ProductFolderTicketState;
use base64::{engine::general_purpose::STANDARD, Engine};
use portable_pty::{native_pty_system, CommandBuilder, PtySize};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::io::Write;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, Manager, State};

#[derive(Default)]
pub struct TerminalManager {
    sessions: Arc<Mutex<HashMap<String, TerminalSession>>>,
}

struct TerminalSession {
    writer: Box<dyn Write + Send>,
    master: Box<dyn portable_pty::MasterPty + Send>,
    killer: Box<dyn portable_pty::ChildKiller + Send + Sync>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TerminalStartRequest {
    pub mode: String,
    pub cwd: Option<String>,
    pub root_ref: Option<String>,
    pub cols: u16,
    pub rows: u16,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TerminalWriteRequest {
    pub session_id: String,
    pub data: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TerminalResizeRequest {
    pub session_id: String,
    pub cols: u16,
    pub rows: u16,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TerminalKillRequest {
    pub session_id: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TerminalStartResponse {
    pub session_id: String,
    pub shell: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct TerminalStatusEvent {
    session_id: String,
    exit_code: Option<u32>,
    signal: Option<String>,
}

fn terminal_status_event(
    session_id: &str,
    status: portable_pty::ExitStatus,
) -> TerminalStatusEvent {
    TerminalStatusEvent {
        session_id: session_id.to_owned(),
        exit_code: Some(status.exit_code()),
        signal: status.signal().map(ToOwned::to_owned),
    }
}

fn terminal_error(message: &str) -> String {
    format!("TERMINAL_DENIED: {message}")
}

fn shell_command() -> Result<CommandBuilder, String> {
    #[cfg(target_os = "windows")]
    {
        let mut command = CommandBuilder::new("powershell.exe");
        command.args(["-NoLogo", "-NoProfile"]);
        apply_terminal_environment(&mut command);
        Ok(command)
    }
    #[cfg(not(target_os = "windows"))]
    {
        let mut command = CommandBuilder::new("/bin/zsh");
        command.args(["-f"]);
        apply_terminal_environment(&mut command);
        Ok(command)
    }
}

fn apply_terminal_environment(command: &mut CommandBuilder) {
    const ALLOWED_KEYS: &[&str] = &[
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "LANG",
        "TMPDIR",
        "TEMP",
        "TMP",
        "SystemRoot",
        "windir",
        "COMSPEC",
        "PATHEXT",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "LC_ALL",
        "LC_CTYPE",
        "LC_COLLATE",
        "LC_MESSAGES",
        "LC_MONETARY",
        "LC_NUMERIC",
        "LC_TIME",
        "LC_PAPER",
        "LC_NAME",
        "LC_ADDRESS",
        "LC_TELEPHONE",
        "LC_MEASUREMENT",
        "LC_IDENTIFICATION",
    ];
    let allowed = std::env::vars_os()
        .filter(|(key, _)| {
            let key = key.to_string_lossy();
            ALLOWED_KEYS
                .iter()
                .any(|allowed| key.eq_ignore_ascii_case(allowed))
        })
        .collect::<Vec<_>>();
    command.env_clear();
    for (key, value) in allowed {
        command.env(key, value);
    }
    command.env("TERM", "xterm-256color");
    command.env("COLORTERM", "truecolor");
    command.env("TERM_PROGRAM", "ImperaOS");
}

fn reject_renderer_cwd(value: Option<&str>) -> Result<(), String> {
    if value.is_some() {
        return Err(terminal_error(
            "renderer-supplied working directories are not trusted",
        ));
    }
    Ok(())
}

fn verified_runtime_workspace_root(app: &AppHandle) -> Result<PathBuf, String> {
    let root = app
        .path()
        .app_data_dir()
        .map_err(|_| terminal_error("could not resolve terminal runtime workspace"))?
        .join("terminal-workspace");
    fs::create_dir_all(&root)
        .map_err(|_| terminal_error("could not initialize terminal runtime workspace"))?;
    Ok(root)
}

async fn terminal_root(
    app: &AppHandle,
    roots: &ProductFolderTicketState,
    root_ref: Option<&str>,
) -> Result<PathBuf, String> {
    match root_ref {
        Some(root_ref) => roots
            .resolve_registered_root_from_native_store(app, root_ref)
            .await
            .map_err(|_| terminal_error("registered project root is unavailable")),
        None => verified_runtime_workspace_root(app),
    }
}

fn interrupt_sequence() -> &'static [u8] {
    b"\x03"
}

#[tauri::command]
pub async fn terminal_start(
    app: AppHandle,
    state: State<'_, TerminalManager>,
    roots: State<'_, ProductFolderTicketState>,
    request: TerminalStartRequest,
) -> Result<TerminalStartResponse, String> {
    if request.mode != "user" {
        return Err(terminal_error(
            "only user-started terminal sessions are enabled",
        ));
    }
    if request.cols == 0 || request.rows == 0 || request.cols > 500 || request.rows > 300 {
        return Err(terminal_error("terminal dimensions are outside policy"));
    }
    reject_renderer_cwd(request.cwd.as_deref())?;
    let mut command = shell_command()?;
    command.cwd(terminal_root(&app, roots.inner(), request.root_ref.as_deref()).await?);
    let pair = native_pty_system()
        .openpty(PtySize {
            rows: request.rows,
            cols: request.cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|_| terminal_error("could not allocate PTY"))?;
    let mut child = pair
        .slave
        .spawn_command(command)
        .map_err(|_| terminal_error("could not start terminal shell"))?;
    let killer = child.clone_killer();
    let reader = pair
        .master
        .try_clone_reader()
        .map_err(|_| terminal_error("could not read PTY"))?;
    let writer = pair
        .master
        .take_writer()
        .map_err(|_| terminal_error("could not write PTY"))?;
    let session_id = format!("terminal-{}", uuid::Uuid::new_v4());
    state
        .sessions
        .lock()
        .map_err(|_| terminal_error("terminal manager unavailable"))?
        .insert(
            session_id.clone(),
            TerminalSession {
                writer,
                master: pair.master,
                killer,
            },
        );
    let output_app = app.clone();
    let output_session_id = session_id.clone();
    std::thread::spawn(move || {
        use std::io::Read;
        let mut reader = reader;
        let mut buffer = [0_u8; 4096];
        while let Ok(count) = reader.read(&mut buffer) {
            if count == 0 {
                break;
            }
            let _ = output_app.emit("terminal://output", serde_json::json!({"sessionId": output_session_id, "data": STANDARD.encode(&buffer[..count])}));
        }
    });
    let status_app = app;
    let status_session_id = session_id.clone();
    let sessions = Arc::clone(&state.sessions);
    std::thread::spawn(move || {
        if let Ok(status) = child.wait() {
            let _ = status_app.emit(
                "terminal://status",
                terminal_status_event(&status_session_id, status),
            );
        }
        if let Ok(mut sessions) = sessions.lock() {
            sessions.remove(&status_session_id);
        }
    });
    Ok(TerminalStartResponse {
        session_id,
        shell: if cfg!(windows) {
            "powershell.exe".into()
        } else {
            "/bin/zsh".into()
        },
    })
}

#[tauri::command]
pub fn terminal_write(
    state: State<'_, TerminalManager>,
    request: TerminalWriteRequest,
) -> Result<(), String> {
    let mut sessions = state
        .sessions
        .lock()
        .map_err(|_| terminal_error("terminal manager unavailable"))?;
    let session = sessions
        .get_mut(&request.session_id)
        .ok_or_else(|| terminal_error("unknown terminal session"))?;
    session
        .writer
        .write_all(request.data.as_bytes())
        .map_err(|_| terminal_error("terminal write failed"))
}

#[tauri::command]
pub fn terminal_resize(
    state: State<'_, TerminalManager>,
    request: TerminalResizeRequest,
) -> Result<(), String> {
    if request.cols == 0 || request.rows == 0 || request.cols > 500 || request.rows > 300 {
        return Err(terminal_error("terminal dimensions are outside policy"));
    }
    let sessions = state
        .sessions
        .lock()
        .map_err(|_| terminal_error("terminal manager unavailable"))?;
    let session = sessions
        .get(&request.session_id)
        .ok_or_else(|| terminal_error("unknown terminal session"))?;
    session
        .master
        .resize(PtySize {
            rows: request.rows,
            cols: request.cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|_| terminal_error("terminal resize failed"))
}

#[tauri::command]
pub fn terminal_interrupt(
    state: State<'_, TerminalManager>,
    request: TerminalKillRequest,
) -> Result<(), String> {
    let mut sessions = state
        .sessions
        .lock()
        .map_err(|_| terminal_error("terminal manager unavailable"))?;
    let session = sessions
        .get_mut(&request.session_id)
        .ok_or_else(|| terminal_error("unknown terminal session"))?;
    session
        .writer
        .write_all(interrupt_sequence())
        .map_err(|_| terminal_error("terminal interrupt failed"))
}

#[tauri::command]
pub fn terminal_kill(
    state: State<'_, TerminalManager>,
    request: TerminalKillRequest,
) -> Result<(), String> {
    let mut sessions = state
        .sessions
        .lock()
        .map_err(|_| terminal_error("terminal manager unavailable"))?;
    let mut session = sessions
        .remove(&request.session_id)
        .ok_or_else(|| terminal_error("unknown terminal session"))?;
    session
        .killer
        .kill()
        .map_err(|_| terminal_error("terminal kill failed"))
}

#[cfg(test)]
mod tests {
    use super::{interrupt_sequence, reject_renderer_cwd, shell_command, terminal_status_event};

    #[test]
    fn renderer_cwd_is_never_a_terminal_authority() {
        assert!(reject_renderer_cwd(Some("/tmp/untrusted")).is_err());
        assert!(reject_renderer_cwd(None).is_ok());
    }

    #[test]
    fn interrupt_uses_only_the_terminal_control_sequence() {
        assert_eq!(interrupt_sequence(), b"\x03");
    }

    #[test]
    fn terminal_shell_does_not_inherit_arbitrary_host_secrets() {
        let secret_key = "IMPERAOS_TERMINAL_TEST_SECRET";
        let locale_prefixed_secret_key = "LC_API_TOKEN";
        std::env::set_var(secret_key, "must-not-cross-pty-boundary");
        std::env::set_var(locale_prefixed_secret_key, "must-not-cross-pty-boundary");
        let command = shell_command().expect("terminal command");
        std::env::remove_var(secret_key);
        std::env::remove_var(locale_prefixed_secret_key);

        assert!(command.get_env(secret_key).is_none());
        assert!(command.get_env(locale_prefixed_secret_key).is_none());
        assert!(command.get_env("PATH").is_some());
    }

    #[test]
    fn terminal_exit_status_preserves_the_native_exit_code() {
        let event =
            terminal_status_event("terminal-test", portable_pty::ExitStatus::with_exit_code(7));

        assert_eq!(event.session_id, "terminal-test");
        assert_eq!(event.exit_code, Some(7));
        assert_eq!(event.signal, None);
    }

    #[test]
    fn native_pty_executes_an_interactive_shell_command_end_to_end() {
        use portable_pty::{native_pty_system, PtySize};
        use std::io::{Read, Write};
        use std::sync::mpsc;
        use std::time::Duration;

        let pair = native_pty_system()
            .openpty(PtySize {
                rows: 24,
                cols: 80,
                pixel_width: 0,
                pixel_height: 0,
            })
            .expect("test PTY");
        let mut child = pair
            .slave
            .spawn_command(shell_command().expect("terminal shell"))
            .expect("spawn terminal shell");
        let mut reader = pair.master.try_clone_reader().expect("PTY reader");
        let mut writer = pair.master.take_writer().expect("PTY writer");
        let (send, receive) = mpsc::channel();
        std::thread::spawn(move || {
            let mut output = Vec::new();
            let _ = reader.read_to_end(&mut output);
            let _ = send.send(output);
        });
        #[cfg(target_os = "windows")]
        let command = "Write-Output '__IMPERAOS_PTY_OK__'; exit\r\n";
        #[cfg(not(target_os = "windows"))]
        let command = "printf '__IMPERAOS_PTY_OK__\\n'; exit\n";
        writer
            .write_all(command.as_bytes())
            .expect("write test command");
        writer.flush().expect("flush test command");
        let status = child.wait().expect("terminal shell exit");
        drop(writer);
        let output = receive
            .recv_timeout(Duration::from_secs(5))
            .expect("PTY output before timeout");

        assert!(status.success());
        assert!(String::from_utf8_lossy(&output).contains("__IMPERAOS_PTY_OK__"));
    }
}
