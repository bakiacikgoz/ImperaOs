from __future__ import annotations

import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from imperaos.computer_use.adapters._macos import applescript_quote, run_applescript
from imperaos.computer_use.models import FileOperationObservation


class FileDialogAdapter:
    def __init__(self, *, allowed_roots: list[str | Path]) -> None:
        self._allowed_roots = [Path(root).expanduser().resolve() for root in allowed_roots]

    def allowed_roots(self) -> list[str]:
        return [str(root) for root in self._allowed_roots]

    def normalize_path(self, path: str | Path) -> Path:
        return Path(path).expanduser().resolve()

    def is_within_allowed_roots(self, path: str | Path) -> bool:
        resolved = self.normalize_path(path)
        return any(root == resolved or root in resolved.parents for root in self._allowed_roots)

    def is_writable_path(self, path: str | Path, *, allow_create: bool = False) -> bool:
        resolved = self.normalize_path(path)
        target = resolved if resolved.exists() and not allow_create else resolved.parent
        if not target.exists():
            return False
        return os.access(target, os.W_OK)

    def ensure_scoped_path(self, path: str | Path) -> Path:
        resolved = self.normalize_path(path)
        if self.is_within_allowed_roots(resolved):
            return resolved
        raise ValueError(f"path outside allowed roots: {resolved}")

    def choose_file(self, *, app_name: str, path: str | Path) -> str:
        resolved = self.ensure_scoped_path(path)
        quoted_app = applescript_quote(app_name)
        quoted_path = applescript_quote(str(resolved))
        script = f"""
tell application "System Events"
  tell process {quoted_app}
    delay 0.4
    keystroke "G" using {{command down, shift down}}
    delay 0.4
    keystroke {quoted_path}
    delay 0.2
    key code 36
    delay 0.5
    key code 36
    delay 0.3
  end tell
end tell
"""
        run_applescript(script, timeout_s=10.0)
        return str(resolved)

    def confirm_dialog(self, *, app_name: str) -> None:
        quoted_app = applescript_quote(app_name)
        script = f"""
tell application "System Events"
  tell process {quoted_app}
    key code 36
  end tell
end tell
"""
        run_applescript(script, timeout_s=5.0)

    def verify_file_exists(self, path: str | Path) -> str:
        resolved = self.ensure_scoped_path(path)
        if not resolved.exists():
            raise FileNotFoundError(str(resolved))
        return str(resolved)

    def move_file_scoped(self, *, source: str | Path, destination: str | Path) -> str:
        source_path = Path(source).expanduser().resolve()
        destination_path = self.ensure_scoped_path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(destination_path))
        return str(destination_path)

    def wait_for_download(
        self,
        *,
        download_dir: str | Path,
        known_files: set[str],
        timeout_s: float = 20.0,
    ) -> Path:
        folder = Path(download_dir).expanduser().resolve()
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            current = {item.name for item in folder.glob("*") if item.is_file()}
            new_files = sorted(current - known_files)
            for candidate in new_files:
                path = folder / candidate
                if not path.name.endswith(".download"):
                    return path
            time.sleep(0.25)
        raise TimeoutError(f"download not detected in {folder}")

    def observe_file_operation(
        self,
        *,
        path: str | Path | None = None,
        dialog_open: bool = False,
        selected_path: str | Path | None = None,
        download_completed: bool | None = None,
        allow_create: bool = False,
    ) -> FileOperationObservation:
        raw_path = selected_path or path
        resolved_path: Path | None = None
        if raw_path is not None:
            resolved_path = self.normalize_path(raw_path)
        file_exists = resolved_path.exists() if resolved_path is not None else None
        file_size_bytes = (
            resolved_path.stat().st_size
            if resolved_path is not None and file_exists and resolved_path.is_file()
            else None
        )
        within_allowed_roots = (
            self.is_within_allowed_roots(resolved_path)
            if resolved_path is not None
            else None
        )
        writable = (
            self.is_writable_path(resolved_path, allow_create=allow_create)
            if resolved_path is not None
            else None
        )
        completed = (
            download_completed
            if download_completed is not None
            else (file_exists and bool(file_size_bytes and file_size_bytes > 0))
            if resolved_path is not None
            else None
        )
        return FileOperationObservation(
            dialog_open=dialog_open,
            selected_path=str(raw_path) if raw_path is not None else None,
            resolved_path=str(resolved_path) if resolved_path is not None else None,
            file_exists=file_exists,
            file_size_bytes=file_size_bytes,
            within_allowed_roots=within_allowed_roots,
            writable=writable,
            download_completed=completed,
            captured_at=datetime.now(UTC).isoformat(),
        )
