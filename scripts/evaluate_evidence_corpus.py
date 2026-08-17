from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.evidence_corpus import (
    build_evidence_verification_corpus,
    verify_evidence_corpus,
)
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and verify evidence corpus fixtures.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--output-root", default="artifacts/evidence-corpus")
    parser.add_argument("--report", default="artifacts/evidence-corpus/corpus_report.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    config = RuntimeConfig.from_profile(args.profile)
    corpus_root = REPO_ROOT / args.output_root
    build_evidence_verification_corpus(output_root=corpus_root, config=config)
    report = verify_evidence_corpus(
        corpus_root=corpus_root,
        config=config,
        root_dir=corpus_root / "state" / "control-plane",
    )
    report_path = REPO_ROOT / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(report["status"])
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
