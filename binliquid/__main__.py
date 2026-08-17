from __future__ import annotations

import sys

from imperaos.cli import app


def main() -> None:
    print("binliquid is deprecated; use imperaos", file=sys.stderr)
    app(prog_name="binliquid")


if __name__ == "__main__":
    main()
