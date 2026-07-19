from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.evidence_index import build_evidence_index, discover_evidence_manifests
from imperaos.control_plane.evidence_pack import EvidencePackBuilder
from imperaos.control_plane.models import EvidencePackManifest
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate control-plane evidence index.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--evidence-root", default="artifacts/control-plane/evidence")
    parser.add_argument("--root-dir", default="artifacts/design-partner-rc/evidence-index/state")
    parser.add_argument("--output", default="artifacts/design-partner-rc/evidence_index.json")
    parser.add_argument("--select-latest-valid", action="store_true")
    parser.add_argument(
        "--staged-evidence-root",
        default="artifacts/design-partner-rc/evidence-sample",
    )
    args = parser.parse_args()

    config = RuntimeConfig.from_profile(args.profile)
    root_dir = REPO_ROOT / args.root_dir
    evidence_root = REPO_ROOT / args.evidence_root
    if args.select_latest_valid:
        evidence_root = _stage_latest_valid_evidence(
            config=config,
            source_root=evidence_root,
            root_dir=root_dir,
            staged_root=REPO_ROOT / args.staged_evidence_root,
        )
    index = build_evidence_index(
        config=config,
        evidence_root=evidence_root,
        root_dir=root_dir,
    )
    payload = index.model_dump(mode="json", by_alias=True)
    output = REPO_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    if index.status == "blocked":
        raise SystemExit(1)


def _stage_latest_valid_evidence(
    *,
    config: RuntimeConfig,
    source_root: Path,
    root_dir: Path,
    staged_root: Path,
) -> Path:
    builder = EvidencePackBuilder(config=config, root_dir=root_dir)
    valid: list[tuple[object, Path]] = []
    for manifest_path in discover_evidence_manifests(source_root):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = EvidencePackManifest.model_validate(
                {key: value for key, value in payload.items() if key != "integrity"}
            )
            result = builder.verify(manifest_path=manifest_path)
        except Exception:  # noqa: BLE001
            continue
        if result.status == "pass":
            valid.append((manifest.generated_at, manifest_path))
    if not valid:
        return source_root

    _generated_at, manifest_path = max(valid, key=lambda item: item[0])
    destination = staged_root / "control-plane" / "evidence" / manifest_path.parent.name
    if staged_root.exists():
        shutil.rmtree(staged_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(manifest_path.parent, destination)
    return staged_root


if __name__ == "__main__":
    main()
