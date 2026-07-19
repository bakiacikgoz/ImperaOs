from __future__ import annotations

ALLOWED_COMMANDS = {
    "rg",
    "ruff",
    "pytest",
    "python",
    "uv",
}


def is_allowed_command(command: list[str]) -> bool:
    if not command:
        return False
    return command[0] in ALLOWED_COMMANDS
