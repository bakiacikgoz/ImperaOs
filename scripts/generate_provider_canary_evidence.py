from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from imperaos.model_providers.canary import run_provider_canary
from imperaos.model_providers.canary_evidence import (
    verify_canary_evidence_root,
    write_router_shadow_evidence,
)
from imperaos.model_providers.models import (
    DataClass,
    ProviderCanaryRequest,
    ProviderRouteShadowRequest,
)
from imperaos.model_providers.registry import resolve_model_provider_registry
from imperaos.model_providers.router_shadow import recommend_provider_shadow
from imperaos.runtime.config import RuntimeConfig

DEFAULT_OUTPUT_DIR = Path("artifacts/model-provider-governance/canary")


def generate_canary_evidence(
    *,
    profile: str = "enterprise",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    config = RuntimeConfig.from_profile(profile)
    registry = resolve_model_provider_registry(config=config, profile=profile)
    skipped = run_provider_canary(
        request=ProviderCanaryRequest(
            provider_id="openai-public",
            profile=profile,
            data_classes=[DataClass.PUBLIC],
            allow_live=False,
            evidence_root=str(output_dir),
        ),
        registry=registry,
        env={},
        evidence_root=output_dir,
    )
    denied = run_provider_canary(
        request=ProviderCanaryRequest(
            provider_id="openai-public",
            profile=profile,
            data_classes=[DataClass.CONFIDENTIAL],
            allow_live=True,
            evidence_root=str(output_dir),
        ),
        registry=registry,
        env={"IMPERAOS_PROVIDER_LIVE_CANARY": "1"},
        evidence_root=output_dir,
    )
    router_decision = recommend_provider_shadow(
        registry=registry,
        request=ProviderRouteShadowRequest(
            task_type="chat",
            data_classes=[DataClass.CONFIDENTIAL],
            required_capabilities=[],
        ),
    )
    router_path = write_router_shadow_evidence(
        decision=router_decision,
        evidence_root=output_dir / "router-shadow",
    )
    verify = verify_canary_evidence_root(output_dir)
    return {
        "version": "model_provider.canary_evidence_generator/v1",
        "status": verify["status"],
        "skipped": skipped.model_dump(mode="json"),
        "denied": denied.model_dump(mode="json"),
        "routerShadowEvidence": str(router_path),
        "verify": verify,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate offline provider canary evidence.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = generate_canary_evidence(profile=args.profile, output_dir=args.output_dir)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"status={result['status']} output_dir={args.output_dir}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
