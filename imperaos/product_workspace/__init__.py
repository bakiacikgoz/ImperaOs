"""Durable, workspace-scoped product projects, tasks and assistant correlations."""

from .service import ProductWorkspaceService
from .store import ProductWorkspaceStore

__all__ = ["ProductWorkspaceService", "ProductWorkspaceStore"]
