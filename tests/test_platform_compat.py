from __future__ import annotations

import subprocess
from types import SimpleNamespace

from imperaos.computer_use.adapters import FileDialogAdapter, ScaffoldBrowserAdapter
from imperaos.computer_use.runtime import ComputerUseRunner, RuntimeAdapters
from imperaos.runtime import platform as platform_mod
from imperaos.runtime.config import RuntimeConfig
from imperaos.tools.local_search import find_matches


class _NoopDesktop:
    def launch_app(self, app_name: str) -> None:
        del app_name

    def focus_window(self, app_name: str) -> None:
        del app_name

    def frontmost_app(self) -> str:
        return ""

    def bundle_id(self, app_name: str) -> str | None:
        del app_name
        return None

    def inspect_windows(self, app_name: str) -> list[object]:
        del app_name
        return []

    def detect_dialog(self, app_name: str) -> bool:
        del app_name
        return False

    def observe_surface(self, app_name: str | None = None):
        del app_name
        raise AssertionError("Windows fail-closed boundary should avoid live desktop calls")


def test_platform_helper_maps_windows(monkeypatch) -> None:
    monkeypatch.setattr(platform_mod._platform, "system", lambda: "Windows")
    monkeypatch.setattr(platform_mod._platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(platform_mod._platform, "release", lambda: "11")

    info = platform_mod.current_platform()

    assert info.label == "windows"
    assert platform_mod.is_windows() is True


def test_safe_allowed_roots_uses_downloads_or_temp(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(platform_mod, "default_download_dir", lambda: tmp_path / "Downloads")
    monkeypatch.setattr(platform_mod, "default_temp_dir", lambda: tmp_path / "Temp")
    config = SimpleNamespace(workspace_root=tmp_path / "workspace")

    roots = platform_mod.safe_allowed_roots(config, tmp_path / "jobs")

    assert (tmp_path / "jobs").resolve() in roots
    assert (tmp_path / "Downloads").resolve() in roots
    assert len({str(root).casefold() for root in roots}) == len(roots)


def test_computer_use_readiness_is_fail_closed_on_windows(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "imperaos.computer_use.runtime.current_platform",
        lambda: SimpleNamespace(
            system="Windows",
            label="windows",
            machine="AMD64",
            release="11",
        ),
    )
    runner = ComputerUseRunner(
        config=RuntimeConfig.from_profile("default"),
        root_dir=tmp_path / "jobs",
        adapters=RuntimeAdapters(
            browser=ScaffoldBrowserAdapter(),
            desktop=_NoopDesktop(),
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
            finder=None,
            editor=None,
        ),
    )

    report = runner.readiness_report()

    assert report["platform"] == "windows"
    assert report["status"] == "blocked"
    assert report["computer_use"]["live_execution"] is False
    assert report["computer_use"]["reason_code"] == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"


def test_computer_use_run_stops_before_live_adapters_on_windows(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "imperaos.computer_use.runtime.current_platform",
        lambda: SimpleNamespace(
            system="Windows",
            label="windows",
            machine="AMD64",
            release="11",
        ),
    )
    runner = ComputerUseRunner(
        config=RuntimeConfig.from_profile("default"),
        root_dir=tmp_path / "jobs",
        adapters=RuntimeAdapters(
            browser=ScaffoldBrowserAdapter(),
            desktop=_NoopDesktop(),
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
            finder=None,
            editor=None,
        ),
    )

    payload = runner.run(prompt="Open https://example.com", job_id="cu-win")

    assert payload["job"]["status"] == "failed"
    assert (
        payload["computer_use"]["platform_boundary"]["reason_code"]
        == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    )


def test_local_search_falls_back_when_rg_cannot_execute(monkeypatch, tmp_path) -> None:
    sample = tmp_path / "sample.md"
    sample.write_text("Fallback policy and router summary lines", encoding="utf-8")

    def blocked_rg(*args, **kwargs):
        del args, kwargs
        raise PermissionError("rg.exe")

    monkeypatch.setattr(subprocess, "run", blocked_rg)

    matches = find_matches("router summary", tmp_path)

    assert matches == [
        {
            "path": str(sample),
            "line": 1,
            "text": "Fallback policy and router summary lines",
        }
    ]
