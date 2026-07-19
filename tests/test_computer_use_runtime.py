from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from imperaos.computer_use.adapters import BrowserAdapter, FileDialogAdapter, WindowMetadata
from imperaos.computer_use.adapters._macos import MacOSAutomationError
from imperaos.computer_use.models import (
    BrowserTaskFamily,
    ComputerUseMode,
    ComputerUseReadinessStatus,
    EvidenceEnvelope,
    PerceptionSnapshot,
    PerceptionSource,
    ProposedAction,
    ReadinessReport,
    SelectorContext,
    SessionExecutionState,
    SurfaceObservation,
    TargetDescriptor,
    VerificationResult,
)
from imperaos.computer_use.perception import build_perception_fingerprint
from imperaos.computer_use.prompt_parser import parse_prompt_to_actions
from imperaos.computer_use.runtime import (
    ComputerUseRunner,
    RuntimeAdapters,
    SessionCommand,
    SessionControlBus,
)
from imperaos.runtime.config import RuntimeConfig


def _wait_until(predicate, timeout_s: float = 5.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if predicate():
                return
        except (PermissionError, json.JSONDecodeError):
            pass
        time.sleep(0.05)
    raise AssertionError("timed out waiting for predicate")


def _read_event_names(events_path: Path) -> list[str]:
    return [event["event"] for event in _read_events(events_path)]


def _read_events(events_path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class _FakeDesktopAdapter:
    def __init__(self) -> None:
        self._frontmost = "Safari"
        self._dialog_open = False
        self._window_titles = {
            "Safari": "Safari window",
            "Finder": "Finder window",
            "Notes": "Notes window",
            "TextEdit": "TextEdit window",
        }
        self._bundle_ids = {
            "Safari": "com.apple.Safari",
            "Finder": "com.apple.finder",
            "Notes": "com.apple.Notes",
            "TextEdit": "com.apple.TextEdit",
        }

    def launch_app(self, app_name: str) -> None:
        self._frontmost = app_name

    def focus_window(self, app_name: str) -> None:
        self._frontmost = app_name

    def frontmost_app(self) -> str:
        return self._frontmost

    def set_frontmost(self, app_name: str) -> None:
        self._frontmost = app_name

    def set_dialog_open(self, value: bool) -> None:
        self._dialog_open = value

    def bundle_id(self, app_name: str) -> str | None:
        return self._bundle_ids.get(app_name)

    def inspect_windows(self, app_name: str) -> list[WindowMetadata]:
        if app_name != self._frontmost and app_name != "Safari":
            return []
        return [
            WindowMetadata(
                app_name=app_name,
                window_title=self._window_titles.get(app_name, f"{app_name} window"),
                focused=app_name == self._frontmost,
                dialog_open=self._dialog_open if app_name == self._frontmost else False,
                bundle_id=self.bundle_id(app_name),
            )
        ]

    def detect_dialog(self, app_name: str) -> bool:
        return app_name == self._frontmost and self._dialog_open

    def observe_surface(self, app_name: str | None = None) -> SurfaceObservation:
        target_app = self._frontmost or app_name or "Safari"
        return SurfaceObservation(
            foreground_app=self._frontmost,
            bundle_id=self.bundle_id(self._frontmost),
            focused_window_title=self._window_titles.get(target_app, f"{target_app} window"),
            modal_detected=self._dialog_open,
            visible_selectors=None,
            captured_at="2026-03-14T00:00:00+00:00",
        )


class _FakeFinderAdapter:
    def __init__(self, *, desktop: _FakeDesktopAdapter, dialog: FileDialogAdapter) -> None:
        self._desktop = desktop
        self._dialog = dialog
        self._selected_paths: list[str] = []

    def reveal_path(self, path: str) -> str:
        resolved = self._dialog.verify_file_exists(path)
        self._selected_paths = [resolved]
        self._desktop.focus_window("Finder")
        return resolved

    def rename_path(self, *, path: str, new_name: str) -> str:
        source = Path(self._dialog.verify_file_exists(path))
        destination = self._dialog.ensure_scoped_path(source.with_name(new_name))
        source.rename(destination)
        return self.reveal_path(str(destination))

    def move_path(self, *, source: str, destination: str) -> str:
        source_path = Path(self._dialog.verify_file_exists(source))
        destination_path = self._dialog.ensure_scoped_path(destination)
        if destination_path.exists() and destination_path.is_dir():
            destination_path = self._dialog.ensure_scoped_path(destination_path / source_path.name)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.rename(destination_path)
        return self.reveal_path(str(destination_path))

    def selected_paths(self) -> list[str]:
        return list(self._selected_paths)

    def current_folder(self) -> str | None:
        if not self._selected_paths:
            return None
        return str(Path(self._selected_paths[0]).parent)

    def observe_surface(self) -> SurfaceObservation:
        return SurfaceObservation(
            foreground_app=self._desktop.frontmost_app(),
            bundle_id=self._desktop.bundle_id("Finder"),
            focused_window_title="Finder window",
            selected_paths=list(self._selected_paths),
            active_document_path=self.current_folder(),
            modal_detected=False,
            visible_selectors=None,
            captured_at="2026-03-14T00:00:00+00:00",
        )


class _FakeTextEditAdapter:
    def __init__(self, *, desktop: _FakeDesktopAdapter, dialog: FileDialogAdapter) -> None:
        self._desktop = desktop
        self._dialog = dialog
        self._current_path: str | None = None
        self._text = ""

    def open_file(self, path: str) -> str:
        resolved = self._dialog.ensure_scoped_path(path)
        if not resolved.exists():
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text("", encoding="utf-8")
        self._current_path = str(resolved)
        self._text = resolved.read_text(encoding="utf-8")
        self._desktop.focus_window("TextEdit")
        return self._current_path

    def append_text(self, *, text: str, path: str | None = None) -> str:
        if path:
            self.open_file(path)
        if self._current_path is None:
            raise RuntimeError("no_open_document")
        self._desktop.focus_window("TextEdit")
        self._text += text
        return self._current_path

    def save_document(self, *, path: str | None = None) -> str:
        if path:
            resolved = self._dialog.ensure_scoped_path(path)
            if self._current_path is None:
                self.open_file(path)
            else:
                resolved.parent.mkdir(parents=True, exist_ok=True)
                self._current_path = str(resolved)
        if self._current_path is None:
            raise RuntimeError("no_open_document")
        resolved = Path(self._current_path)
        resolved.write_text(self._text, encoding="utf-8")
        self._desktop.focus_window("TextEdit")
        return self._current_path

    def current_document_path(self) -> str | None:
        return self._current_path

    def current_document_text(self) -> str:
        return self._text

    def observe_surface(self) -> SurfaceObservation:
        return SurfaceObservation(
            foreground_app=self._desktop.frontmost_app(),
            bundle_id=self._desktop.bundle_id("TextEdit"),
            focused_window_title="TextEdit window",
            active_document_path=self._current_path,
            modal_detected=False,
            visible_selectors=None,
            captured_at="2026-03-14T00:00:00+00:00",
        )


class _FakeBrowserAdapter(BrowserAdapter):
    adapter_status = "fake_runtime"

    def __init__(
        self,
        *,
        desktop: _FakeDesktopAdapter,
        on_verified=None,
        surface_url_overrides: dict[int, str] | None = None,
        hidden_selectors_on_observe: dict[int, set[str]] | None = None,
        modal_on_observe: set[int] | None = None,
        create_download_artifact: bool = True,
        omit_selected_file_result: bool = False,
        wait_delay_s: float | None = None,
    ) -> None:
        self._desktop = desktop
        self._current_url = "about:blank"
        self._title = "Fake Browser"
        self._values: dict[str, str] = {}
        self._on_verified = on_verified
        self._observe_count = 0
        self._surface_url_overrides = dict(surface_url_overrides or {})
        self._hidden_selectors_on_observe = {
            key: set(value) for key, value in (hidden_selectors_on_observe or {}).items()
        }
        self._modal_on_observe = set(modal_on_observe or ())
        self._create_download_artifact = create_download_artifact
        self._omit_selected_file_result = omit_selected_file_result
        self._wait_delay_s = wait_delay_s

    def observe_surface(self, *, target: TargetDescriptor | None = None) -> SurfaceObservation:
        self._observe_count += 1
        selector = target.selector if target is not None else None
        current_url = self._surface_url_overrides.get(self._observe_count, self._current_url)
        visible_selectors: list[str] | None = None
        if selector and selector not in {"document", "window"}:
            hidden = self._hidden_selectors_on_observe.get(self._observe_count, set())
            visible_selectors = [] if selector in hidden else [selector]
        return SurfaceObservation(
            foreground_app=self._desktop.frontmost_app(),
            bundle_id=self._desktop.bundle_id("Safari"),
            focused_window_title="Safari window",
            active_tab_url=current_url,
            active_tab_title=self._title if current_url == self._current_url else "Drifted page",
            modal_detected=self._observe_count in self._modal_on_observe,
            visible_selectors=visible_selectors,
            captured_at="2026-03-14T00:00:00+00:00",
        )

    def inspect_target(self, *, target: TargetDescriptor) -> PerceptionSnapshot:
        selector_context = SelectorContext(
            selector=target.selector,
            selector_source=target.selector_source,
            selector_trace=[target.selector],
        )
        fingerprint = build_perception_fingerprint(
            window_or_tab_identity="safari:fake",
            app_identity="browser:safari",
            selector_context=selector_context.model_dump(mode="json"),
            screenshot_hash=f"{target.selector}:{self._current_url}",
        )
        return PerceptionSnapshot(
            source=PerceptionSource.DOM,
            confidence=0.99,
            perception_fingerprint=fingerprint,
            sensitive_surface=False,
            focused=self._desktop.frontmost_app() == "Safari",
            unexpected_modal=False,
            selector_ambiguous=False,
            window_or_tab_identity="safari:fake",
            app_identity="browser:safari",
            current_url=self._current_url,
            selector_context=selector_context,
            evidence=EvidenceEnvelope(
                screenshot_hash="shot-hash-runtime",
                redacted_fingerprint="fingerprint-runtime",
                accessibility_subset={
                    "title": self._title,
                    "value": self._values.get(target.selector, ""),
                },
            ),
        )

    def execute(self, *, action: ProposedAction) -> dict[str, str]:
        self._desktop.focus_window("Safari")
        if action.action_id == "open_url":
            self._current_url = str(
                action.parameters.get("url") or action.target_descriptor.current_url
            )
            self._title = "Opened"
            return {"status": "executed", "url": self._current_url, "title": self._title}
        if action.action_id == "type_text":
            text = str(action.parameters.get("text") or "")
            self._values[action.target_descriptor.selector] = text
            return {"status": "executed", "value": text}
        if action.action_id == "click":
            self._values[action.target_descriptor.selector] = "clicked"
            return {"status": "executed"}
        if action.action_id == "select_option":
            value = str(action.parameters.get("value") or "")
            self._values[action.target_descriptor.selector] = value
            return {"status": "executed", "value": value}
        if action.action_id == "upload_file":
            selected_path = str(action.parameters.get("path") or "")
            self._values[action.target_descriptor.selector] = Path(selected_path).name
            result = {
                "status": "executed",
                "selected_file_name": Path(selected_path).name,
                "dialog_interacted": True,
            }
            if not self._omit_selected_file_result:
                result["selected_file"] = selected_path
            return result
        if action.action_id == "download_file":
            output_path = str(action.parameters.get("output_path") or "")
            if output_path and self._create_download_artifact:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_text("download artifact", encoding="utf-8")
            result = {"status": "executed", "download_triggered": True}
            if output_path and self._create_download_artifact:
                result["download_path"] = output_path
            return result
        if action.action_id == "wait":
            seconds = float(action.parameters.get("seconds") or 0.0)
            time.sleep(self._wait_delay_s if self._wait_delay_s is not None else seconds)
            return {"status": "executed"}
        raise RuntimeError(f"unsupported action in fake adapter: {action.action_id}")

    def verify(
        self,
        *,
        action: ProposedAction,
        before: PerceptionSnapshot | None = None,
    ) -> VerificationResult:
        del before
        kind = action.verification_kind
        expected = action.verification_value or ""
        if kind == "url":
            verified = self._current_url.startswith(expected)
            result = VerificationResult(
                verified=verified,
                kind="url",
                summary="URL matches the requested destination." if verified else "URL mismatch.",
                expected={"url": expected},
                observed={"url": self._current_url},
                mismatch_code=None if verified else "url_mismatch",
                retryable=not verified,
            )
        elif kind == "value":
            current = self._values.get(action.target_descriptor.selector, "")
            verified = current == expected
            result = VerificationResult(
                verified=verified,
                kind="value",
                summary="Value matches expected input." if verified else "Value mismatch.",
                expected={"value": expected},
                observed={"value": current},
                mismatch_code=None if verified else "value_mismatch",
                retryable=not verified,
            )
        elif kind == "selector_present":
            result = VerificationResult(
                verified=True,
                kind="selector_present",
                summary="Selector remained present after click.",
                expected={"selector_count": 1},
                observed={"selector_count": 1, "state_change": True},
            )
        else:
            result = VerificationResult(
                verified=True,
                kind=kind or "none",
                summary="Verification passed.",
            )
        if result.verified and self._on_verified is not None:
            self._on_verified(action)
        return result


class _FailingClickBrowserAdapter(_FakeBrowserAdapter):
    def verify(
        self,
        *,
        action: ProposedAction,
        before: PerceptionSnapshot | None = None,
    ) -> VerificationResult:
        if action.verification_kind == "selector_present":
            return VerificationResult(
                verified=False,
                kind="selector_present",
                summary="Click did not cause a visible state change.",
                expected={"state_change": True},
                observed={"state_change": False},
                mismatch_code="no_state_change_after_click",
                retryable=True,
            )
        return super().verify(action=action, before=before)


def test_prompt_parser_builds_an_automation_sequence() -> None:
    family, actions = parse_prompt_to_actions(
        prompt=(
            'launch "Safari"\n'
            'open "https://ops.example.internal/queue"\n'
            'type "ImperaOS" into "#name"'
        ),
        mode=ComputerUseMode.EXECUTE,
    )

    assert family == BrowserTaskFamily.AUTOMATION_SEQUENCE
    assert [item.action_id for item in actions] == ["launch_app", "open_url", "type_text"]
    assert actions[1].verification_kind == "url"
    assert actions[2].parameters["text"] == "ImperaOS"


def test_prompt_parser_builds_local_desktop_actions() -> None:
    family, actions = parse_prompt_to_actions(
        prompt=(
            'finder_reveal "/tmp/report.txt"\n'
            'textedit_open "/tmp/note.txt"\n'
            'textedit_append "reviewed"'
        ),
        mode=ComputerUseMode.EXECUTE,
    )

    assert family == BrowserTaskFamily.AUTOMATION_SEQUENCE
    assert [item.action_id for item in actions] == [
        "finder_reveal",
        "textedit_open",
        "textedit_append",
    ]
    assert actions[0].app_identity == "desktop:Finder"
    assert actions[1].verification_kind == "document_path"
    assert actions[2].verification_kind == "document_contains"


def test_session_control_bus_round_trips_commands(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-control"
    job_dir.mkdir()
    bus = SessionControlBus(job_dir)

    bus.write(SessionCommand.PAUSE, reason="operator_pause")
    paused = bus.read()
    assert paused.command == SessionCommand.PAUSE
    assert paused.reason == "operator_pause"

    bus.clear()
    assert bus.read().command == SessionCommand.RUN


def test_computer_use_runner_executes_a_real_runtime_slice_with_fake_adapters(
    tmp_path: Path,
) -> None:
    root_dir = tmp_path / "jobs"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    browser = _FakeBrowserAdapter(desktop=desktop)
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=browser,
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )

    payload = runner.run(
        prompt='open "https://ops.example.internal/queue"\ntype "ImperaOS Operator" into "#name"',
        job_id="job-runtime-complete",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "completed"
    status_payload = json.loads(
        (root_dir / "job-runtime-complete" / "status.json").read_text(encoding="utf-8")
    )
    assert status_payload["computer_use"]["lifecycle_state"] == "completed"
    assert (
        status_payload["computer_use"]["world_model"]["current_url"]
        == "https://ops.example.internal/queue"
    )
    assert status_payload["computer_use"]["last_verification_result"]["kind"] == "value"
    assert status_payload["computer_use"]["expected_surface"]["app_name"] == "Safari"
    assert status_payload["computer_use"]["surface_mismatch"] is None
    assert (
        status_payload["computer_use"]["world_model"]["observed_surface"]["active_tab_url"]
        == "https://ops.example.internal/queue"
    )
    event_names = _read_event_names(root_dir / "job-runtime-complete" / "events.jsonl")
    assert "action_verified" in event_names
    assert "session_completed" in event_names


def test_computer_use_runner_executes_finder_local_file_flow(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    source_dir = tmp_path / "incoming"
    source_dir.mkdir()
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    source_path = source_dir / "report.txt"
    source_path.write_text("queued report", encoding="utf-8")
    renamed_path = source_dir / "report-renamed.txt"
    final_path = processed_dir / renamed_path.name
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    dialog = FileDialogAdapter(allowed_roots=[tmp_path])
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop),
            desktop=desktop,
            dialog=dialog,
            finder=_FakeFinderAdapter(desktop=desktop, dialog=dialog),
            editor=_FakeTextEditAdapter(desktop=desktop, dialog=dialog),
        ),
    )

    payload = runner.run(
        prompt="\n".join(
            [
                f'finder_reveal "{source_path}"',
                f'finder_rename "{source_path}" to "{renamed_path.name}"',
                f'finder_move "{renamed_path}" to "{processed_dir}"',
            ]
        ),
        job_id="job-runtime-finder-flow",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "completed"
    assert final_path.exists()
    status_payload = json.loads(
        (root_dir / "job-runtime-finder-flow" / "status.json").read_text(encoding="utf-8")
    )
    assert status_payload["computer_use"]["world_model"]["selected_paths"] == [str(final_path)]
    assert (
        status_payload["computer_use"]["artifacts"]["finder_move"]["result_path"]
        == str(final_path)
    )


def test_computer_use_runner_executes_textedit_local_edit_flow(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    document_path = tmp_path / "notes.txt"
    document_path.write_text("hello", encoding="utf-8")
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    dialog = FileDialogAdapter(allowed_roots=[tmp_path])
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop),
            desktop=desktop,
            dialog=dialog,
            finder=_FakeFinderAdapter(desktop=desktop, dialog=dialog),
            editor=_FakeTextEditAdapter(desktop=desktop, dialog=dialog),
        ),
    )

    payload = runner.run(
        prompt="\n".join(
            [
                f'textedit_open "{document_path}"',
                'textedit_append " world"',
                f'textedit_save "{document_path}"',
            ]
        ),
        job_id="job-runtime-textedit-flow",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "completed"
    assert document_path.read_text(encoding="utf-8") == "hello world"
    status_payload = json.loads(
        (root_dir / "job-runtime-textedit-flow" / "status.json").read_text(encoding="utf-8")
    )
    assert (
        status_payload["computer_use"]["world_model"]["active_document_path"]
        == str(document_path)
    )
    assert (
        status_payload["computer_use"]["artifacts"]["textedit_save"]["document_path"]
        == str(document_path)
    )


def test_computer_use_runner_executes_mixed_browser_and_local_document_flow(
    tmp_path: Path,
) -> None:
    root_dir = tmp_path / "jobs"
    download_target = tmp_path / "downloaded.txt"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    dialog = FileDialogAdapter(allowed_roots=[tmp_path])
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop),
            desktop=desktop,
            dialog=dialog,
            finder=_FakeFinderAdapter(desktop=desktop, dialog=dialog),
            editor=_FakeTextEditAdapter(desktop=desktop, dialog=dialog),
        ),
    )

    payload = runner.run(
        prompt="\n".join(
            [
                'open "https://ops.example.internal/report"',
                f'download "#download" to "{download_target}"',
                f'textedit_open "{download_target}"',
                'textedit_append " reviewed"',
                f'textedit_save "{download_target}"',
            ]
        ),
        job_id="job-runtime-browser-local-flow",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "completed"
    assert download_target.read_text(encoding="utf-8") == "download artifact reviewed"
    status_payload = json.loads(
        (root_dir / "job-runtime-browser-local-flow" / "status.json").read_text(
            encoding="utf-8"
        )
    )
    assert str(download_target) in status_payload["computer_use"]["world_model"][
        "filesystem_result_set"
    ]


def test_computer_use_runner_allows_launch_app_to_change_foreground_surface(
    tmp_path: Path,
) -> None:
    root_dir = tmp_path / "jobs"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    desktop.set_frontmost("Notes")
    browser = _FakeBrowserAdapter(desktop=desktop)
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=browser,
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )

    payload = runner.run(
        prompt='launch "Safari"\nopen "https://ops.example.internal/queue"',
        job_id="job-runtime-launch-app",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "completed"
    status_payload = json.loads(
        (root_dir / "job-runtime-launch-app" / "status.json").read_text(encoding="utf-8")
    )
    assert status_payload["computer_use"]["surface_mismatch"] is None
    assert status_payload["computer_use"]["last_verification_result"]["verified"] is True


def test_computer_use_runner_fails_closed_on_wrong_tab_drift(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(
                desktop=desktop,
                surface_url_overrides={3: "https://drift.example.internal/review"},
            ),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )

    payload = runner.run(
        prompt='open "https://ops.example.internal/queue"\ntype "ImperaOS Operator" into "#name"',
        job_id="job-runtime-wrong-tab",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "failed"
    status_payload = json.loads(
        (root_dir / "job-runtime-wrong-tab" / "status.json").read_text(encoding="utf-8")
    )
    assert status_payload["computer_use"]["surface_mismatch"]["code"] == "wrong_tab"
    assert status_payload["computer_use"]["last_verification_result"]["mismatch_code"] == (
        "wrong_tab"
    )
    assert (
        status_payload["computer_use"]["observed_surface"]["active_tab_url"]
        == "https://drift.example.internal/review"
    )
    events = _read_events(root_dir / "job-runtime-wrong-tab" / "events.jsonl")
    mismatch_events = [
        event for event in events if event["event"] == "computer_use.surface_mismatch"
    ]
    assert len(mismatch_events) == 1
    mismatch_data = mismatch_events[0]["data"]
    assert mismatch_data["reason_code"] == "wrong_tab"
    assert mismatch_data["observed_surface"]["active_tab_url"] == (
        "https://drift.example.internal/review"
    )
    assert mismatch_data["expected_surface"]["tab_url_host"] == "ops.example.internal"


def test_computer_use_runner_fails_closed_on_wrong_foreground_app(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    desktop.set_frontmost("Notes")
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )

    payload = runner.run(
        prompt='type "ImperaOS Operator" into "#name"',
        job_id="job-runtime-wrong-app",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "failed"
    status_payload = json.loads(
        (root_dir / "job-runtime-wrong-app" / "status.json").read_text(encoding="utf-8")
    )
    assert status_payload["computer_use"]["surface_mismatch"]["code"] == "wrong_app"
    assert status_payload["computer_use"]["observed_surface"]["foreground_app"] == "Notes"


def test_computer_use_runner_fails_closed_on_unexpected_modal(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop, modal_on_observe={1}),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )

    payload = runner.run(
        prompt='type "ImperaOS Operator" into "#name"',
        job_id="job-runtime-modal",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "failed"
    status_payload = json.loads(
        (root_dir / "job-runtime-modal" / "status.json").read_text(encoding="utf-8")
    )
    assert status_payload["computer_use"]["surface_mismatch"]["code"] == "unexpected_modal"


def test_computer_use_runner_fails_closed_on_missing_expected_selector(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(
                desktop=desktop,
                hidden_selectors_on_observe={1: {"#name"}},
            ),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )

    payload = runner.run(
        prompt='type "ImperaOS Operator" into "#name"',
        job_id="job-runtime-missing-selector",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "failed"
    status_payload = json.loads(
        (root_dir / "job-runtime-missing-selector" / "status.json").read_text(
            encoding="utf-8"
        )
    )
    assert status_payload["computer_use"]["surface_mismatch"]["code"] == (
        "missing_expected_selector"
    )


def test_computer_use_runner_verifies_allowed_root_upload_and_serializes_artifact(
    tmp_path: Path,
) -> None:
    root_dir = tmp_path / "jobs"
    upload_path = tmp_path / "upload.txt"
    upload_path.write_text("upload fixture", encoding="utf-8")
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )

    payload = runner.run(
        prompt=(
            'open "https://ops.example.internal/queue"\n'
            f'upload "{upload_path}" to "#upload"'
        ),
        job_id="job-runtime-upload-success",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "completed"
    status_payload = json.loads(
        (root_dir / "job-runtime-upload-success" / "status.json").read_text(
            encoding="utf-8"
        )
    )
    verification = status_payload["computer_use"]["last_verification_result"]
    assert verification["expected_file_operation"]["operation"] == "upload"
    assert verification["observed_file_operation"]["resolved_path"] == str(upload_path.resolve())
    assert verification["file_operation_mismatch"] is None
    assert status_payload["computer_use"]["artifacts"]["upload_file"]["selected_file"] == str(
        upload_path
    )
    event_names = _read_event_names(root_dir / "job-runtime-upload-success" / "events.jsonl")
    assert "computer_use.file_operation_verified" in event_names


def test_computer_use_runner_fails_closed_on_upload_path_outside_allowed_roots(
    tmp_path: Path,
) -> None:
    root_dir = tmp_path / "jobs"
    outside_path = tmp_path.parent / "outside-upload.txt"
    outside_path.write_text("outside root", encoding="utf-8")
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )

    payload = runner.run(
        prompt=(
            'open "https://ops.example.internal/queue"\n'
            f'upload "{outside_path}" to "#upload"'
        ),
        job_id="job-runtime-upload-outside-root",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "failed"
    status_payload = json.loads(
        (root_dir / "job-runtime-upload-outside-root" / "status.json").read_text(
            encoding="utf-8"
        )
    )
    assert status_payload["computer_use"]["file_operation_mismatch"]["code"] == (
        "path_outside_allowed_roots"
    )
    assert status_payload["computer_use"]["last_verification_result"]["mismatch_code"] == (
        "path_outside_allowed_roots"
    )


def test_computer_use_runner_fails_closed_on_missing_upload_file(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    missing_path = tmp_path / "missing-upload.txt"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )

    payload = runner.run(
        prompt=(
            'open "https://ops.example.internal/queue"\n'
            f'upload "{missing_path}" to "#upload"'
        ),
        job_id="job-runtime-upload-missing",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "failed"
    status_payload = json.loads(
        (root_dir / "job-runtime-upload-missing" / "status.json").read_text(
            encoding="utf-8"
        )
    )
    assert status_payload["computer_use"]["file_operation_mismatch"]["code"] == "file_missing"


def test_computer_use_runner_verifies_download_artifact_and_indexes_it(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    output_path = tmp_path / "artifact.txt"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )

    payload = runner.run(
        prompt=(
            'open "https://ops.example.internal/queue"\n'
            f'download "#download" to "{output_path}"'
        ),
        job_id="job-runtime-download-success",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "completed"
    assert output_path.exists()
    status_payload = json.loads(
        (root_dir / "job-runtime-download-success" / "status.json").read_text(
            encoding="utf-8"
        )
    )
    verification = status_payload["computer_use"]["last_verification_result"]
    assert verification["expected_file_operation"]["operation"] == "download"
    assert verification["observed_file_operation"]["file_size_bytes"] > 0
    assert status_payload["computer_use"]["artifacts"]["download_file"]["download_path"] == str(
        output_path
    )
    assert (
        str(output_path)
        in status_payload["computer_use"]["world_model"]["filesystem_result_set"]
    )


def test_computer_use_runner_fails_closed_when_download_artifact_is_not_created(
    tmp_path: Path,
) -> None:
    root_dir = tmp_path / "jobs"
    output_path = tmp_path / "missing-artifact.txt"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop, create_download_artifact=False),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )

    payload = runner.run(
        prompt=(
            'open "https://ops.example.internal/queue"\n'
            f'download "#download" to "{output_path}"'
        ),
        job_id="job-runtime-download-missing",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "failed"
    status_payload = json.loads(
        (root_dir / "job-runtime-download-missing" / "status.json").read_text(
            encoding="utf-8"
        )
    )
    assert status_payload["computer_use"]["file_operation_mismatch"]["code"] == (
        "file_not_created"
    )
    events = _read_events(root_dir / "job-runtime-download-missing" / "events.jsonl")
    mismatch_events = [
        event for event in events if event["event"] == "computer_use.file_operation_mismatch"
    ]
    assert len(mismatch_events) == 1
    assert mismatch_events[0]["data"]["reason_code"] == "file_not_created"


def test_computer_use_runner_honors_pause_and_resume(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    job_id = "job-runtime-pause"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    pause_triggered = {"value": False}

    def request_pause(action: ProposedAction) -> None:
        if action.action_id == "open_url" and not pause_triggered["value"]:
            SessionControlBus(root_dir / job_id).write(SessionCommand.PAUSE, reason="test_pause")
            pause_triggered["value"] = True

    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop, on_verified=request_pause),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )
    outcome: dict[str, object] = {}

    def worker() -> None:
        try:
            outcome["payload"] = runner.run(
                prompt=(
                    'open "https://ops.example.internal/queue"\n'
                    'type "ImperaOS Operator" into "#name"'
                ),
                job_id=job_id,
                mode=ComputerUseMode.EXECUTE,
            )
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    status_path = root_dir / job_id / "status.json"
    _wait_until(
        lambda: status_path.exists()
        and json.loads(status_path.read_text(encoding="utf-8"))["computer_use"]["paused"] is True
    )

    control_runner = ComputerUseRunner(config=config, root_dir=root_dir)
    control_runner.request_control(job_id=job_id, command=SessionCommand.RESUME)
    thread.join(timeout=5.0)

    assert not thread.is_alive()
    assert "error" not in outcome
    payload = outcome["payload"]
    assert isinstance(payload, dict)
    assert payload["job"]["status"] == "completed"
    event_names = _read_event_names(root_dir / job_id / "events.jsonl")
    assert "session_paused" in event_names
    assert "session_resumed" in event_names


def test_computer_use_runner_fails_closed_on_verification_mismatch(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FailingClickBrowserAdapter(desktop=desktop),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )

    payload = runner.run(
        prompt='open "https://ops.example.internal/queue"\nclick "#advance"',
        job_id="job-runtime-verify-fail",
        mode=ComputerUseMode.EXECUTE,
    )

    assert payload["job"]["status"] == "failed"
    status_payload = json.loads(
        (root_dir / "job-runtime-verify-fail" / "status.json").read_text(encoding="utf-8")
    )
    assert status_payload["computer_use"]["last_verification_result"]["mismatch_code"] == (
        "no_state_change_after_click"
    )
    event_names = _read_event_names(root_dir / "job-runtime-verify-fail" / "events.jsonl")
    assert "action_failed" in event_names


def test_computer_use_runner_honors_stop_while_paused(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    job_id = "job-runtime-stop"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    pause_triggered = {"value": False}

    def request_pause(action: ProposedAction) -> None:
        if action.action_id == "open_url" and not pause_triggered["value"]:
            SessionControlBus(root_dir / job_id).write(SessionCommand.PAUSE, reason="test_pause")
            pause_triggered["value"] = True

    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop, on_verified=request_pause),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )
    outcome: dict[str, object] = {}

    def worker() -> None:
        try:
            outcome["payload"] = runner.run(
                prompt=(
                    'open "https://ops.example.internal/queue"\n'
                    'type "ImperaOS Operator" into "#name"'
                ),
                job_id=job_id,
                mode=ComputerUseMode.EXECUTE,
            )
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    status_path = root_dir / job_id / "status.json"
    _wait_until(
        lambda: status_path.exists()
        and json.loads(status_path.read_text(encoding="utf-8"))["computer_use"]["paused"] is True
    )

    control_runner = ComputerUseRunner(config=config, root_dir=root_dir)
    control_runner.request_control(job_id=job_id, command=SessionCommand.STOP)
    thread.join(timeout=5.0)

    assert not thread.is_alive()
    assert "error" in outcome
    assert "session stopped by operator" in str(outcome["error"])

    status_payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert status_payload["computer_use"]["lifecycle_state"] == "stopped"
    assert status_payload["job"]["status"] == "failed"
    event_names = _read_event_names(root_dir / job_id / "events.jsonl")
    assert "session_stopped" in event_names


def test_computer_use_runner_pauses_at_pre_action_checkpoint_and_resumes(
    tmp_path: Path,
) -> None:
    root_dir = tmp_path / "jobs"
    job_id = "job-runtime-pre-action-pause"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    control_runner = ComputerUseRunner(config=config, root_dir=root_dir)
    first_pause: dict[str, object] = {}

    def request_pause(action: ProposedAction) -> None:
        if action.action_id == "open_url" and not first_pause:
            first_pause.update(
                control_runner.request_control(job_id=job_id, command=SessionCommand.PAUSE)
            )

    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop, on_verified=request_pause),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )
    outcome: dict[str, object] = {}

    def worker() -> None:
        try:
            outcome["payload"] = runner.run(
                prompt=(
                    'open "https://ops.example.internal/queue"\n'
                    'wait "0.5"\n'
                    'type "ImperaOS Operator" into "#name"'
                ),
                job_id=job_id,
                mode=ComputerUseMode.EXECUTE,
            )
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    status_path = root_dir / job_id / "status.json"
    _wait_until(
        lambda: status_path.exists() and bool(first_pause),
        timeout_s=10.0,
    )
    assert first_pause["outcome"] == "accepted"
    _wait_until(
        lambda: json.loads(status_path.read_text(encoding="utf-8"))["computer_use"][
            "session_state"
        ]
        == SessionExecutionState.PAUSED.value
    )

    paused_status = json.loads(status_path.read_text(encoding="utf-8"))
    assert paused_status["computer_use"]["last_safe_checkpoint"] == "after_verify"
    assert _read_event_names(root_dir / job_id / "events.jsonl").count("action_started") == 1

    duplicate_pause = control_runner.request_control(job_id=job_id, command=SessionCommand.PAUSE)
    assert duplicate_pause["outcome"] == "already_applied"

    resume_result = control_runner.request_control(job_id=job_id, command=SessionCommand.RESUME)
    assert resume_result["outcome"] == "accepted"
    thread.join(timeout=5.0)

    assert not thread.is_alive()
    assert "error" not in outcome
    payload = outcome["payload"]
    assert isinstance(payload, dict)
    assert payload["job"]["status"] == "completed"
    events = _read_event_names(root_dir / job_id / "events.jsonl")
    assert events.index("computer_use.control_command_received") < events.index(
        "computer_use.pause_requested"
    )
    assert events.index("computer_use.pause_requested") < events.index("computer_use.paused")
    assert events.index("computer_use.resume_requested") < events.index("computer_use.resumed")


def test_computer_use_runner_stops_at_safe_checkpoint_during_long_action(
    tmp_path: Path,
) -> None:
    root_dir = tmp_path / "jobs"
    job_id = "job-runtime-mid-run-stop"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop, wait_delay_s=1.0),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )
    outcome: dict[str, object] = {}

    def worker() -> None:
        try:
            outcome["payload"] = runner.run(
                prompt=(
                    'open "https://ops.example.internal/queue"\n'
                    'wait "1.0"\n'
                    'type "ImperaOS Operator" into "#name"'
                ),
                job_id=job_id,
                mode=ComputerUseMode.EXECUTE,
            )
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    events_path = root_dir / job_id / "events.jsonl"
    _wait_until(
        lambda: events_path.exists()
        and _read_event_names(events_path).count("action_started") >= 2,
        timeout_s=10.0,
    )
    control_runner = ComputerUseRunner(config=config, root_dir=root_dir)
    stop_result = control_runner.request_control(job_id=job_id, command=SessionCommand.STOP)
    assert stop_result["outcome"] == "accepted"
    thread.join(timeout=10.0)

    assert not thread.is_alive()
    assert "error" in outcome
    assert "session stopped by operator" in str(outcome["error"])

    status_payload = json.loads(
        (root_dir / job_id / "status.json").read_text(encoding="utf-8")
    )
    assert status_payload["computer_use"]["session_state"] == SessionExecutionState.STOPPED.value
    assert status_payload["computer_use"]["stopped_by_user"] is True
    assert status_payload["computer_use"]["last_safe_checkpoint"] == "after_execute"
    event_names = _read_event_names(events_path)
    assert event_names.index("computer_use.control_command_received") < event_names.index(
        "computer_use.stop_requested"
    )
    assert event_names.index("computer_use.stop_requested") < event_names.index(
        "computer_use.stopped"
    )

    duplicate_stop = control_runner.request_control(job_id=job_id, command=SessionCommand.STOP)
    assert duplicate_stop["outcome"] == "already_applied"


def test_computer_use_runner_rejects_invalid_resume_while_running(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    job_id = "job-runtime-invalid-resume"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    control_runner = ComputerUseRunner(config=config, root_dir=root_dir)
    resume_result: dict[str, object] = {}

    def request_invalid_resume(action: ProposedAction) -> None:
        if action.action_id == "open_url" and not resume_result:
            resume_result.update(
                control_runner.request_control(job_id=job_id, command=SessionCommand.RESUME)
            )

    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(
                desktop=desktop,
                on_verified=request_invalid_resume,
                wait_delay_s=0.4,
            ),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )
    outcome: dict[str, object] = {}

    def worker() -> None:
        try:
            outcome["payload"] = runner.run(
                prompt=(
                    'open "https://ops.example.internal/queue"\n'
                    'wait "0.4"\n'
                    'type "ImperaOS Operator" into "#name"'
                ),
                job_id=job_id,
                mode=ComputerUseMode.EXECUTE,
            )
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    thread.join(timeout=5.0)

    assert not thread.is_alive()
    assert "error" not in outcome
    assert resume_result["outcome"] == "rejected"
    events = _read_events(root_dir / job_id / "events.jsonl")
    names = [event["event"] for event in events]
    received_index = names.index("computer_use.control_command_received")
    rejected_index = names.index("computer_use.control_command_rejected")
    assert received_index < rejected_index
    rejected = events[rejected_index]["data"]["result"]
    assert rejected["reason"] == "resume_not_allowed_from_running"


def test_computer_use_runner_stops_while_awaiting_approval(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    job_id = "job-runtime-approval-stop"
    config = RuntimeConfig.from_profile("default").model_copy(
        update={
            "governance": RuntimeConfig.from_profile("default").governance.model_copy(
                update={"approval_store_path": str(tmp_path / "approvals.sqlite3")}
            )
        }
    )
    desktop = _FakeDesktopAdapter()
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )
    outcome: dict[str, object] = {}

    def worker() -> None:
        try:
            outcome["payload"] = runner.run(
                prompt='open "https://ops.example.internal/queue"\nclick "#submit"',
                job_id=job_id,
                mode=ComputerUseMode.EXECUTE,
            )
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    status_path = root_dir / job_id / "status.json"
    _wait_until(
        lambda: status_path.exists()
        and json.loads(status_path.read_text(encoding="utf-8"))["computer_use"]["session_state"]
        == SessionExecutionState.AWAITING_APPROVAL.value
    )
    control_runner = ComputerUseRunner(config=config, root_dir=root_dir)
    stop_result = control_runner.request_control(job_id=job_id, command=SessionCommand.STOP)
    assert stop_result["outcome"] == "accepted"
    thread.join(timeout=5.0)

    assert not thread.is_alive()
    assert "error" in outcome
    status_payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert status_payload["computer_use"]["session_state"] == SessionExecutionState.STOPPED.value
    assert status_payload["computer_use"]["stopped_by_user"] is True


def test_computer_use_runner_loads_recovery_state_for_paused_session(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    job_id = "job-runtime-recovery-paused"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    control_runner = ComputerUseRunner(config=config, root_dir=root_dir)

    def request_pause(action: ProposedAction) -> None:
        if action.action_id == "open_url":
            control_runner.request_control(job_id=job_id, command=SessionCommand.PAUSE)

    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop, on_verified=request_pause),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )
    outcome: dict[str, object] = {}

    def worker() -> None:
        try:
            outcome["payload"] = runner.run(
                prompt=(
                    'open "https://ops.example.internal/queue"\n'
                    'wait "0.5"\n'
                    'type "ImperaOS Operator" into "#name"'
                ),
                job_id=job_id,
                mode=ComputerUseMode.EXECUTE,
            )
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    status_path = root_dir / job_id / "status.json"
    _wait_until(
        lambda: status_path.exists()
        and json.loads(status_path.read_text(encoding="utf-8"))["computer_use"][
            "session_state"
        ]
        == SessionExecutionState.PAUSED.value
        and (root_dir / job_id / "events.jsonl").exists(),
        timeout_s=10.0,
    )

    recovery = control_runner.load_recovery_state(job_id=job_id)
    assert recovery["recoverable_state"] == SessionExecutionState.PAUSED.value
    assert recovery["resume_allowed"] is True
    assert recovery["last_completed_action_index"] == 0

    event_names = _read_event_names(root_dir / job_id / "events.jsonl")
    assert "computer_use.recovery_loaded" in event_names

    control_runner.request_control(job_id=job_id, command=SessionCommand.RESUME)
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert "error" not in outcome


def test_computer_use_runner_marks_active_recovery_as_not_resumable(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    job_id = "job-runtime-recovery-running"
    config = RuntimeConfig.from_profile("default")
    desktop = _FakeDesktopAdapter()
    runner = ComputerUseRunner(
        config=config,
        root_dir=root_dir,
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop, wait_delay_s=0.4),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path]),
        ),
    )
    outcome: dict[str, object] = {}

    def worker() -> None:
        try:
            outcome["payload"] = runner.run(
                prompt=(
                    'open "https://ops.example.internal/queue"\n'
                    'wait "0.4"\n'
                    'type "ImperaOS Operator" into "#name"'
                ),
                job_id=job_id,
                mode=ComputerUseMode.EXECUTE,
            )
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    events_path = root_dir / job_id / "events.jsonl"
    _wait_until(
        lambda: events_path.exists()
        and _read_event_names(events_path).count("action_started") >= 2,
        timeout_s=10.0,
    )
    control_runner = ComputerUseRunner(config=config, root_dir=root_dir)
    recovery = control_runner.load_recovery_state(job_id=job_id)
    assert recovery["recoverable_state"] == SessionExecutionState.RUNNING.value
    assert recovery["resume_allowed"] is False

    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert "error" not in outcome
    assert "computer_use.recovery_not_resumable" in _read_event_names(events_path)


def test_computer_use_readiness_report_flags_safari_javascript_blocker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir()
    desktop = _FakeDesktopAdapter()
    runner = ComputerUseRunner(
        config=RuntimeConfig.from_profile("default"),
        root_dir=tmp_path / "jobs",
        adapters=RuntimeAdapters(
            browser=_FakeBrowserAdapter(desktop=desktop),
            desktop=desktop,
            dialog=FileDialogAdapter(allowed_roots=[tmp_path, downloads_dir]),
        ),
    )

    monkeypatch.setattr(
        "imperaos.computer_use.runtime.current_platform",
        lambda: SimpleNamespace(
            system="Darwin",
            label="macos",
            machine="arm64",
            release="23.0.0",
        ),
    )
    monkeypatch.setattr(
        "imperaos.computer_use.runtime.shutil.which",
        lambda name: "/usr/bin/osascript" if name == "osascript" else None,
    )

    class _Proc:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(
        "imperaos.computer_use.runtime.subprocess.run",
        lambda *args, **kwargs: _Proc(),
    )

    def fake_run_applescript(script: str, *, timeout_s: float = 15.0) -> str:
        del timeout_s
        if "return version" in script:
            return "18.4"
        if "UI elements enabled" in script:
            return "true"
        if 'do JavaScript "document.readyState"' in script:
            raise MacOSAutomationError(
                "Safari got an error: Allow JavaScript from Apple Events is disabled."
            )
        return ""

    monkeypatch.setattr(
        "imperaos.computer_use.runtime.run_applescript",
        fake_run_applescript,
    )

    report = runner.readiness_report()
    js_check = next(
        item
        for item in report["checks"]
        if item["key"] == "safari_javascript_apple_events"
    )
    assert any(item["key"] == "finder" for item in report["checks"])
    assert any(item["key"] == "textedit" for item in report["checks"])
    assert report["status"] == "blocked"
    assert js_check["status"] == "fail"
    assert "Allow JavaScript from Apple Events" in js_check["remediation"]


def test_computer_use_doctor_classifies_surface_mismatch(monkeypatch, tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    root_dir.mkdir()
    job_id = "cu-doctor-surface"
    job_dir = root_dir / job_id
    job_dir.mkdir()
    (job_dir / "status.json").write_text(
        json.dumps(
            {
                "job": {
                    "job_id": job_id,
                    "case_id": f"case-{job_id}",
                    "team_id": "imperaos-computer-use",
                    "status": "failed",
                },
                "computer_use": {
                    "session_state": "failed",
                    "lifecycle_state": "failed",
                    "stopped_by_user": False,
                    "surface_mismatch": {
                        "code": "wrong_tab",
                        "message": (
                            "Runtime stopped because the active tab drifted "
                            "away from the expected URL."
                        ),
                    },
                    "last_control_result": {},
                    "last_verification_result": {},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    runner = ComputerUseRunner(
        config=RuntimeConfig.from_profile("default"),
        root_dir=root_dir,
    )
    monkeypatch.setattr(
        runner,
        "_build_readiness_report",
        lambda: ReadinessReport(
            status=ComputerUseReadinessStatus.READY,
            summary="This machine is ready for the pilot.",
            checked_at="2026-03-14T10:10:00Z",
            checks=[],
        ),
    )

    report = runner.doctor(job_id=job_id)
    assert report["status"] == "blocked"
    assert report["surface_mismatch_code"] == "wrong_tab"
    assert report["job_id"] == job_id
    assert "expected tab" in report["remediation"]


def test_computer_use_summary_aggregates_recent_outcomes(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    root_dir.mkdir()
    fixtures = [
        (
            "cu-summary-success",
            {
                "job": {
                    "job_id": "cu-summary-success",
                    "status": "completed",
                    "finished_at": "2026-03-14T10:00:00Z",
                },
                "computer_use": {"session_state": "completed"},
            },
        ),
        (
            "cu-summary-blocked",
            {
                "job": {
                    "job_id": "cu-summary-blocked",
                    "status": "blocked",
                    "finished_at": "2026-03-14T10:05:00Z",
                },
                "computer_use": {
                    "session_state": "awaiting_approval",
                    "last_control_result": {"reason": "approval_not_executed"},
                },
            },
        ),
        (
            "cu-summary-failed",
            {
                "job": {
                    "job_id": "cu-summary-failed",
                    "status": "failed",
                    "finished_at": "2026-03-14T10:10:00Z",
                },
                "computer_use": {
                    "session_state": "failed",
                    "surface_mismatch": {"code": "wrong_tab"},
                },
            },
        ),
        (
            "cu-summary-stopped",
            {
                "job": {
                    "job_id": "cu-summary-stopped",
                    "status": "failed",
                    "finished_at": "2026-03-14T10:15:00Z",
                },
                "computer_use": {
                    "session_state": "stopped",
                    "stopped_by_user": True,
                },
            },
        ),
    ]
    for index, (job_id, payload) in enumerate(fixtures):
        job_dir = root_dir / job_id
        job_dir.mkdir()
        status_path = job_dir / "status.json"
        status_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        touched = 1_700_000_000 + index
        os.utime(status_path, (touched, touched))

    runner = ComputerUseRunner(config=RuntimeConfig.from_profile("default"), root_dir=root_dir)
    summary = runner.summary(limit=4)
    assert summary["counts"] == {
        "success": 1,
        "blocked": 1,
        "failed": 1,
        "stopped": 1,
        "active": 0,
    }
    assert summary["top_failure_codes"][0]["code"] in {"wrong_tab", "approval_not_executed"}
    assert summary["last_success_at"] == "2026-03-14T10:00:00Z"
