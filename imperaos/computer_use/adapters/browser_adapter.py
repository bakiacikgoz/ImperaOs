from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from imperaos.computer_use.adapters._macos import applescript_quote, run_applescript
from imperaos.computer_use.adapters.desktop_adapter import DesktopAdapter
from imperaos.computer_use.adapters.dialog_adapter import FileDialogAdapter
from imperaos.computer_use.models import (
    EvidenceEnvelope,
    PerceptionSnapshot,
    PerceptionSource,
    ProposedAction,
    SelectorContext,
    SurfaceObservation,
    TargetDescriptor,
    VerificationResult,
)
from imperaos.computer_use.perception import build_perception_fingerprint


class BrowserAdapter(ABC):
    adapter_status = "scaffold_only"

    @abstractmethod
    def observe_surface(self, *, target: TargetDescriptor | None = None) -> SurfaceObservation:
        raise NotImplementedError

    @abstractmethod
    def inspect_target(self, *, target: TargetDescriptor) -> PerceptionSnapshot:
        raise NotImplementedError

    @abstractmethod
    def execute(self, *, action: ProposedAction) -> dict[str, Any]:
        raise NotImplementedError

    def verify(
        self,
        *,
        action: ProposedAction,
        before: PerceptionSnapshot | None = None,
    ) -> VerificationResult:
        raise NotImplementedError


class ScaffoldBrowserAdapter(BrowserAdapter):
    def observe_surface(self, *, target: TargetDescriptor | None = None) -> SurfaceObservation:
        del target
        raise NotImplementedError("browser adapter scaffold only")

    def inspect_target(self, *, target: TargetDescriptor) -> PerceptionSnapshot:
        del target
        raise NotImplementedError("browser adapter scaffold only")

    def execute(self, *, action: ProposedAction) -> dict[str, Any]:
        del action
        raise NotImplementedError("browser adapter scaffold only")

    def verify(
        self,
        *,
        action: ProposedAction,
        before: PerceptionSnapshot | None = None,
    ) -> VerificationResult:
        del action, before
        raise NotImplementedError("browser adapter scaffold only")


class SafariBrowserAdapter(BrowserAdapter):
    adapter_status = "safari_applescript"

    def __init__(
        self,
        *,
        desktop_adapter: DesktopAdapter | None = None,
        dialog_adapter: FileDialogAdapter | None = None,
        app_name: str = "Safari",
        download_dir: str | Path | None = None,
        wait_timeout_s: float = 20.0,
    ) -> None:
        self._desktop = desktop_adapter or DesktopAdapter()
        self._dialog = dialog_adapter
        self._app_name = app_name
        self._download_dir = (
            Path(download_dir).expanduser().resolve()
            if download_dir is not None
            else Path.home().joinpath("Downloads").resolve()
        )
        self._wait_timeout_s = wait_timeout_s

    def observe_surface(self, *, target: TargetDescriptor | None = None) -> SurfaceObservation:
        selector = target.selector if target is not None else "document"
        desktop_surface = self._desktop.observe_surface(self._app_name)
        state = self._safe_page_state(selector=selector or "document")
        selector_count = int(state.get("selectorCount") or 0)
        visible_selectors: list[str] | None = None
        if selector and selector not in {"document", "window"}:
            visible_selectors = [selector] if selector_count >= 1 else []
        return SurfaceObservation(
            foreground_app=desktop_surface.foreground_app,
            bundle_id=desktop_surface.bundle_id,
            focused_window_title=desktop_surface.focused_window_title,
            active_tab_url=str(state.get("url") or "") or None,
            active_tab_title=(
                str(state.get("title") or desktop_surface.focused_window_title or "") or None
            ),
            modal_detected=desktop_surface.modal_detected or bool(state.get("hasModal")),
            visible_selectors=visible_selectors,
            captured_at=datetime.now(UTC).isoformat(),
        )

    def inspect_target(self, *, target: TargetDescriptor) -> PerceptionSnapshot:
        self._ensure_browser()
        state = self._page_state(selector=target.selector)
        current_url = str(state.get("url") or target.current_url)
        title = str(state.get("title") or "")
        selector_count = int(state.get("selectorCount") or 0)
        focused = self._desktop.frontmost_app() == self._app_name
        unexpected_modal = self._desktop.detect_dialog(self._app_name) or bool(
            state.get("hasModal")
        )
        confidence = 0.98 if selector_count == 1 or target.selector == "document" else 0.42
        selector_context = SelectorContext(
            selector=target.selector,
            selector_source=target.selector_source,
            selector_trace=[target.selector] if target.selector else [],
        )
        screenshot_hash = hashlib.sha256(
            f"{current_url}|{title}|{target.selector}|{selector_count}".encode()
        ).hexdigest()
        perception_fingerprint = build_perception_fingerprint(
            window_or_tab_identity=f"safari:{title or 'untitled'}",
            app_identity="browser:safari",
            selector_context=selector_context.model_dump(mode="json"),
            screenshot_hash=screenshot_hash,
        )
        return PerceptionSnapshot(
            source=PerceptionSource.DOM,
            confidence=confidence,
            perception_fingerprint=perception_fingerprint,
            sensitive_surface=False,
            focused=focused,
            unexpected_modal=unexpected_modal,
            selector_ambiguous=selector_count > 1,
            window_or_tab_identity=f"safari:{title or 'untitled'}",
            app_identity="browser:safari",
            current_url=current_url,
            selector_context=selector_context,
            evidence=EvidenceEnvelope(
                screenshot_hash=screenshot_hash,
                redacted_fingerprint=hashlib.sha256(
                    f"{current_url}|{title}|{selector_count}".encode()
                ).hexdigest(),
                accessibility_subset={
                    "title": title,
                    "selector_count": selector_count,
                    "tag_name": state.get("tagName"),
                    "value": state.get("value"),
                    "ready_state": state.get("readyState"),
                    "file_name": state.get("fileName"),
                    "scroll_top": state.get("scrollTop"),
                    "window_scroll_y": state.get("windowScrollY"),
                    "has_modal": state.get("hasModal"),
                },
            ),
        )

    def execute(self, *, action: ProposedAction) -> dict[str, Any]:
        self._ensure_browser()
        if action.action_id == "open_url":
            url = str(action.parameters.get("url") or action.target_descriptor.current_url)
            self._open_url(url=url, new_tab=bool(action.parameters.get("new_tab")))
            self._wait_until_ready(url=url)
            return {"status": "executed", "url": self.current_url(), "title": self.current_title()}

        if action.action_id == "switch_tab":
            url = str(action.parameters.get("url") or action.target_descriptor.current_url)
            self._open_url(url=url, new_tab=True)
            self._wait_until_ready(url=url)
            return {"status": "executed", "url": self.current_url(), "title": self.current_title()}

        if action.action_id == "click":
            self._eval_js(
                """
(() => {
  const el = document.querySelector(SELECTOR);
  if (!el) throw new Error("selector_not_found");
  el.click();
  return JSON.stringify({clicked: true, tagName: el.tagName});
})()
""",
                selector=action.target_descriptor.selector,
            )
            time.sleep(0.15)
            return {"status": "executed"}

        if action.action_id == "type_text":
            text = str(action.parameters.get("text") or "")
            self._eval_js(
                """
(() => {
  const el = document.querySelector(SELECTOR);
  if (!el) throw new Error("selector_not_found");
  el.focus();
  el.value = VALUE;
  el.dispatchEvent(new Event("input", {bubbles: true}));
  el.dispatchEvent(new Event("change", {bubbles: true}));
  return JSON.stringify({value: el.value});
})()
""",
                selector=action.target_descriptor.selector,
                value=text,
            )
            return {"status": "executed", "value": text}

        if action.action_id == "select_option":
            value = str(action.parameters.get("value") or "")
            self._eval_js(
                """
(() => {
  const el = document.querySelector(SELECTOR);
  if (!el) throw new Error("selector_not_found");
  const option = Array.from(el.options).find((item) => item.value === VALUE || item.text === VALUE);
  if (!option) throw new Error("option_not_found");
  el.value = option.value;
  el.dispatchEvent(new Event("change", {bubbles: true}));
  return JSON.stringify({value: el.value});
})()
""",
                selector=action.target_descriptor.selector,
                value=value,
            )
            return {"status": "executed", "value": value}

        if action.action_id == "scroll":
            amount = int(action.parameters.get("amount") or 0)
            selector = action.target_descriptor.selector
            if selector == "window":
                self._eval_js(
                    """
(() => {
  window.scrollTo({top: AMOUNT, behavior: "instant"});
  return JSON.stringify({top: window.scrollY});
})()
""",
                    amount=amount,
                )
            else:
                self._eval_js(
                    """
(() => {
  const el = document.querySelector(SELECTOR);
  if (!el) throw new Error("selector_not_found");
  el.scrollTop = AMOUNT;
  return JSON.stringify({top: el.scrollTop});
})()
""",
                    selector=selector,
                    amount=amount,
                )
            return {"status": "executed", "amount": amount}

        if action.action_id == "upload_file":
            if self._dialog is None:
                raise RuntimeError("file dialog adapter unavailable")
            path = str(action.parameters.get("path") or "")
            self._eval_js(
                """
(() => {
  const el = document.querySelector(SELECTOR);
  if (!el) throw new Error("selector_not_found");
  el.click();
  return JSON.stringify({clicked: true});
})()
""",
                selector=action.target_descriptor.selector,
            )
            self._wait_for_dialog_state(open_expected=True)
            selected = self._dialog.choose_file(app_name=self._app_name, path=path)
            self._wait_for_dialog_state(open_expected=False)
            time.sleep(0.35)
            self._wait_for_file_input(
                selector=action.target_descriptor.selector,
                expected_name=Path(selected).name,
            )
            return {
                "status": "executed",
                "selected_file": selected,
                "selected_file_name": Path(selected).name,
                "dialog_interacted": True,
            }

        if action.action_id == "download_file":
            output_path = action.parameters.get("output_path")
            if output_path and self._dialog is not None:
                return self._download_via_dom(
                    selector=action.target_descriptor.selector,
                    output_path=str(output_path),
                )
            known = {
                item.name
                for item in self._download_dir.glob("*")
                if item.is_file() and not item.name.endswith(".download")
            }
            self._eval_js(
                """
(() => {
  const el = document.querySelector(SELECTOR);
  if (!el) throw new Error("selector_not_found");
  el.click();
  return JSON.stringify({clicked: true});
})()
""",
                selector=action.target_descriptor.selector,
            )
            if self._dialog is not None and self._desktop.detect_dialog(self._app_name):
                self._dialog.confirm_dialog(app_name=self._app_name)
            downloaded = (
                self._dialog.wait_for_download(
                    download_dir=self._download_dir,
                    known_files=known,
                    timeout_s=self._wait_timeout_s,
                )
                if self._dialog is not None
                else _wait_for_download(
                    download_dir=self._download_dir,
                    known_files=known,
                    timeout_s=self._wait_timeout_s,
                )
            )
            if output_path and self._dialog is not None:
                moved = self._dialog.move_file_scoped(
                    source=downloaded,
                    destination=str(output_path),
                )
                return {
                    "status": "executed",
                    "download_path": moved,
                    "download_triggered": True,
                    "dialog_interacted": bool(self._dialog is not None),
                }
            return {
                "status": "executed",
                "download_path": str(downloaded),
                "download_triggered": True,
                "dialog_interacted": bool(self._dialog is not None),
            }

        if action.action_id == "wait":
            time.sleep(float(action.parameters.get("seconds") or 0))
            return {"status": "executed"}

        raise RuntimeError(f"unsupported browser action: {action.action_id}")

    def verify(
        self,
        *,
        action: ProposedAction,
        before: PerceptionSnapshot | None = None,
    ) -> VerificationResult:
        self._ensure_browser()
        kind = action.verification_kind
        expected = action.verification_value or ""
        if not kind:
            return VerificationResult(
                verified=True,
                kind="none",
                summary="No additional verification was requested.",
            )

        before_state = self._before_state(before)
        if kind == "url":
            after_state = self._page_state(selector="document")
            return self._verify_url(expected_url=expected, after_state=after_state)
        if kind == "selector_present":
            state = self._page_state(selector=action.target_descriptor.selector)
            selector_count = int(state.get("selectorCount") or 0)
            changed = self._click_changed(before_state=before_state, after_state=state)
            verified = selector_count >= 1 and changed
            return VerificationResult(
                verified=verified,
                kind=kind,
                summary=(
                    "Click produced a visible surface change."
                    if verified
                    else "Click did not produce a visible state transition."
                ),
                expected={"selector": action.target_descriptor.selector, "state_change": True},
                observed={
                    "selector_count": selector_count,
                    "current_url": str(state.get("url") or ""),
                    "title": str(state.get("title") or ""),
                    "has_modal": bool(state.get("hasModal")),
                },
                mismatch_code=None if verified else "no_state_change_after_click",
                retryable=not verified,
            )
        if kind == "value":
            state = self._page_state(selector=action.target_descriptor.selector)
            current_value = str(state.get("value") or "")
            verified = current_value == expected
            return VerificationResult(
                verified=verified,
                kind=kind,
                summary=(
                    "Observed value matches the requested input."
                    if verified
                    else "Observed value does not match the requested input."
                ),
                expected={"value": expected},
                observed={"value": current_value},
                mismatch_code=None if verified else "value_mismatch",
                retryable=not verified,
            )
        if kind == "scroll":
            state = self._page_state(selector=action.target_descriptor.selector)
            current = (
                int(state.get("scrollTop") or 0)
                if action.target_descriptor.selector != "window"
                else int(state.get("windowScrollY") or 0)
            )
            expected_amount = int(expected)
            verified = current == expected_amount
            return VerificationResult(
                verified=verified,
                kind=kind,
                summary=(
                    "Scroll offset matches the requested position."
                    if verified
                    else "Scroll offset does not match the requested position."
                ),
                expected={"scroll": expected_amount},
                observed={"scroll": current},
                mismatch_code=None if verified else "scroll_mismatch",
                retryable=not verified,
            )
        if kind == "file_selected":
            state = self._page_state(selector=action.target_descriptor.selector)
            current = str(state.get("fileName") or "")
            verified = current == expected
            return VerificationResult(
                verified=verified,
                kind=kind,
                summary=(
                    "Selected file is reflected by the target input."
                    if verified
                    else "Selected file is not reflected by the target input."
                ),
                expected={"file_name": expected},
                observed={"file_name": current},
                mismatch_code=None if verified else "file_selection_missing",
                retryable=not verified,
            )
        if kind == "download":
            triggered = bool(
                action.execution_result.get("download_triggered")
                or action.execution_result.get("download_path")
            )
            return VerificationResult(
                verified=triggered,
                kind=kind,
                summary=(
                    "Download action produced a filesystem handoff signal."
                    if triggered
                    else "Download action did not produce a handoff signal."
                ),
                expected={"download_triggered": True, "path": str(expected or "")},
                observed={
                    "download_triggered": triggered,
                    "path": str(action.execution_result.get("download_path") or ""),
                },
                mismatch_code=None if triggered else "download_not_triggered",
                retryable=not triggered,
            )
        return VerificationResult(
            verified=False,
            kind=kind,
            summary=f"Unknown verification kind: {kind}.",
            mismatch_code=f"unknown_verification_kind:{kind}",
            retryable=False,
        )

    def current_url(self) -> str:
        script = (
            f'tell application {applescript_quote(self._app_name)} '
            "to return URL of current tab of front window"
        )
        return run_applescript(script)

    def current_title(self) -> str:
        script = (
            f'tell application {applescript_quote(self._app_name)} '
            "to return name of current tab of front window"
        )
        return run_applescript(script)

    def _before_state(self, before: PerceptionSnapshot | None) -> dict[str, Any]:
        if before is None:
            return {}
        accessibility = before.evidence.accessibility_subset or {}
        return {
            "url": before.current_url,
            "title": str(accessibility.get("title") or ""),
            "value": str(accessibility.get("value") or ""),
            "selectorCount": int(accessibility.get("selector_count") or 0),
            "fileName": str(accessibility.get("file_name") or ""),
            "scrollTop": int(accessibility.get("scroll_top") or 0),
            "windowScrollY": int(accessibility.get("window_scroll_y") or 0),
            "hasModal": bool(accessibility.get("has_modal")),
            "readyState": str(accessibility.get("ready_state") or ""),
        }

    def _verify_url(
        self,
        *,
        expected_url: str,
        after_state: dict[str, Any],
    ) -> VerificationResult:
        current_url = str(after_state.get("url") or self.current_url())
        current_parsed = urlparse(current_url)
        expected_parsed = urlparse(expected_url)
        host_matches = current_parsed.netloc == expected_parsed.netloc
        path_matches = (
            current_parsed.path == expected_parsed.path
            or current_parsed.path.startswith(expected_parsed.path.rstrip("/"))
        )
        ready = str(after_state.get("readyState") or "") == "complete"
        verified = host_matches and path_matches and ready
        return VerificationResult(
            verified=verified,
            kind="url",
            summary=(
                "Active tab URL and readiness match the requested destination."
                if verified
                else "Active tab URL or readiness does not match the requested destination."
            ),
            expected={
                "url": expected_url,
                "host": expected_parsed.netloc,
                "path": expected_parsed.path or "/",
                "ready_state": "complete",
            },
            observed={
                "url": current_url,
                "host": current_parsed.netloc,
                "path": current_parsed.path or "/",
                "ready_state": str(after_state.get("readyState") or ""),
            },
            mismatch_code=None if verified else "url_mismatch",
            retryable=not verified,
        )

    def _click_changed(
        self,
        *,
        before_state: dict[str, Any],
        after_state: dict[str, Any],
    ) -> bool:
        if not before_state:
            return int(after_state.get("selectorCount") or 0) >= 1
        comparable_keys = [
            "url",
            "title",
            "value",
            "selectorCount",
            "fileName",
            "scrollTop",
            "windowScrollY",
            "hasModal",
        ]
        return any(before_state.get(key) != after_state.get(key) for key in comparable_keys)

    def _ensure_browser(self) -> None:
        self._desktop.launch_app(self._app_name)
        self._desktop.focus_window(self._app_name)
        time.sleep(0.2)

    def _open_url(self, *, url: str, new_tab: bool) -> None:
        quoted_app = applescript_quote(self._app_name)
        quoted_url = applescript_quote(url)
        if new_tab:
            script = f"""
tell application {quoted_app}
  activate
  if (count of windows) = 0 then
    make new document with properties {{URL:{quoted_url}}}
  else
    tell front window
      set current tab to (make new tab with properties {{URL:{quoted_url}}})
    end tell
  end if
end tell
"""
        else:
            script = f"""
tell application {quoted_app}
  activate
  if (count of windows) = 0 then
    make new document with properties {{URL:{quoted_url}}}
  else
    set URL of current tab of front window to {quoted_url}
  end if
end tell
"""
        run_applescript(script, timeout_s=15.0)

    def _wait_until_ready(self, *, url: str | None = None) -> None:
        deadline = time.time() + self._wait_timeout_s
        while time.time() < deadline:
            state = self._page_state(selector="document")
            ready = str(state.get("readyState") or "") == "complete"
            current_url = str(state.get("url") or "")
            if ready and (url is None or current_url.startswith(url)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"page did not become ready for {url or 'current page'}")

    def _wait_for_file_input(self, *, selector: str, expected_name: str) -> None:
        deadline = time.time() + self._wait_timeout_s
        while time.time() < deadline:
            state = self._page_state(selector=selector)
            if str(state.get("fileName") or "") == expected_name:
                return
            time.sleep(0.2)
        raise TimeoutError(f"file input did not update for {selector}")

    def _wait_for_dialog_state(
        self,
        *,
        open_expected: bool,
        timeout_s: float | None = None,
    ) -> None:
        deadline = time.time() + (timeout_s or min(self._wait_timeout_s, 5.0))
        while time.time() < deadline:
            if self._desktop.detect_dialog(self._app_name) is open_expected:
                return
            time.sleep(0.1)

    def _download_via_dom(self, *, selector: str, output_path: str) -> dict[str, Any]:
        if self._dialog is None:
            raise RuntimeError("file dialog adapter unavailable")
        target_path = self._dialog.ensure_scoped_path(output_path)
        payload = json.loads(
            self._eval_js(
                """
(() => {
  const el = document.querySelector(SELECTOR);
  if (!el) throw new Error("selector_not_found");
  const href = el.href || el.getAttribute("href") || "";
  if (!href) throw new Error("download_href_missing");
  const suggestedName = el.getAttribute("download") || href.split("/").pop() || "download";
  return JSON.stringify({
    href,
    fileName: suggestedName
  });
})()
""",
                selector=selector,
            )
        )
        request = Request(
            str(payload.get("href") or ""),
            headers={"User-Agent": "ImperaOS/real-acceptance"},
        )
        with urlopen(request, timeout=self._wait_timeout_s) as response:
            content = response.read()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        return {
            "status": "executed",
            "download_path": str(target_path),
            "download_triggered": True,
            "dialog_interacted": False,
            "download_source_url": str(payload.get("href") or ""),
            "download_size_bytes": len(content),
            "download_mode": "direct_request",
        }

    def _safe_page_state(self, *, selector: str) -> dict[str, Any]:
        try:
            return self._page_state(selector=selector, activate=False)
        except RuntimeError:
            return {}

    def _page_state(self, *, selector: str, activate: bool = True) -> dict[str, Any]:
        payload = self._eval_js(
            """
(() => {
  const selector = SELECTOR;
  const nodes = selector === "document"
    ? [document.documentElement]
    : Array.from(document.querySelectorAll(selector));
  const first = nodes[0] || null;
  const fileName = first && first.files && first.files.length > 0 ? first.files[0].name : "";
  return JSON.stringify({
    url: window.location.href,
    title: document.title,
    readyState: document.readyState,
    selectorCount: nodes.length,
    tagName: first ? first.tagName : "",
    value: first && "value" in first ? String(first.value ?? "") : "",
    fileName,
    scrollTop: first && "scrollTop" in first ? Number(first.scrollTop ?? 0) : 0,
    windowScrollY: Number(window.scrollY || 0),
    hasModal: Boolean(
      document.querySelector("dialog[open], [role='dialog'][open], [aria-modal='true']")
    ),
  });
})()
""",
            selector=selector,
            activate=activate,
        )
        return json.loads(payload)

    def _eval_js(self, template: str, *, activate: bool = True, **values: object) -> str:
        script = template
        for key, value in values.items():
            placeholder = key.upper()
            script = script.replace(placeholder, json.dumps(value, ensure_ascii=False))
        activation = "  activate\n" if activate else ""
        applescript = f"""
tell application {applescript_quote(self._app_name)}
{activation}  do JavaScript {applescript_quote(script)} in current tab of front window
end tell
"""
        return run_applescript(applescript, timeout_s=self._wait_timeout_s)


def _wait_for_download(
    *,
    download_dir: Path,
    known_files: set[str],
    timeout_s: float,
) -> Path:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        current = {item.name for item in download_dir.glob("*") if item.is_file()}
        new_files = sorted(current - known_files)
        for candidate in new_files:
            path = download_dir / candidate
            if not path.name.endswith(".download"):
                return path
        time.sleep(0.25)
    raise TimeoutError(f"download not detected in {download_dir}")
