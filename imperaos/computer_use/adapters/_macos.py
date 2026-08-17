from __future__ import annotations

import subprocess


class MacOSAutomationError(RuntimeError):
    pass


def run_applescript(script: str, *, timeout_s: float = 15.0) -> str:
    proc = subprocess.run(
        ["osascript", "-"],
        input=script,
        text=True,
        capture_output=True,
        timeout=timeout_s,
        check=False,
    )
    if proc.returncode != 0:
        raise MacOSAutomationError(proc.stderr.strip() or "osascript failed")
    return proc.stdout.strip()


def applescript_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
