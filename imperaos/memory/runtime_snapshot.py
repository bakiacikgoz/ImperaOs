from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from imperaos.memory.models import StrictModel
from imperaos.runtime.config import RuntimeConfig


class MemoryRuntimeSnapshot(StrictModel):
    enabled: bool = False
    status: Literal["disabled", "pass", "degraded", "blocked"] = "disabled"
    context_top_k: int = Field(default=0, alias="contextTopK")
    max_context_chars: int = Field(default=0, alias="maxContextChars")
    post_run_write_enabled: bool = Field(default=False, alias="postRunWriteEnabled")
    last_evidence_ref: str | None = Field(default=None, alias="lastEvidenceRef")
    warnings: list[str] = Field(default_factory=list)


class MemorySyncSnapshot(StrictModel):
    enabled: bool = False
    status: Literal["disabled", "pass", "degraded", "blocked"] = "disabled"
    export_raw_content: bool = Field(default=False, alias="exportRawContent")
    import_apply_requires_approval: bool = Field(
        default=True,
        alias="importApplyRequiresApproval",
    )
    allow_cross_environment_import: bool = Field(
        default=False,
        alias="allowCrossEnvironmentImport",
    )
    last_pack_ref: str | None = Field(default=None, alias="lastPackRef")
    warnings: list[str] = Field(default_factory=list)


def build_memory_runtime_snapshot(
    *,
    config: RuntimeConfig,
    evidence_root: str | Path = "artifacts",
    generated_at: datetime | None = None,
) -> MemoryRuntimeSnapshot:
    _ = generated_at
    runtime = config.memory.runtime
    enabled = bool(config.memory.v3_enabled and runtime.enabled)
    warnings: list[str] = []
    if not config.memory.v3_enabled:
        warnings.append("MEMORY_V3_DISABLED")
    if not runtime.enabled:
        warnings.append("MEMORY_RUNTIME_DISABLED")
    evidence_ref = _latest_ref(Path(evidence_root) / "memory-runtime")
    return MemoryRuntimeSnapshot(
        enabled=enabled,
        status="pass" if enabled else "disabled",
        contextTopK=runtime.context_top_k,
        maxContextChars=runtime.max_context_chars,
        postRunWriteEnabled=runtime.post_run_write_enabled,
        lastEvidenceRef=evidence_ref,
        warnings=warnings,
    )


def build_memory_sync_snapshot(
    *,
    config: RuntimeConfig,
    evidence_root: str | Path = "artifacts",
    generated_at: datetime | None = None,
) -> MemorySyncSnapshot:
    _ = generated_at
    sync = config.memory.sync
    warnings: list[str] = []
    if not sync.enabled:
        warnings.append("MEMORY_SYNC_DISABLED")
    if sync.export_raw_content:
        warnings.append("MEMORY_SYNC_RAW_EXPORT_BLOCKED")
    return MemorySyncSnapshot(
        enabled=sync.enabled,
        status="pass" if sync.enabled and not sync.export_raw_content else "disabled",
        exportRawContent=sync.export_raw_content,
        importApplyRequiresApproval=sync.import_apply_requires_approval,
        allowCrossEnvironmentImport=sync.allow_cross_environment_import,
        lastPackRef=_latest_ref(Path(evidence_root) / "memory-sync"),
        warnings=warnings,
    )


def _latest_ref(root: Path) -> str | None:
    if not root.exists():
        return None
    candidates = sorted(root.glob("*.json"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        return None
    return str(candidates[-1])
