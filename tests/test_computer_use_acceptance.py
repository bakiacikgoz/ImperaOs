from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from imperaos.computer_use import ComputerUseMode, ComputerUseRunner, SessionCommand
from imperaos.runtime.config import RuntimeConfig

REAL_COMPUTER_USE_ENABLED = os.getenv("IMPERAOS_ENABLE_REAL_COMPUTER_USE_TESTS") == "1"


def _real_computer_use_skip_reason() -> str | None:
    if sys.platform != "darwin" or not REAL_COMPUTER_USE_ENABLED:
        return (
            "Enable with IMPERAOS_ENABLE_REAL_COMPUTER_USE_TESTS=1 on macOS "
            "with Safari automation permissions."
        )
    try:
        subprocess.run(
            ["open", "-a", "Safari", "about:blank"],
            check=True,
            capture_output=True,
            text=True,
        )
        time.sleep(0.5)
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "Safari" to do JavaScript "document.readyState" '
                "in current tab of front window",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        message = ""
        if isinstance(exc, subprocess.CalledProcessError):
            message = exc.stderr.strip() or exc.stdout.strip()
        if "Allow JavaScript from Apple Events" in message:
            return (
                "Safari Developer setting 'Allow JavaScript from Apple Events' must "
                "be enabled for real computer-use acceptance tests."
            )
        return f"Real Safari acceptance preflight failed: {message or exc}"
    return None


REAL_COMPUTER_USE_SKIP_REASON = _real_computer_use_skip_reason()


def _real_local_computer_use_skip_reason() -> str | None:
    if sys.platform != "darwin" or not REAL_COMPUTER_USE_ENABLED:
        return (
            "Enable with IMPERAOS_ENABLE_REAL_COMPUTER_USE_TESTS=1 on macOS "
            "with AppleScript automation permissions."
        )
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "TextEdit" to return name',
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        message = ""
        if isinstance(exc, subprocess.CalledProcessError):
            message = exc.stderr.strip() or exc.stdout.strip()
        return f"Real local acceptance preflight failed: {message or exc}"
    return None


REAL_LOCAL_COMPUTER_USE_SKIP_REASON = _real_local_computer_use_skip_reason()


def _reset_real_safari() -> None:
    if sys.platform != "darwin":
        return
    subprocess.run(
        ["open", "-a", "Safari"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "Safari" to activate',
            "-e",
            'tell application "System Events"',
            "-e",
            '  tell process "Safari"',
            "-e",
            '    repeat while (count of windows) > 0',
            "-e",
            '      keystroke "w" using {command down}',
            "-e",
            "      delay 0.2",
            "-e",
            "    end repeat",
            "-e",
            "  end tell",
            "-e",
            "end tell",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _wait_for_event_count(
    events_path: Path,
    *,
    event_name: str,
    count: int,
    timeout_s: float = 20.0,
) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if events_path.exists():
            names = [
                json.loads(line)["event"]
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if sum(name == event_name for name in names) >= count:
                return
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {count} {event_name!r} events")


def _wait_for_session_state(
    status_path: Path,
    *,
    session_state: str,
    timeout_s: float = 20.0,
) -> dict[str, object]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if status_path.exists():
            payload = json.loads(status_path.read_text(encoding="utf-8"))
            if payload["computer_use"]["session_state"] == session_state:
                return payload
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for session_state={session_state!r}")


def _write_upload_download_site(site_dir: Path) -> None:
    (site_dir / "artifact.txt").write_text("runtime acceptance download", encoding="utf-8")
    (site_dir / "index.html").write_text(
        """
<!doctype html>
<html lang="en">
  <body>
    <form>
      <label for="name">Name</label>
      <input id="name" type="text" />
      <label for="role">Role</label>
      <select id="role">
        <option value="">Pick one</option>
        <option value="operator">operator</option>
      </select>
      <label for="upload">Upload</label>
      <input id="upload" type="file" />
    </form>
    <a id="download" href="/artifact.txt" download="artifact.txt">Download artifact</a>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )


def _start_site_server(site_dir: Path) -> tuple[ThreadingHTTPServer, threading.Thread]:
    handler = partial(SimpleHTTPRequestHandler, directory=str(site_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _start_auth_site_server() -> tuple[ThreadingHTTPServer, threading.Thread]:
    session_cookie = "imperaos_session=pilot"

    class _AuthSiteHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003
            del format, args

        def _is_authenticated(self) -> bool:
            return session_cookie in self.headers.get("Cookie", "")

        def _redirect(self, location: str, *, cookie: str | None = None) -> None:
            self.send_response(303)
            self.send_header("Location", location)
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()

        def _write_html(self, body: str, *, status: int = 200) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in {"/", "/entry", "/entry.html"}:
                self._write_html(
                    """
<!doctype html>
<html lang="en">
  <body>
    <p id="entry">Bootstrap an authenticated session for the protected fixture.</p>
    <a id="enter" href="/session/bootstrap">Enter protected workspace</a>
  </body>
</html>
""".strip()
                )
                return
            if path in {"/", "/login", "/login.html"}:
                self._write_html(
                    """
<!doctype html>
<html lang="en">
  <body>
    <form id="login-form" action="/session/login" method="post">
      <label for="username">Username</label>
      <input id="username" name="username" type="text" />
      <button id="login" type="submit">Sign in</button>
    </form>
  </body>
</html>
""".strip()
                )
                return
            if path == "/session/bootstrap":
                self._redirect(
                    "/protected/index.html",
                    cookie=f"{session_cookie}; Path=/",
                )
                return
            if path in {"/protected", "/protected/index.html"}:
                if not self._is_authenticated():
                    self._redirect("/login.html")
                    return
                self._write_html(
                    """
<!doctype html>
<html lang="en">
  <body>
    <p id="welcome">Authenticated session active.</p>
    <form id="protected-form" action="/protected/submit" method="post">
      <label for="notes">Notes</label>
      <input id="notes" name="notes" type="text" />
      <button id="submit" type="submit">Submit</button>
    </form>
    <a
      id="download"
      href="/protected/artifact.txt"
      download="protected-artifact.txt"
    >
      Download protected artifact
    </a>
  </body>
</html>
""".strip()
                )
                return
            if path == "/protected/success.html":
                if not self._is_authenticated():
                    self._redirect("/login.html")
                    return
                self._write_html(
                    """
<!doctype html>
<html lang="en">
  <body>
    <p id="success">Protected form submitted successfully.</p>
  </body>
</html>
""".strip()
                )
                return
            if path == "/protected/artifact.txt":
                if not self._is_authenticated():
                    self._redirect("/login.html")
                    return
                content = b"authenticated download artifact"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            content_length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(content_length).decode("utf-8")
            parsed = parse_qs(body)
            if path == "/session/login":
                username = parsed.get("username", [""])[0]
                if username:
                    self._redirect(
                        "/protected/index.html",
                        cookie=f"{session_cookie}; Path=/",
                    )
                    return
                self._write_html("missing username", status=400)
                return
            if path == "/protected/submit":
                if not self._is_authenticated():
                    self._redirect("/login.html")
                    return
                note = parsed.get("notes", [""])[0]
                if note:
                    self._redirect("/protected/success.html")
                    return
                self._write_html("missing note", status=400)
                return
            self.send_response(404)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), _AuthSiteHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


@pytest.mark.skipif(
    REAL_LOCAL_COMPUTER_USE_SKIP_REASON is not None,
    reason=REAL_LOCAL_COMPUTER_USE_SKIP_REASON or "",
)
def test_real_textedit_local_edit_acceptance(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    root_dir.mkdir()
    document_path = root_dir / "local-note.txt"
    document_path.write_text("pilot", encoding="utf-8")

    config = RuntimeConfig.from_profile("default")
    runner = ComputerUseRunner(config=config, root_dir=root_dir)
    payload = runner.run(
        prompt="\n".join(
            [
                f'textedit_open "{document_path}"',
                'textedit_append " local review"',
                f'textedit_save "{document_path}"',
            ]
        ),
        job_id="real-textedit-local-acceptance",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "completed"
    assert document_path.read_text(encoding="utf-8") == "pilot local review"
    status_payload = json.loads(
        (root_dir / "real-textedit-local-acceptance" / "status.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        status_payload["computer_use"]["world_model"]["active_document_path"]
        == str(document_path)
    )


@pytest.mark.skipif(
    REAL_COMPUTER_USE_SKIP_REASON is not None,
    reason=REAL_COMPUTER_USE_SKIP_REASON or "",
)
def test_real_safari_upload_acceptance(tmp_path: Path) -> None:
    _reset_real_safari()
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    root_dir = tmp_path / "jobs"
    root_dir.mkdir()
    upload_path = root_dir / "upload.txt"
    upload_path.write_text("runtime acceptance upload", encoding="utf-8")
    _write_upload_download_site(site_dir)
    server, thread = _start_site_server(site_dir)

    try:
        config = RuntimeConfig.from_profile("default")
        runner = ComputerUseRunner(config=config, root_dir=root_dir)
        payload = runner.run(
            prompt="\n".join(
                [
                    'launch "Safari"',
                    f'open "http://127.0.0.1:{server.server_port}/index.html"',
                    'type "ImperaOS Operator" into "#name"',
                    'select "operator" in "#role"',
                    f'upload "{upload_path}" to "#upload"',
                ]
            ),
            job_id="real-safari-upload-acceptance",
            mode=ComputerUseMode.EXECUTE,
        )

        assert payload["job"]["status"] == "completed"
        status_payload = json.loads(
            (root_dir / "real-safari-upload-acceptance" / "status.json").read_text(
                encoding="utf-8"
            )
        )
        assert (
            status_payload["computer_use"]["last_verification_result"]["expected_file_operation"][
                "operation"
            ]
            == "upload"
        )
        assert (
            status_payload["computer_use"]["artifacts"]["upload_file"]["selected_file"]
            == str(upload_path)
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


@pytest.mark.skipif(
    REAL_COMPUTER_USE_SKIP_REASON is not None,
    reason=REAL_COMPUTER_USE_SKIP_REASON or "",
)
def test_real_safari_surface_drift_acceptance(tmp_path: Path) -> None:
    _reset_real_safari()
    site_dir = tmp_path / "surface-site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text(
        """
<!doctype html>
<html lang="en">
  <body>
    <label for="name">Name</label>
    <input id="name" type="text" />
    <label for="notes">Notes</label>
    <input id="notes" type="text" />
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )
    (site_dir / "other.html").write_text(
        """
<!doctype html>
<html lang="en">
  <body>
    <p>Drifted away from the expected surface.</p>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    handler = partial(SimpleHTTPRequestHandler, directory=str(site_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        config = RuntimeConfig.from_profile("default")
        root_dir = tmp_path / "jobs"
        runner = ComputerUseRunner(config=config, root_dir=root_dir)
        outcome: dict[str, object] = {}
        job_id = "real-safari-surface-drift"

        def worker() -> None:
            try:
                outcome["payload"] = runner.run(
                    prompt="\n".join(
                        [
                            f'open "http://127.0.0.1:{server.server_port}/index.html"',
                            'type "ImperaOS Operator" into "#name"',
                            'wait "2.0"',
                            'type "This step should fail after drift" into "#notes"',
                        ]
                    ),
                    job_id=job_id,
                    mode=ComputerUseMode.EXECUTE,
                )
            except Exception as exc:  # noqa: BLE001
                outcome["error"] = exc

        worker_thread = threading.Thread(target=worker, daemon=True)
        worker_thread.start()

        events_path = root_dir / job_id / "events.jsonl"
        _wait_for_event_count(events_path, event_name="action_verified", count=2)
        drift_url = f"http://127.0.0.1:{server.server_port}/other.html"
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "Safari" to set URL of current tab of front window '
                f'to "{drift_url}"',
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        worker_thread.join(timeout=30.0)
        assert not worker_thread.is_alive()
        assert "error" not in outcome
        payload = outcome["payload"]
        assert isinstance(payload, dict)
        assert payload["job"]["status"] == "failed"

        status_payload = json.loads(
            (root_dir / job_id / "status.json").read_text(encoding="utf-8")
        )
        assert status_payload["computer_use"]["surface_mismatch"]["code"] == "wrong_tab"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


@pytest.mark.skipif(
    REAL_COMPUTER_USE_SKIP_REASON is not None,
    reason=REAL_COMPUTER_USE_SKIP_REASON or "",
)
def test_real_safari_download_acceptance(tmp_path: Path) -> None:
    _reset_real_safari()
    site_dir = tmp_path / "download-site"
    site_dir.mkdir()
    root_dir = tmp_path / "jobs"
    root_dir.mkdir()
    download_target = root_dir / "downloaded-artifact.txt"
    _write_upload_download_site(site_dir)
    server, thread = _start_site_server(site_dir)

    try:
        config = RuntimeConfig.from_profile("default")
        runner = ComputerUseRunner(config=config, root_dir=root_dir)
        payload = runner.run(
            prompt="\n".join(
                [
                    'launch "Safari"',
                    f'open "http://127.0.0.1:{server.server_port}/index.html"',
                    f'download "#download" to "{download_target}"',
                ]
            ),
            job_id="real-safari-download-acceptance",
            mode=ComputerUseMode.EXECUTE,
        )

        assert payload["job"]["status"] == "completed"
        assert download_target.exists()
        assert download_target.read_text(encoding="utf-8") == "runtime acceptance download"
        status_payload = json.loads(
            (root_dir / "real-safari-download-acceptance" / "status.json").read_text(
                encoding="utf-8"
            )
        )
        assert (
            status_payload["computer_use"]["last_verification_result"]["expected_file_operation"][
                "operation"
            ]
            == "download"
        )
        assert (
            status_payload["computer_use"]["artifacts"]["download_file"]["download_path"]
            == str(download_target)
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


@pytest.mark.skipif(
    REAL_COMPUTER_USE_SKIP_REASON is not None,
    reason=REAL_COMPUTER_USE_SKIP_REASON or "",
)
def test_real_safari_authenticated_navigation_acceptance(tmp_path: Path) -> None:
    _reset_real_safari()
    root_dir = tmp_path / "jobs"
    root_dir.mkdir()
    server, thread = _start_auth_site_server()

    try:
        config = RuntimeConfig.from_profile("default")
        runner = ComputerUseRunner(config=config, root_dir=root_dir)
        payload = runner.run(
            prompt="\n".join(
                [
                    'launch "Safari"',
                    f'open "http://127.0.0.1:{server.server_port}/entry.html"',
                    'click "#enter"',
                    'wait "0.5"',
                    'type "Authenticated note" into "#notes"',
                ]
            ),
            job_id="real-safari-auth-navigation",
            mode=ComputerUseMode.EXECUTE,
        )

        assert payload["job"]["status"] == "completed"
        status_payload = json.loads(
            (root_dir / "real-safari-auth-navigation" / "status.json").read_text(
                encoding="utf-8"
            )
        )
        assert (
            status_payload["computer_use"]["current_url"]
            == f"http://127.0.0.1:{server.server_port}/protected/index.html"
        )
        assert status_payload["computer_use"]["last_verification_result"]["verified"] is True
        assert status_payload["computer_use"]["surface_mismatch"] is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


@pytest.mark.skipif(
    REAL_COMPUTER_USE_SKIP_REASON is not None,
    reason=REAL_COMPUTER_USE_SKIP_REASON or "",
)
def test_real_safari_authenticated_download_acceptance(tmp_path: Path) -> None:
    _reset_real_safari()
    root_dir = tmp_path / "jobs"
    root_dir.mkdir()
    download_target = root_dir / "protected-artifact.txt"
    server, thread = _start_auth_site_server()

    try:
        config = RuntimeConfig.from_profile("default")
        runner = ComputerUseRunner(config=config, root_dir=root_dir)
        payload = runner.run(
            prompt="\n".join(
                [
                    'launch "Safari"',
                    f'open "http://127.0.0.1:{server.server_port}/entry.html"',
                    'click "#enter"',
                    'wait "0.5"',
                    f'download "#download" to "{download_target}"',
                ]
            ),
            job_id="real-safari-auth-download",
            mode=ComputerUseMode.EXECUTE,
        )

        assert payload["job"]["status"] == "completed"
        assert download_target.exists()
        assert download_target.read_text(encoding="utf-8") == "authenticated download artifact"
        status_payload = json.loads(
            (root_dir / "real-safari-auth-download" / "status.json").read_text(
                encoding="utf-8"
            )
        )
        verification = status_payload["computer_use"]["last_verification_result"]
        assert verification["expected_file_operation"]["operation"] == "download"
        assert verification["file_operation_mismatch"] is None
        assert (
            status_payload["computer_use"]["artifacts"]["download_file"]["download_path"]
            == str(download_target)
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


@pytest.mark.skipif(
    REAL_COMPUTER_USE_SKIP_REASON is not None,
    reason=REAL_COMPUTER_USE_SKIP_REASON or "",
)
def test_real_safari_pause_resume_acceptance(tmp_path: Path) -> None:
    _reset_real_safari()
    site_dir = tmp_path / "pause-site"
    site_dir.mkdir()
    root_dir = tmp_path / "jobs"
    root_dir.mkdir()
    _write_upload_download_site(site_dir)
    server, server_thread = _start_site_server(site_dir)

    try:
        config = RuntimeConfig.from_profile("default")
        runner = ComputerUseRunner(config=config, root_dir=root_dir)
        outcome: dict[str, object] = {}
        job_id = "real-safari-pause-resume"

        def worker() -> None:
            try:
                outcome["payload"] = runner.run(
                    prompt="\n".join(
                        [
                            'launch "Safari"',
                            f'open "http://127.0.0.1:{server.server_port}/index.html"',
                            'type "ImperaOS Operator" into "#name"',
                            'wait "2.0"',
                            'type "Recovered after pause" into "#name"',
                        ]
                    ),
                    job_id=job_id,
                    mode=ComputerUseMode.EXECUTE,
                )
            except Exception as exc:  # noqa: BLE001
                outcome["error"] = exc

        worker_thread = threading.Thread(target=worker, daemon=True)
        worker_thread.start()

        events_path = root_dir / job_id / "events.jsonl"
        status_path = root_dir / job_id / "status.json"
        _wait_for_event_count(events_path, event_name="action_verified", count=2)
        control_runner = ComputerUseRunner(config=config, root_dir=root_dir)
        control_runner.request_control(job_id=job_id, command=SessionCommand.PAUSE)
        paused_payload = _wait_for_session_state(status_path, session_state="paused")
        assert paused_payload["computer_use"]["last_safe_checkpoint"] in {
            "before_action",
            "after_execute",
            "after_verify",
        }
        assert paused_payload["computer_use"]["last_control_result"]["command_type"] == "pause"
        assert paused_payload["computer_use"]["last_control_result"]["resulting_state"] == "paused"

        control_runner.request_control(job_id=job_id, command=SessionCommand.RESUME)
        worker_thread.join(timeout=30.0)
        assert not worker_thread.is_alive()
        assert "error" not in outcome
        payload = outcome["payload"]
        assert isinstance(payload, dict)
        assert payload["job"]["status"] == "completed"
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5.0)


@pytest.mark.skipif(
    REAL_COMPUTER_USE_SKIP_REASON is not None,
    reason=REAL_COMPUTER_USE_SKIP_REASON or "",
)
def test_real_safari_stop_acceptance(tmp_path: Path) -> None:
    _reset_real_safari()
    site_dir = tmp_path / "stop-site"
    site_dir.mkdir()
    root_dir = tmp_path / "jobs"
    root_dir.mkdir()
    _write_upload_download_site(site_dir)
    server, server_thread = _start_site_server(site_dir)

    try:
        config = RuntimeConfig.from_profile("default")
        runner = ComputerUseRunner(config=config, root_dir=root_dir)
        outcome: dict[str, object] = {}
        job_id = "real-safari-stop"

        def worker() -> None:
            try:
                outcome["payload"] = runner.run(
                    prompt="\n".join(
                        [
                            'launch "Safari"',
                            f'open "http://127.0.0.1:{server.server_port}/index.html"',
                            'wait "3.0"',
                            'type "This step should not execute" into "#name"',
                        ]
                    ),
                    job_id=job_id,
                    mode=ComputerUseMode.EXECUTE,
                )
            except Exception as exc:  # noqa: BLE001
                outcome["error"] = exc

        worker_thread = threading.Thread(target=worker, daemon=True)
        worker_thread.start()

        events_path = root_dir / job_id / "events.jsonl"
        status_path = root_dir / job_id / "status.json"
        _wait_for_event_count(events_path, event_name="action_started", count=2)
        control_runner = ComputerUseRunner(config=config, root_dir=root_dir)
        control_runner.request_control(job_id=job_id, command=SessionCommand.STOP)
        worker_thread.join(timeout=30.0)
        assert not worker_thread.is_alive()
        assert "error" in outcome
        stopped_payload = _wait_for_session_state(status_path, session_state="stopped")
        assert stopped_payload["computer_use"]["stopped_by_user"] is True
        assert stopped_payload["computer_use"]["last_control_result"]["command_type"] == "stop"
        assert (
            stopped_payload["computer_use"]["last_control_result"]["resulting_state"]
            == "stopped"
        )
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5.0)
