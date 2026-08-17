from __future__ import annotations

import base64
import json
import os
import shutil
import struct
import subprocess
import zlib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from imperaos.computer_use.vision_runtime.providers.ollama_vision import (
    OllamaVisionResponse,
    parse_ollama_response,
)

ProviderClient = Callable[..., Any]
ModelLister = Callable[[], set[str]]


def doctor_vision_provider(
    *,
    provider: str,
    model: str | None,
    synthetic_fixture: bool,
    timeout_s: float = 30.0,
    max_retries: int = 1,
    client: ProviderClient | None = None,
    model_lister: ModelLister | None = None,
    which: Callable[[str], str | None] = shutil.which,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    normalized_provider = provider.strip().lower()
    fixture = _synthetic_fixture_metadata()
    base = {
        "artifactVersion": "computer_use_provider_doctor/v1",
        "status": "blocked",
        "provider": normalized_provider,
        "kind": normalized_provider,
        "model": model,
        "modelConfigured": bool(model),
        "modelPresent": False,
        "visionInputAccepted": False,
        "strictJsonPass": False,
        "schemaValidationPass": False,
        "timeoutMs": int(timeout_s * 1000),
        "stage": "blocked",
        "ready": False,
        "strictJsonValidated": False,
        "syntheticFixture": fixture["public"],
        "localOnly": True,
        "createdAt": datetime.now(UTC).isoformat(),
        "reasonCode": None,
        "checks": {
            "provider_supported": normalized_provider == "ollama",
            "model_configured": bool(model),
            "synthetic_fixture": synthetic_fixture,
            "local_endpoint": _local_ollama_endpoint(environment or os.environ),
            "strict_json_contract": False,
        },
    }

    if normalized_provider != "ollama":
        return _blocked(base, "VISION_PROVIDER_UNAVAILABLE")
    if not model:
        return _blocked(base, "VISION_PROVIDER_MODEL_NOT_CONFIGURED")
    if not synthetic_fixture:
        return _blocked(base, "VISION_PROVIDER_INVALID_RESPONSE")
    if not base["checks"]["local_endpoint"]:
        return _blocked(base, "VISION_PROVIDER_UNAVAILABLE")
    if client is None and which("ollama") is None:
        return _blocked(base, "VISION_PROVIDER_UNAVAILABLE")

    models = (
        model_lister()
        if model_lister is not None
        else {model}
        if client is not None
        else _list_ollama_models()
    )
    model_present = _model_present(model, models)
    base["modelPresent"] = model_present
    base["checks"]["model_present"] = model_present
    if not model_present:
        return _blocked(base, "VISION_PROVIDER_MODEL_NOT_FOUND")

    active_client = client or _ollama_generate_client
    prompt = _synthetic_provider_prompt(fixture["public"])
    last_error: BaseException | None = None
    for _attempt in range(max_retries + 1):
        try:
            raw = active_client(
                model=model,
                prompt=prompt,
                timeout_s=timeout_s,
                image_base64=fixture["imageBase64"],
            )
            parsed = _parse_provider_doctor_response(raw)
            base["status"] = "pass"
            base["stage"] = "ready"
            base["ready"] = True
            base["modelConfigured"] = True
            base["modelPresent"] = True
            base["visionInputAccepted"] = True
            base["strictJsonPass"] = True
            base["schemaValidationPass"] = True
            base["strictJsonValidated"] = True
            base["checks"]["strict_json_contract"] = True
            base["reasonCode"] = None
            base["response"] = {
                "surfaceKind": parsed.surface_kind.value,
                "uiElementCount": len(parsed.ui_elements),
                "sensitiveIndicatorCount": len(parsed.sensitive_indicators),
                "confidence": parsed.confidence,
            }
            return base
        except TimeoutError:
            return _blocked(base, "VISION_PROVIDER_TIMEOUT")
        except _ProviderNotVisionCapable:
            return _blocked(base, "VISION_PROVIDER_NOT_VISION_CAPABLE")
        except _ProviderInvalidResponse:
            return _blocked(base, "VISION_PROVIDER_INVALID_RESPONSE")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if _looks_like_timeout(exc):
                return _blocked(base, "VISION_PROVIDER_TIMEOUT")
            if _looks_like_model_not_found(exc):
                return _blocked(base, "VISION_PROVIDER_MODEL_NOT_FOUND")
            if _looks_like_vision_rejection(exc):
                return _blocked(base, "VISION_PROVIDER_NOT_VISION_CAPABLE")
            continue
    payload = _blocked(base, "VISION_PROVIDER_UNAVAILABLE")
    payload["errorType"] = type(last_error).__name__ if last_error is not None else None
    return payload


def _blocked(payload: dict[str, Any], reason_code: str) -> dict[str, Any]:
    payload = dict(payload)
    payload["status"] = "blocked"
    payload["stage"] = "blocked"
    payload["ready"] = False
    payload["visionInputAccepted"] = False
    payload["strictJsonPass"] = False
    payload["schemaValidationPass"] = False
    payload["strictJsonValidated"] = False
    payload["reasonCode"] = reason_code
    return payload


class _ProviderInvalidResponse(RuntimeError):
    pass


class _ProviderNotVisionCapable(RuntimeError):
    pass


def _parse_provider_doctor_response(raw: Any) -> OllamaVisionResponse:
    try:
        parsed = parse_ollama_response(raw)
    except Exception as exc:  # noqa: BLE001
        raise _ProviderInvalidResponse from exc
    if not parsed.ui_elements:
        raise _ProviderNotVisionCapable
    return parsed


def _ollama_generate_client(
    *,
    model: str,
    prompt: str,
    timeout_s: float,
    image_base64: str,
) -> Any:
    try:
        import ollama
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("ollama python client is unavailable") from exc
    client = ollama.Client(timeout=timeout_s)
    return client.generate(
        model=model,
        prompt=prompt,
        images=[image_base64],
        format="json",
        options={"temperature": 0},
    )


def _synthetic_provider_prompt(fixture: Mapping[str, Any]) -> str:
    return (
        "Inspect this local synthetic fixture image. Return strict JSON only with "
        "surface_kind, active_app_guess, active_window_title_guess, "
        "visible_text_redacted, ui_elements, sensitive_indicators, candidate_actions, "
        "summary, and confidence. candidate_actions may be an empty list for this "
        "readiness check. This is a non-sensitive local readiness check. "
        f"Fixture metadata: {json.dumps(dict(fixture), sort_keys=True)}"
    )


def _synthetic_fixture_metadata() -> dict[str, Any]:
    width = 320
    height = 180
    png = _fixture_png(width=width, height=height)
    digest = sha256(png).hexdigest()
    return {
        "imageBase64": base64.b64encode(png).decode("ascii"),
        "public": {
            "kind": "synthetic_local_fixture_png",
            "screenshotHash": f"sha256:{digest}",
            "dimensions": [width, height],
            "redacted": True,
            "rawPersisted": False,
        },
    }


def _fixture_png(*, width: int, height: int) -> bytes:
    rows: list[bytes] = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            red, green, blue = 245, 247, 250
            if 24 <= x <= 296 and 28 <= y <= 60:
                red, green, blue = 220, 235, 255
            if 42 <= x <= 190 and 84 <= y <= 112:
                red, green, blue = 255, 255, 255
            if 202 <= x <= 278 and 84 <= y <= 112:
                red, green, blue = 35, 110, 210
            if 42 <= x <= 278 and 132 <= y <= 146:
                red, green, blue = 232, 238, 245
            row.extend((red, green, blue))
        rows.append(b"\x00" + bytes(row))
    raw = b"".join(rows)
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        signature
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind)
    crc = zlib.crc32(data, crc)
    return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", crc & 0xFFFFFFFF)


def _local_ollama_endpoint(environment: Mapping[str, str]) -> bool:
    value = environment.get("OLLAMA_HOST", "").strip()
    if not value:
        return True
    lowered = value.lower()
    allowed = (
        lowered.startswith("http://127.0.0.1")
        or lowered.startswith("http://localhost")
        or lowered.startswith("https://127.0.0.1")
        or lowered.startswith("https://localhost")
        or lowered.startswith("127.0.0.1")
        or lowered.startswith("localhost")
    )
    return allowed


def _list_ollama_models() -> set[str]:
    try:
        proc = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    if proc.returncode != 0:
        return set()
    models: set[str] = set()
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split()
        if parts:
            models.add(parts[0])
    return models


def _model_present(model: str, models: set[str]) -> bool:
    normalized = model.strip()
    if normalized in models:
        return True
    if ":" not in normalized and f"{normalized}:latest" in models:
        return True
    return any(candidate.split(":", maxsplit=1)[0] == normalized for candidate in models)


def _looks_like_timeout(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    return "timeout" in name or "timed out" in message or "timeout" in message


def _looks_like_model_not_found(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "not found" in message or "model not found" in message or "pull model" in message


def _looks_like_vision_rejection(exc: BaseException) -> bool:
    message = str(exc).lower()
    return (
        "image" in message
        and (
            "unsupported" in message
            or "does not support" in message
            or "vision" in message
            or "multi-modal" in message
            or "multimodal" in message
        )
    )
