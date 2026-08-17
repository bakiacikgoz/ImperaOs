from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from imperaos.computer_use.adapters._macos import applescript_quote, run_applescript
from imperaos.computer_use.adapters.desktop_adapter import DesktopAdapter
from imperaos.computer_use.adapters.dialog_adapter import FileDialogAdapter
from imperaos.computer_use.models import SurfaceObservation


class TextEditAdapter:
    def __init__(
        self,
        *,
        desktop_adapter: DesktopAdapter | None = None,
        dialog_adapter: FileDialogAdapter,
        app_name: str = "TextEdit",
        wait_timeout_s: float = 10.0,
    ) -> None:
        self._desktop = desktop_adapter or DesktopAdapter()
        self._dialog = dialog_adapter
        self._app_name = app_name
        self._wait_timeout_s = wait_timeout_s
        self._last_document_path: str | None = None
        self._last_document_text: str | None = None

    def open_file(self, path: str | Path) -> str:
        resolved = self._dialog.ensure_scoped_path(path)
        if not resolved.exists():
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text("", encoding="utf-8")
        subprocess.run(
            ["open", "-a", self._app_name, str(resolved)],
            check=True,
            capture_output=True,
            text=True,
        )
        self._desktop.focus_window(self._app_name)
        self._last_document_path = str(resolved)
        self._last_document_text = resolved.read_text(encoding="utf-8")
        return self._last_document_path

    def append_text(self, *, text: str, path: str | Path | None = None) -> str:
        if path is not None:
            self.open_file(path)
        if self._last_document_text is None and self._last_document_path is not None:
            cached_path = Path(self._last_document_path)
            if cached_path.exists():
                self._last_document_text = cached_path.read_text(encoding="utf-8")
        script = f"""
tell application {applescript_quote(self._app_name)}
  activate
end tell
delay 0.2
tell application "System Events"
  keystroke {applescript_quote(text)}
end tell
"""
        run_applescript(script, timeout_s=self._wait_timeout_s)
        self._last_document_text = (self._last_document_text or "") + text
        return self._last_document_path or ""

    def save_document(self, *, path: str | Path | None = None) -> str:
        if path is not None:
            resolved = self._dialog.ensure_scoped_path(path)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            script = f"""
tell application {applescript_quote(self._app_name)}
  activate
  if (count of documents) = 0 then open POSIX file {applescript_quote(str(resolved))}
  save front document in POSIX file {applescript_quote(str(resolved))}
  return POSIX path of (path of front document)
end tell
"""
            try:
                saved = run_applescript(script, timeout_s=self._wait_timeout_s)
            except (subprocess.TimeoutExpired, RuntimeError):
                if self._last_document_text is not None:
                    resolved.write_text(self._last_document_text, encoding="utf-8")
                saved = str(resolved)
            self._last_document_path = saved or str(resolved)
            if resolved.exists():
                self._last_document_text = resolved.read_text(encoding="utf-8")
            return self._last_document_path
        script = f"""
tell application {applescript_quote(self._app_name)}
  activate
  if (count of documents) = 0 then error "no_open_document"
  save front document
  try
    return POSIX path of (path of front document)
  on error
    return ""
  end try
end tell
"""
        try:
            saved = run_applescript(script, timeout_s=self._wait_timeout_s)
        except (subprocess.TimeoutExpired, RuntimeError):
            saved = self._last_document_path or ""
            if saved and self._last_document_text is not None:
                Path(saved).write_text(self._last_document_text, encoding="utf-8")
        if saved:
            self._last_document_path = saved
        if self._last_document_path is not None:
            candidate = Path(self._last_document_path)
            if candidate.exists():
                self._last_document_text = candidate.read_text(encoding="utf-8")
        return self._last_document_path or saved or ""

    def current_document_path(self) -> str | None:
        if self._last_document_path:
            return self._last_document_path
        script = f"""
tell application "System Events"
  if not (exists process {applescript_quote(self._app_name)}) then
    return ""
  end if
end tell
tell application {applescript_quote(self._app_name)}
  if (count of documents) = 0 then
    return ""
  end if
  try
    return POSIX path of (path of front document)
  on error
    return ""
  end try
end tell
"""
        raw = run_applescript(script, timeout_s=self._wait_timeout_s)
        return raw or None

    def current_document_text(self) -> str:
        if self._last_document_text is not None:
            return self._last_document_text
        if self._last_document_path:
            candidate = Path(self._last_document_path)
            if candidate.exists():
                self._last_document_text = candidate.read_text(encoding="utf-8")
                return self._last_document_text
        script = f"""
tell application "System Events"
  if not (exists process {applescript_quote(self._app_name)}) then
    return ""
  end if
end tell
tell application {applescript_quote(self._app_name)}
  if (count of documents) = 0 then
    return ""
  end if
  return text of front document
end tell
"""
        return run_applescript(script, timeout_s=self._wait_timeout_s)

    def observe_surface(self) -> SurfaceObservation:
        desktop_surface = self._desktop.observe_surface(self._app_name)
        if desktop_surface.foreground_app != self._app_name:
            return SurfaceObservation(
                foreground_app=desktop_surface.foreground_app,
                bundle_id=desktop_surface.bundle_id,
                focused_window_title=desktop_surface.focused_window_title,
                active_tab_url=None,
                active_tab_title=None,
                selected_paths=None,
                active_document_path=None,
                clipboard_text=None,
                modal_detected=desktop_surface.modal_detected,
                visible_selectors=None,
                captured_at=datetime.now(UTC).isoformat(),
            )
        return SurfaceObservation(
            foreground_app=desktop_surface.foreground_app,
            bundle_id=desktop_surface.bundle_id,
            focused_window_title=desktop_surface.focused_window_title,
            active_tab_url=None,
            active_tab_title=None,
            selected_paths=None,
            active_document_path=self.current_document_path(),
            clipboard_text=None,
            modal_detected=desktop_surface.modal_detected,
            visible_selectors=None,
            captured_at=datetime.now(UTC).isoformat(),
        )
