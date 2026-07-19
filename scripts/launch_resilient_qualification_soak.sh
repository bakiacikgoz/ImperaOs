#!/usr/bin/env bash
set -euo pipefail

SOAK_HOURS="72"
VALID_HOURS="96"
PROFILE="enterprise"
MODE="mixed"
RUNNER="venv"
RUN_ID=""
SOURCE_ROOT=""
WORKSPACE_ROOT=""
OUTPUT_ROOT="artifacts/qualification"
STATE_ROOT="artifacts/qualification/supervisor"
VERIFY_TIMEOUT_SECONDS="180"
VERIFY_INTERVAL_SECONDS="5"
FORCE=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: scripts/launch_resilient_qualification_soak.sh [options]

Prepares an isolated /private/tmp workspace, refreshes enterprise identity,
submits a supervised qualification soak via launchd, and verifies heartbeat.

Options:
  --hours, --soak-hours HOURS       Soak duration in hours (default: 72)
  --valid-hours HOURS              Refreshed identity validity (default: 96)
  --profile PROFILE                Runtime profile (default: enterprise)
  --mode MODE                      Qualification mode (default: mixed)
  --run-id ID                      Stable run id (default: final72h-<utc>)
  --source-root PATH               Source repo root (default: current dir)
  --workspace-root PATH            Isolated workspace path
  --runner auto|venv|uv            Runner passed to supervised soak (default: venv)
  --output-root PATH               Qualification output root inside workspace
  --state-root PATH                Supervisor state root inside workspace
  --verify-timeout SECONDS         Heartbeat verification timeout (default: 180)
  --verify-interval SECONDS        Heartbeat polling interval (default: 5)
  --force                          Replace an existing workspace for this run
  --dry-run                        Prepare workspace and supervised dry-run only
  -h, --help                       Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hours|--soak-hours)
      SOAK_HOURS="${2:?missing value for $1}"
      shift 2
      ;;
    --valid-hours)
      VALID_HOURS="${2:?missing value for $1}"
      shift 2
      ;;
    --profile)
      PROFILE="${2:?missing value for $1}"
      shift 2
      ;;
    --mode)
      MODE="${2:?missing value for $1}"
      shift 2
      ;;
    --run-id)
      RUN_ID="${2:?missing value for $1}"
      shift 2
      ;;
    --source-root)
      SOURCE_ROOT="${2:?missing value for $1}"
      shift 2
      ;;
    --workspace-root)
      WORKSPACE_ROOT="${2:?missing value for $1}"
      shift 2
      ;;
    --runner)
      RUNNER="${2:?missing value for $1}"
      shift 2
      ;;
    --output-root)
      OUTPUT_ROOT="${2:?missing value for $1}"
      shift 2
      ;;
    --state-root)
      STATE_ROOT="${2:?missing value for $1}"
      shift 2
      ;;
    --verify-timeout)
      VERIFY_TIMEOUT_SECONDS="${2:?missing value for $1}"
      shift 2
      ;;
    --verify-interval)
      VERIFY_INTERVAL_SECONDS="${2:?missing value for $1}"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

if [[ -z "${SOURCE_ROOT}" ]]; then
  SOURCE_ROOT="$(pwd -P)"
fi
if [[ -z "${RUN_ID}" ]]; then
  RUN_ID="final72h-$(date -u +%Y%m%dT%H%M%SZ)"
fi
if [[ -z "${WORKSPACE_ROOT}" ]]; then
  WORKSPACE_ROOT="/private/tmp/imperaos_soak_${RUN_ID}"
fi

SOURCE_ROOT="$(cd "${SOURCE_ROOT}" && pwd -P)"
WORKSPACE_ROOT="$(python3 -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).expanduser())' "${WORKSPACE_ROOT}")"
RUN_DIR="${WORKSPACE_ROOT}/${STATE_ROOT}/${RUN_ID}"

case "${RUNNER}" in
  auto|venv|uv) ;;
  *)
    echo "Unsupported runner: ${RUNNER}" >&2
    exit 64
    ;;
esac

if [[ -e "${WORKSPACE_ROOT}" ]]; then
  if [[ "${FORCE}" -ne 1 ]]; then
    echo "Workspace already exists: ${WORKSPACE_ROOT}" >&2
    echo "Use --force to replace it, or choose a new --run-id." >&2
    exit 3
  fi
  rm -rf "${WORKSPACE_ROOT}"
fi

mkdir -p "${WORKSPACE_ROOT}"

copy_item() {
  local item="$1"
  if [[ -e "${SOURCE_ROOT}/${item}" ]]; then
    mkdir -p "$(dirname "${WORKSPACE_ROOT}/${item}")"
    rsync -a --delete "${SOURCE_ROOT}/${item}" "${WORKSPACE_ROOT}/$(dirname "${item}")/"
  fi
}

copy_item ".python-version"
copy_item "pyproject.toml"
copy_item "uv.lock"
copy_item "README.md"
copy_item "KEY_MANAGEMENT.md"
copy_item ".venv"
copy_item ".imperaos"
copy_item "imperaos"
copy_item "config"
copy_item "contracts"
copy_item "examples"
copy_item "scripts"

PYTHON_BIN="python3"
if [[ -x "${WORKSPACE_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${WORKSPACE_ROOT}/.venv/bin/python"
fi

(
  cd "${WORKSPACE_ROOT}"
  "${PYTHON_BIN}" scripts/refresh_enterprise_identity_assertion.py \
    --valid-hours "${VALID_HOURS}" \
    --no-backup
  scripts/run_qualification_soak_supervised.sh \
    --hours "${SOAK_HOURS}" \
    --profile "${PROFILE}" \
    --mode "${MODE}" \
    --output-root "${OUTPUT_ROOT}" \
    --state-root "${STATE_ROOT}" \
    --run-id "${RUN_ID}" \
    --runner "${RUNNER}" \
    --dry-run
)

if [[ "${DRY_RUN}" -eq 1 ]]; then
  cat <<EOF
Prepared resilient soak workspace.
Workspace : ${WORKSPACE_ROOT}
Run dir   : ${RUN_DIR}
Dry run   : complete
Monitor   : scripts/watch_qualification_soak.sh --run-dir ${RUN_DIR}
EOF
  exit 0
fi

(
  cd "${WORKSPACE_ROOT}"
  scripts/run_qualification_soak_supervised.sh \
    --hours "${SOAK_HOURS}" \
    --profile "${PROFILE}" \
    --mode "${MODE}" \
    --output-root "${OUTPUT_ROOT}" \
    --state-root "${STATE_ROOT}" \
    --run-id "${RUN_ID}" \
    --runner "${RUNNER}" \
    --launchd
)

deadline=$((SECONDS + VERIFY_TIMEOUT_SECONDS))
while (( SECONDS < deadline )); do
  if "${PYTHON_BIN}" - "${RUN_DIR}" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

run_dir = Path(sys.argv[1])
status_path = run_dir / "status.json"
heartbeat_path = run_dir / "heartbeat.txt"
if not status_path.exists() or not heartbeat_path.exists():
    raise SystemExit(1)
status = json.loads(status_path.read_text(encoding="utf-8"))
heartbeat = heartbeat_path.read_text(encoding="utf-8").strip()
heartbeat_at = datetime.fromisoformat(heartbeat.replace("Z", "+00:00")).astimezone(UTC)
age = (datetime.now(UTC) - heartbeat_at).total_seconds()
if status.get("status") != "running":
    raise SystemExit(1)
if not status.get("child_pid"):
    raise SystemExit(1)
if age > 180:
    raise SystemExit(1)
PY
  then
    cat <<EOF
Resilient qualification soak is running.
Workspace : ${WORKSPACE_ROOT}
Run id    : ${RUN_ID}
Run dir   : ${RUN_DIR}
Monitor   : scripts/watch_qualification_soak.sh --run-dir ${RUN_DIR}
EOF
    exit 0
  fi
  sleep "${VERIFY_INTERVAL_SECONDS}"
done

echo "Soak launch did not produce a fresh running heartbeat within ${VERIFY_TIMEOUT_SECONDS}s." >&2
echo "Run dir: ${RUN_DIR}" >&2
if [[ -f "${RUN_DIR}/launchd.stderr.log" ]]; then
  tail -80 "${RUN_DIR}/launchd.stderr.log" >&2 || true
fi
if [[ -f "${RUN_DIR}/qualification.stderr.log" ]]; then
  tail -80 "${RUN_DIR}/qualification.stderr.log" >&2 || true
fi
exit 1
exit 4
