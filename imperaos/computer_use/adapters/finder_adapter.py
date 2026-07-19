from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from imperaos.computer_use.adapters._macos import run_applescript
from imperaos.computer_use.adapters.desktop_adapter import DesktopAdapter
from imperaos.computer_use.adapters.dialog_adapter import FileDialogAdapter
from imperaos.computer_use.models import SurfaceObservation


class FinderAdapter:
    def __init__(
        self,
        *,
        desktop_adapter: DesktopAdapter | None = None,
        dialog_adapter: FileDialogAdapter,
        app_name: str = "Finder",
    ) -> None:
        self._desktop = desktop_adapter or DesktopAdapter()
        self._dialog = dialog_adapter
        self._app_name = app_name

    def reveal_path(self, path: str | Path) -> str:
        resolved = self._dialog.verify_file_exists(path)
        subprocess.run(
            ["open", "-R", resolved],
            check=True,
            capture_output=True,
            text=True,
        )
        self._desktop.focus_window(self._app_name)
        return resolved

    def rename_path(self, *, path: str | Path, new_name: str) -> str:
        source = Path(self._dialog.verify_file_exists(path))
        destination = self._dialog.ensure_scoped_path(source.with_name(new_name))
        source.rename(destination)
        self.reveal_path(destination)
        return str(destination)

    def move_path(self, *, source: str | Path, destination: str | Path) -> str:
        source_path = Path(self._dialog.verify_file_exists(source))
        destination_path = self._dialog.ensure_scoped_path(destination)
        if destination_path.exists() and destination_path.is_dir():
            destination_path = self._dialog.ensure_scoped_path(destination_path / source_path.name)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(destination_path))
        self.reveal_path(destination_path)
        return str(destination_path)

    def selected_paths(self) -> list[str]:
        script = """
tell application "Finder"
  activate
  set selectedPaths to {}
  repeat with itemRef in (get selection)
    set end of selectedPaths to POSIX path of (itemRef as alias)
  end repeat
  return selectedPaths as string
end tell
"""
        raw = run_applescript(script, timeout_s=8.0)
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    def current_folder(self) -> str | None:
        script = """
tell application "Finder"
  if (count of Finder windows) = 0 then
    return ""
  end if
  return POSIX path of (target of front Finder window as alias)
end tell
"""
        raw = run_applescript(script, timeout_s=8.0)
        return raw or None

    def observe_surface(self) -> SurfaceObservation:
        desktop_surface = self._desktop.observe_surface(self._app_name)
        return SurfaceObservation(
            foreground_app=desktop_surface.foreground_app,
            bundle_id=desktop_surface.bundle_id,
            focused_window_title=desktop_surface.focused_window_title,
            active_tab_url=None,
            active_tab_title=None,
            selected_paths=self.selected_paths(),
            active_document_path=self.current_folder(),
            clipboard_text=None,
            modal_detected=desktop_surface.modal_detected,
            visible_selectors=None,
            captured_at=datetime.now(UTC).isoformat(),
        )
