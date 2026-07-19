from __future__ import annotations

import argparse
import json

from imperaos.memory.sync_pack import export_memory_sync_pack
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="balanced")
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-environment", default="local")
    args = parser.parse_args()
    pack = export_memory_sync_pack(
        config=RuntimeConfig.from_profile(args.profile),
        output_path=args.output,
        source_environment=args.source_environment,
    )
    print(json.dumps(pack.manifest.model_dump(mode="json", by_alias=True), sort_keys=True))


if __name__ == "__main__":
    main()
