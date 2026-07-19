from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime

from imperaos.computer_use.adapters._macos import applescript_quote, run_applescript
from imperaos.computer_use.models import SurfaceObservation


@dataclass(slots=True)
class WindowMetadata:
    app_name: str
    window_title: str
    focused: bool
    dialog_open: bool
    bundle_id: str | None = None


class DesktopAdapter:
    def launch_app(self, app_name: str) -> None:
        subprocess.run(["open", "-a", app_name], check=True, capture_output=True, text=True)

    def focus_window(self, app_name: str) -> None:
        run_applescript(f'tell application {applescript_quote(app_name)} to activate')

    def frontmost_app(self) -> str:
        script = """
tell application "System Events"
  return name of first application process whose frontmost is true
end tell
"""
        return run_applescript(script)

    def bundle_id(self, app_name: str) -> str | None:
        try:
            bundle_id = run_applescript(f"return id of application {applescript_quote(app_name)}")
        except RuntimeError:
            return None
        return bundle_id or None

    def inspect_windows(self, app_name: str) -> list[WindowMetadata]:
        quoted = applescript_quote(app_name)
        script = f"""
tell application "System Events"
  if not (exists process {quoted}) then
    return ""
  end if
  tell process {quoted}
    set focusedFlag to frontmost
    set windowTitle to ""
    if (count of windows) > 0 then
      set windowTitle to name of front window
    end if
    set dialogFlag to false
    if (count of windows) > 0 then
      if (exists sheet 1 of front window) then
        set dialogFlag to true
      end if
    end if
    return (windowTitle & "|" & focusedFlag & "|" & dialogFlag)
  end tell
end tell
"""
        raw = run_applescript(script)
        if not raw:
            return []
        title, focused, dialog = (raw.split("|", 2) + ["", "false", "false"])[:3]
        return [
            WindowMetadata(
                app_name=app_name,
                window_title=title,
                focused=focused.lower() == "true",
                dialog_open=dialog.lower() == "true",
                bundle_id=self.bundle_id(app_name),
            )
        ]

    def detect_dialog(self, app_name: str) -> bool:
        windows = self.inspect_windows(app_name)
        return any(item.dialog_open for item in windows)

    def observe_surface(self, app_name: str | None = None) -> SurfaceObservation:
        foreground_app = self.frontmost_app()
        target_app = foreground_app or app_name or ""
        windows = self.inspect_windows(target_app) if target_app else []
        window_title = windows[0].window_title if windows else ""
        bundle_id = windows[0].bundle_id if windows else self.bundle_id(target_app)
        return SurfaceObservation(
            foreground_app=foreground_app or None,
            bundle_id=bundle_id,
            focused_window_title=window_title or None,
            modal_detected=any(item.dialog_open for item in windows),
            visible_selectors=None,
            captured_at=datetime.now(UTC).isoformat(),
        )
