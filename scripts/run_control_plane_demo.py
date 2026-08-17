from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic Agent Control Plane demo.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--agent-spec", default="examples/control_plane/agent_governed_ops.yaml")
    parser.add_argument("--summary", default="artifacts/control-plane/demo_summary.md")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    commands = [
        [
            "uv",
            "run",
            "imperaos",
            "control-plane",
            "agent",
            "register",
            "--spec",
            args.agent_spec,
            "--profile",
            args.profile,
            "--json",
        ],
        [
            "uv",
            "run",
            "imperaos",
            "control-plane",
            "policy",
            "simulate",
            "--agent-id",
            "governed-ops",
            "--profile",
            args.profile,
            "--json",
        ],
        [
            "uv",
            "run",
            "imperaos",
            "control-plane",
            "claims",
            "verify",
            "--profile",
            args.profile,
            "--json",
        ],
    ]
    results = []
    for command in commands:
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
        results.append(
            {
                "command": " ".join(command),
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        )
    summary = Path(args.summary)
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(_render_markdown(results), encoding="utf-8")
    payload = {
        "status": "pass"
        if all(item["exit_code"] in {0, 3} for item in results)
        else "fail",
        "summary": str(summary),
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(str(summary))


def _render_markdown(results: list[dict[str, object]]) -> str:
    lines = ["# Agent Control Plane Demo Summary", ""]
    for item in results:
        lines.append(f"## `{item['command']}`")
        lines.append("")
        lines.append(f"Exit code: `{item['exit_code']}`")
        lines.append("")
        lines.append("```json")
        lines.append(str(item["stdout"]).strip())
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
