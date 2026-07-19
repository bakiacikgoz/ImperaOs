from __future__ import annotations

import argparse
import json

from imperaos.memory.sync_importer import import_memory_sync_pack
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="balanced")
    parser.add_argument("--input", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approval-id")
    args = parser.parse_args()
    report = import_memory_sync_pack(
        config=RuntimeConfig.from_profile(args.profile),
        input_path=args.input,
        dry_run=not args.apply,
        approval_id=args.approval_id,
    )
    print(json.dumps(report.model_dump(mode="json", by_alias=True), sort_keys=True))
    if report.status == "blocked" and args.apply:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
