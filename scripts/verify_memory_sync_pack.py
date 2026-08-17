from __future__ import annotations

import argparse
import json

from imperaos.memory.sync_pack import verify_memory_sync_pack


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    result = verify_memory_sync_pack(args.input)
    print(json.dumps(result.model_dump(mode="json", by_alias=True), sort_keys=True))
    if result.status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
