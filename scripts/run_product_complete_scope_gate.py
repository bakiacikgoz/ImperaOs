from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.release.product_complete import build_product_complete_no_ship_register

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "product-complete"
REQUIRED_DOCS = (
    "docs/PRODUCT_COMPLETE_SCOPE.md",
    "docs/PRODUCT_COMPLETE_NO_SHIP_REGISTER.md",
)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def run_scope_gate(*, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    missing_docs = [path for path in REQUIRED_DOCS if not (REPO_ROOT / path).exists()]
    no_ship_register = build_product_complete_no_ship_register()
    blockers: list[str] = []
    if missing_docs:
        blockers.append("PRODUCT_COMPLETE_SCOPE_DOCS_MISSING")
    if no_ship_register.blocking_count:
        blockers.append("PRODUCT_COMPLETE_NO_SHIP_BLOCKERS_OPEN")
    status = "pass" if not blockers else "fail"
    report = {
        "schemaVersion": "product-complete.scope-gate/v1",
        "generatedAtUtc": _now(),
        "status": status,
        "requiredDocs": list(REQUIRED_DOCS),
        "missingDocs": missing_docs,
        "noShipRegister": no_ship_register.model_dump(mode="json", by_alias=True),
        "blockingReasons": blockers,
        "artifacts": [
            _relative(output_root / "product_complete_scope_gate.json"),
            _relative(output_root / "no_ship_register.json"),
        ],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "product_complete_scope_gate.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_root / "no_ship_register.json").write_text(
        json.dumps(
            no_ship_register.model_dump(mode="json", by_alias=True),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run product-complete scope/no-ship gate.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = run_scope_gate(output_root=args.output_root)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"status={report['status']} output={args.output_root}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
