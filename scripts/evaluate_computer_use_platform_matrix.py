from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.computer_use.vision_runtime.platforms import evaluate_platform_matrix  # noqa: E402
from imperaos.runtime.config import resolve_runtime_config  # noqa: E402
from imperaos.runtime.platform import current_platform  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate computer-use platform gates.")
    parser.add_argument("--profile", default="balanced")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown", required=True)
    args = parser.parse_args(argv)

    config, _source_map = resolve_runtime_config(
        profile=args.profile,
        root_dir=REPO_ROOT,
        env={},
    )
    matrix = evaluate_platform_matrix(
        config.computer_use,
        current_platform=current_platform().label,
        profile=args.profile,
    )

    output_path = Path(args.output)
    markdown_path = Path(args.markdown)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(matrix), encoding="utf-8")
    print(json.dumps(matrix, ensure_ascii=False, indent=2))
    return 0 if matrix["status"] == "pass" else 1


def _render_markdown(matrix: dict[str, object]) -> str:
    platforms = matrix.get("platforms", {})
    lines = [
        "# Computer-Use Platform Matrix",
        "",
        f"- Status: `{matrix.get('status')}`",
        f"- Profile: `{matrix.get('profile')}`",
        f"- Current platform: `{matrix.get('currentPlatform')}`",
        f"- Live automation default: `{matrix.get('liveAutomationDefault')}`",
        f"- Raw screenshot persistence default: `{matrix.get('rawScreenshotPersistenceDefault')}`",
        "",
        (
            "| Platform | Stage | Live | Supervised Local | Evidence | Capture | Input | "
            "Reason | Public Claim |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if isinstance(platforms, dict):
        for platform, payload in platforms.items():
            if not isinstance(payload, dict):
                continue
            lines.append(
                (
                    "| {platform} | {stage} | {live} | {supervised} | {evidence} | "
                    "{capture} | {input} | {reason} | {public_claim} |"
                ).format(
                    platform=platform,
                    stage=payload.get("stage"),
                    live=payload.get("liveEnabled"),
                    supervised=payload.get("supervisedLiveAllowed"),
                    evidence=payload.get("evidenceStatus"),
                    capture=payload.get("captureBackend"),
                    input=payload.get("inputBackend"),
                    reason=payload.get("reasonCode"),
                    public_claim=payload.get("public_live_claim_allowed"),
                )
            )
    lines.extend(["", "## Capability Blockers", ""])
    if isinstance(platforms, dict):
        for platform, payload in platforms.items():
            if not isinstance(payload, dict):
                continue
            capability = payload.get("capability", {})
            blockers = (
                capability.get("blockers", [])
                if isinstance(capability, dict)
                else []
            )
            if not isinstance(blockers, list) or not blockers:
                lines.append(f"- {platform}: None")
                continue
            for blocker in blockers:
                if not isinstance(blocker, dict):
                    continue
                lines.append(f"- {platform}: `{blocker.get('code')}`")
    blockers = matrix.get("blockers", [])
    lines.extend(["", "## Blockers", ""])
    if isinstance(blockers, list) and blockers:
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
