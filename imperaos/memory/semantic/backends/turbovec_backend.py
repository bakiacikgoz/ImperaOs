from __future__ import annotations

import importlib.util

from imperaos.memory.semantic.backends.null_backend import NullSemanticBackend
from imperaos.memory.semantic.models import SemanticIndexStatus


class TurboVecSemanticBackend(NullSemanticBackend):
    backend_kind = "turbovec"

    @staticmethod
    def dependency_available() -> bool:
        return importlib.util.find_spec("turbovec") is not None

    def status(self, workspace_id: str) -> SemanticIndexStatus:
        if not self.dependency_available():
            return SemanticIndexStatus(
                status="unavailable_optional",
                enabled=False,
                backendKind="turbovec",
                workspaceId=workspace_id,
                reasonCodes=("MEMORY_TURBOVEC_OPTIONAL_DEPENDENCY_MISSING",),
            )
        return SemanticIndexStatus(
            status="blocked",
            enabled=False,
            backendKind="turbovec",
            workspaceId=workspace_id,
            reasonCodes=("MEMORY_TURBOVEC_EXPERIMENTAL_DISABLED",),
        )
