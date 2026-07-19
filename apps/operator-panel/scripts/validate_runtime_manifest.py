#!/usr/bin/env python3
"""Validate the portable identity contract for a bundled runtime manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PLATFORM_KEYS = {
    "windows": frozenset(
        {
            "platform",
            "arch",
            "python",
            "imperaos_version",
            "created_at_utc",
            "source_wheel",
            "source_wheel_sha256",
            "python_exe_sha256",
            "uv_lock_sha256",
            "git_sha",
        }
    ),
    "macos": frozenset(
        {
            "platform",
            "arch",
            "python",
            "imperaos_version",
            "wheel_sha256",
            "git_head",
            "built_at_utc",
        }
    ),
}
PLATFORM_ARCHES = {
    "windows": frozenset({"x86_64"}),
    "macos": frozenset({"arm64", "x86_64"}),
}


class ManifestValidationError(ValueError):
    """Raised when a runtime manifest violates its serialized contract."""


def parse_manifest(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ManifestValidationError(f"cannot read manifest: {path}: {exc}") from exc

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        key, separator, value = line.partition("=")
        if not separator or not key or key != key.strip() or value != value.strip():
            raise ManifestValidationError(f"invalid manifest line {line_number}")
        if key in values:
            raise ManifestValidationError(f"duplicate manifest key: {key}")
        if not value:
            raise ManifestValidationError(f"blank manifest value: {key}")
        values[key] = value
    return values


def validate_manifest(
    values: dict[str, str],
    *,
    platform: str,
    arch: str,
    runtime_version: str,
) -> None:
    allowed_arches = PLATFORM_ARCHES[platform]
    if arch not in allowed_arches:
        supported = ", ".join(sorted(allowed_arches))
        raise ManifestValidationError(
            f"unsupported arch for {platform}: {arch} (expected one of: {supported})"
        )

    expected_keys = PLATFORM_KEYS[platform]
    unexpected = sorted(values.keys() - expected_keys)
    if unexpected:
        raise ManifestValidationError(
            f"unexpected manifest key: {', '.join(unexpected)}"
        )
    missing = sorted(expected_keys - values.keys())
    if missing:
        raise ManifestValidationError(f"missing manifest key: {', '.join(missing)}")

    if values["platform"] != platform:
        raise ManifestValidationError(
            f"platform mismatch: expected {platform}, got {values['platform']}"
        )
    if values["arch"] != arch:
        raise ManifestValidationError(
            f"arch mismatch: expected {arch}, got {values['arch']}"
        )
    if values["imperaos_version"] != runtime_version:
        raise ManifestValidationError(
            "version mismatch: expected "
            f"{values['imperaos_version']}, got {runtime_version}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--platform", choices=sorted(PLATFORM_KEYS), required=True)
    parser.add_argument("--arch", required=True)
    parser.add_argument("--runtime-version", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        values = parse_manifest(args.manifest)
        validate_manifest(
            values,
            platform=args.platform,
            arch=args.arch,
            runtime_version=args.runtime_version,
        )
    except ManifestValidationError as exc:
        print(f"[manifest-verify] {exc}", file=sys.stderr)
        return 2

    print(
        "[manifest-verify] manifest=pass "
        f"platform={args.platform} arch={args.arch} "
        f"imperaos_version={args.runtime_version}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
