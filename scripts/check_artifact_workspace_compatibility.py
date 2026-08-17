from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

MATRIX_PATH = Path("contracts/artifact_workspace/dependency_matrix.json")
PACKAGE_PATH = Path("apps/operator-panel/package.json")
TAURI_CONFIG_PATH = Path("apps/operator-panel/src-tauri/tauri.conf.json")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_dependency_matrix(repo_root: Path) -> dict[str, Any]:
    matrix = _load_json(repo_root / MATRIX_PATH)
    package_manifest = _load_json(repo_root / PACKAGE_PATH)
    tauri_config = _load_json(repo_root / TAURI_CONFIG_PATH)
    dependencies = {
        **package_manifest.get("dependencies", {}),
        **package_manifest.get("devDependencies", {}),
    }
    blockers: list[dict[str, str]] = []
    packages = matrix.get("packages", [])
    seen: set[str] = set()
    matrix_valid = matrix.get("schemaVersion") == "artifact-workspace.dependency-matrix/v1"

    for item in packages:
        package = str(item.get("package", ""))
        version = str(item.get("version", ""))
        if not package or package in seen or not version or version[0] in "^~*<>":
            matrix_valid = False
        seen.add(package)
        installed = dependencies.get(package)
        if item.get("required") is True and installed is None:
            blockers.append(
                {"code": "MISSING_REQUIRED_DEPENDENCY", "subject": package, "detail": version}
            )
        elif installed is not None and installed != version:
            blockers.append(
                {
                    "code": "DEPENDENCY_VERSION_MISMATCH",
                    "subject": package,
                    "detail": f"expected {version}; observed {installed}",
                }
            )
        if item.get("licenseGate") == "commercial":
            blockers.append(
                {
                    "code": "LICENSE_GATE_BLOCKED",
                    "subject": package,
                    "detail": "commercial entitlement not recorded",
                }
            )

    csp = tauri_config.get("app", {}).get("security", {}).get("csp")
    if csp is None:
        blockers.append(
            {"code": "CSP_DISABLED", "subject": str(TAURI_CONFIG_PATH), "detail": "csp is null"}
        )
    elif "unsafe-eval" in json.dumps(csp):
        blockers.append(
            {
                "code": "CSP_UNSAFE_EVAL_FORBIDDEN",
                "subject": str(TAURI_CONFIG_PATH),
                "detail": "unsafe-eval is not allowed",
            }
        )

    secondary_lock = repo_root / "apps/operator-panel/pnpm-lock.yaml"
    if secondary_lock.exists():
        blockers.append(
            {
                "code": "SECONDARY_LOCKFILE_PRESENT",
                "subject": "apps/operator-panel/pnpm-lock.yaml",
                "detail": "workspace uses the root pnpm-lock.yaml as canonical",
            }
        )

    return {
        "schemaVersion": "artifact-workspace.compatibility-report/v1",
        "matrixValid": matrix_valid,
        "releaseReady": matrix_valid and not blockers,
        "canonicalLockfile": matrix.get("canonicalLockfile"),
        "reactVersion": dependencies.get("react"),
        "cspConfigured": csp is not None,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check artifact workspace dependency decisions")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--release",
        action="store_true",
        help="Fail when any release blocker remains",
    )
    args = parser.parse_args()
    report = evaluate_dependency_matrix(args.repo_root.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if not report["matrixValid"]:
        return 2
    if args.release and not report["releaseReady"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
