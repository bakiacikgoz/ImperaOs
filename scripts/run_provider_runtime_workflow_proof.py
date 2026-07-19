from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.provider_runtime_workflows import (  # noqa: E402
    ProviderWorkflowProofRequest,
    run_provider_workflow_proof,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run provider governed read-only workflow proof.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--provider", default="openai_responses")
    parser.add_argument("--mode", default="dry-run")
    parser.add_argument("--output-root", default="artifacts/provider-runtime/workflow-proof")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run_provider_workflow_proof(
        ProviderWorkflowProofRequest(
            workflow_kind="read_only_ops_triage",
            provider_kind=args.provider,
            profile=args.profile,
            runtime_mode=args.mode.replace("-", "_"),
            output_root=_resolve_path(args.output_root),
        )
    )
    payload = result.to_payload()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"wrote {result.artifact_path}")
    if result.status in {"blocked", "error"}:
        raise SystemExit(1)


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


if __name__ == "__main__":
    main()
