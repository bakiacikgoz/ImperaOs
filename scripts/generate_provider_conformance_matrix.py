from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from imperaos.model_providers.conformance import (
    build_provider_conformance_matrix,
    write_provider_conformance_matrix,
)
from imperaos.model_providers.registry import resolve_model_provider_registry
from imperaos.runtime.config import RuntimeConfig


def generate_provider_conformance_matrix(
    *,
    profile: str,
    mode: str,
    output_root: Path,
) -> dict[str, object]:
    config = RuntimeConfig.from_profile(profile)
    registry = resolve_model_provider_registry(config=config, profile=profile)
    matrix = build_provider_conformance_matrix(registry=registry, profile=profile, mode=mode)
    paths = write_provider_conformance_matrix(matrix=matrix, output_root=output_root)
    status = "pass" if all(item.fail_count == 0 for item in matrix.providers) else "fail"
    return {
        "version": "model_provider.conformance_matrix_run/v1",
        "status": status,
        "profile": profile,
        "mode": mode,
        "providerCount": len(matrix.providers),
        "providersWithFailures": [
            item.provider_id for item in matrix.providers if item.fail_count > 0
        ],
        "paths": paths,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate provider conformance matrix.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/model-provider-governance/conformance"),
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    report = generate_provider_conformance_matrix(
        profile=args.profile,
        mode=args.mode,
        output_root=args.output_root,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"status={report['status']} profile={report['profile']} "
            f"providers={report['providerCount']}"
        )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
