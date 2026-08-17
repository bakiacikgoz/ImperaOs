from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NoReturn

from imperaos.artifacts.rpc_server import ArtifactRpcServer
from imperaos.artifacts.service import ArtifactService


def _artifact_root(argv: list[str]) -> Path:
    try:
        root_index = argv.index("--root") + 1
        return Path(argv[root_index])
    except (ValueError, IndexError) as exc:
        raise SystemExit("ARTIFACT_RPC_UNAVAILABLE") from exc


def _exit_after_published_revision(
    server: ArtifactRpcServer,
    *,
    revision_number: int,
) -> None:
    store = server.service.store
    publish_content = store._publish_content
    marker = store.filesystem.root / f"crash-after-publish-{revision_number}.once"

    def crash_once(revision: object, content: bytes) -> NoReturn | None:
        publish_content(revision, content)  # type: ignore[arg-type]
        if getattr(revision, "revision_number", None) != revision_number or marker.exists():
            return None
        marker.write_text("injected", encoding="ascii")
        os._exit(91)

    store._publish_content = crash_once  # type: ignore[method-assign]


def main(argv: list[str]) -> int:
    root = _artifact_root(argv)
    server = ArtifactRpcServer(ArtifactService(root))
    configured_revision = os.environ.get(
        "IMPERAOS_ARTIFACT_CRASH_AFTER_PUBLISH_REVISION"
    )
    if configured_revision is not None:
        _exit_after_published_revision(
            server,
            revision_number=int(configured_revision),
        )
    return server.serve(sys.stdin.buffer, sys.stdout.buffer, sys.stderr.buffer)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
