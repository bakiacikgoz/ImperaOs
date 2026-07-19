from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--status", default="pass")
    args = parser.parse_args()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "release.synthetic-gate-artifact/v1",
                "gateId": args.gate_id,
                "status": args.status,
                "generatedAtUtc": datetime.now(UTC).isoformat(),
                "rawPersistence": False,
                "evidenceMode": "hash_only",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
