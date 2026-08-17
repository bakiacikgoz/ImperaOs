from __future__ import annotations

import platform as _platform
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class PlatformInfo:
    system: str
    label: str
    machine: str
    release: str


def current_platform() -> PlatformInfo:
    system = _platform.system()
    label = {
        "Darwin": "macos",
        "Linux": "linux",
        "Windows": "windows",
    }.get(system, "unknown")
    return PlatformInfo(
        system=system,
        label=label,
        machine=_platform.machine(),
        release=_platform.release(),
    )


def platform_label() -> str:
    return current_platform().label


def is_windows() -> bool:
    return platform_label() == "windows"


def is_macos() -> bool:
    return platform_label() == "macos"


def is_linux() -> bool:
    return platform_label() == "linux"


def default_temp_dir() -> Path:
    return Path(tempfile.gettempdir()).expanduser().resolve()


def default_download_dir() -> Path:
    downloads = Path.home().joinpath("Downloads").expanduser()
    if downloads.exists() and downloads.is_dir():
        return downloads.resolve()
    return default_temp_dir()


def safe_allowed_roots(config: Any, artifact_root: str | Path) -> list[Path]:
    candidates = [
        Path.cwd(),
        Path(getattr(config, "workspace_root", Path.cwd())).expanduser(),
        Path(artifact_root).expanduser(),
        default_download_dir(),
        default_temp_dir(),
    ]
    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        key = str(resolved).casefold()
        if key in seen:
            continue
        seen.add(key)
        roots.append(resolved)
    return roots
