from __future__ import annotations

from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Keep wheel resources from shadowing exact editable package redirects."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if version == "editable":
            build_data["force_include_editable"] = {"config": "config"}
