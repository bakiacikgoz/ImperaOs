#!/usr/bin/env bash
set -uo pipefail

SOAK_HOURS="24"
PROFILE="enterprise"
MODE="mixed"
OUTPUT_ROOT="artifacts/qualification"
STATE_ROOT=""
RUN_ID=""
RUNNER="auto"
DETACH=0
LAUNCHD=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: scripts/run_qualification_soak_supervised.sh [options]

Runs a long qualification soak with a durable supervisor.

Options:
  --hours, --soak-hours HOURS   Soak duration in hours (default: 24)
  --profile PROFILE             Runtime profile (default: enterprise)
  --mode MODE                   Qualification mode (default: mixed)
  --output-root PATH            Qualification output root (default: artifacts/qualification)
  --state-root PATH             Supervisor state root (default: <output-root>/supervisor)
  --run-id ID                   Stable supervisor run id
  --runner auto|venv|uv         Command runner (default: auto, prefer .venv)
  --detach                      Start in the background with nohup
  --launchd                     Start as a macOS launchd agent
  --dry-run                     Print the command and exit without running
  -h, --help                    Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hours|--soak-hours)
      SOAK_HOURS="${2:?missing value for $1}"
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
    --output-root)
      OUTPUT_ROOT="${2:?missing value for $1}"
      shift 2
      ;;
    --state-root)
      STATE_ROOT="${2:?missing value for $1}"
      shift 2
      ;;
    --run-id)
      RUN_ID="${2:?missing value for $1}"
      shift 2
      ;;
    --runner)
      RUNNER="${2:?missing value for $1}"
      shift 2
      ;;
    --detach)
      DETACH=1
      shift
      ;;
    --launchd)
      LAUNCHD=1
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

if [[ -z "${STATE_ROOT}" ]]; then
  STATE_ROOT="${OUTPUT_ROOT}/supervisor"
fi
if [[ -z "${RUN_ID}" ]]; then
  RUN_ID="rc24h-$(date -u +%Y%m%dT%H%M%SZ)"
fi

REPO_ROOT="$(/bin/pwd -P)"
SCRIPT_PATH="$0"
if [[ "${SCRIPT_PATH}" != /* ]]; then
  SCRIPT_PATH="${REPO_ROOT}/${SCRIPT_PATH#./}"
fi

RUN_DIR="${STATE_ROOT}/${RUN_ID}"
STATUS_PATH="${RUN_DIR}/status.json"
HEARTBEAT_PATH="${RUN_DIR}/heartbeat.txt"
STDOUT_PATH="${RUN_DIR}/qualification.stdout.json"
STDERR_PATH="${RUN_DIR}/qualification.stderr.log"
SUPERVISOR_LOG_PATH="${RUN_DIR}/supervisor.nohup.log"
LOCK_DIR="${STATE_ROOT}/.running.lock"
case "${RUNNER}" in
  auto)
    if [[ -x ".venv/bin/imperaos" ]]; then
      RESOLVED_RUNNER="venv"
    else
      RESOLVED_RUNNER="uv"
    fi
    ;;
  venv|uv)
    RESOLVED_RUNNER="${RUNNER}"
    ;;
  *)
    echo "Unsupported runner: ${RUNNER}" >&2
    exit 64
    ;;
esac

if [[ "${RESOLVED_RUNNER}" == "venv" ]]; then
  COMMAND=(
    .venv/bin/python -m imperaos qualification run
    --profile "${PROFILE}"
    --mode "${MODE}"
    --soak-hours "${SOAK_HOURS}"
    --output-root "${OUTPUT_ROOT}"
    --json
  )
else
  COMMAND=(
    uv run imperaos qualification run
    --profile "${PROFILE}"
    --mode "${MODE}"
    --soak-hours "${SOAK_HOURS}"
    --output-root "${OUTPUT_ROOT}"
    --json
  )
fi
COMMAND_DISPLAY="$(printf "%q " "${COMMAND[@]}")"

write_json() {
  local path="$1"
  shift
  mkdir -p "$(dirname "${path}")"
  env "$@" python3 - "${path}" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "schemaVersion": "qualification-soak-supervisor/v1",
    "run_id": os.environ["RUN_ID"],
    "status": os.environ["STATUS"],
    "profile": os.environ["PROFILE"],
    "mode": os.environ["MODE"],
    "soak_hours": float(os.environ["SOAK_HOURS"]),
    "runner": os.environ["RUNNER"],
    "output_root": os.environ["OUTPUT_ROOT"],
    "state_root": os.environ["STATE_ROOT"],
    "run_dir": os.environ["RUN_DIR"],
    "command": os.environ["COMMAND_DISPLAY"].strip(),
    "cwd": os.environ["CWD"],
    "supervisor_pid": int(os.environ["SUPERVISOR_PID"]),
    "child_pid": int(os.environ["CHILD_PID"]) if os.environ.get("CHILD_PID") else None,
    "exit_code": int(os.environ["EXIT_CODE"]) if os.environ.get("EXIT_CODE") else None,
    "caffeinate_enabled": os.environ["CAFFEINATE_ENABLED"] == "1",
    "stdout_path": os.environ["STDOUT_PATH"],
    "stderr_path": os.environ["STDERR_PATH"],
    "heartbeat_path": os.environ["HEARTBEAT_PATH"],
    "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
os.replace(tmp, path)
PY
}

write_status() {
  local status="$1"
  local exit_code="${2:-}"
  write_json "${STATUS_PATH}" \
    "RUN_ID=${RUN_ID}" \
    "STATUS=${status}" \
    "PROFILE=${PROFILE}" \
    "MODE=${MODE}" \
    "SOAK_HOURS=${SOAK_HOURS}" \
    "RUNNER=${RESOLVED_RUNNER}" \
    "OUTPUT_ROOT=${OUTPUT_ROOT}" \
    "STATE_ROOT=${STATE_ROOT}" \
    "RUN_DIR=${RUN_DIR}" \
    "COMMAND_DISPLAY=${COMMAND_DISPLAY}" \
    "CWD=${REPO_ROOT}" \
    "SUPERVISOR_PID=$$" \
    "CHILD_PID=${CHILD_PID:-}" \
    "EXIT_CODE=${exit_code}" \
    "CAFFEINATE_ENABLED=${CAFFEINATE_ENABLED:-0}" \
    "STDOUT_PATH=${STDOUT_PATH}" \
    "STDERR_PATH=${STDERR_PATH}" \
    "HEARTBEAT_PATH=${HEARTBEAT_PATH}"
}

if [[ "${DRY_RUN}" -eq 1 ]]; then
  mkdir -p "${RUN_DIR}"
  write_status "dry_run" ""
  cat "${STATUS_PATH}"
  exit 0
fi

if [[ "${LAUNCHD}" -eq 1 ]]; then
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "--launchd is only supported on macOS" >&2
    exit 64
  fi
  mkdir -p "${RUN_DIR}"
  LAUNCHD_LABEL="com.imperaos.qualification-soak.${RUN_ID//[^A-Za-z0-9]/-}"
  PLIST_PATH="${RUN_DIR}/${LAUNCHD_LABEL}.plist"
  LAUNCHD_STDOUT_PATH="${RUN_DIR}/launchd.stdout.log"
  LAUNCHD_STDERR_PATH="${RUN_DIR}/launchd.stderr.log"
  PROGRAM_ARGS_JSON="$(
    python3 - <<PY
import json
print(json.dumps([
    "$SCRIPT_PATH",
    "--hours", "$SOAK_HOURS",
    "--profile", "$PROFILE",
    "--mode", "$MODE",
    "--output-root", "$OUTPUT_ROOT",
    "--state-root", "$STATE_ROOT",
    "--run-id", "$RUN_ID",
    "--runner", "$RESOLVED_RUNNER",
]))
PY
  )"
  LAUNCHD_LABEL="${LAUNCHD_LABEL}" \
  PLIST_PATH="${PLIST_PATH}" \
  WORKING_DIRECTORY="${REPO_ROOT}" \
  PROGRAM_ARGS_JSON="${PROGRAM_ARGS_JSON}" \
  LAUNCHD_STDOUT_PATH="${LAUNCHD_STDOUT_PATH}" \
  LAUNCHD_STDERR_PATH="${LAUNCHD_STDERR_PATH}" \
  python3 - <<'PY'
import json
import os
import plistlib
from pathlib import Path

plist_path = Path(os.environ["PLIST_PATH"])
program_arguments = json.loads(os.environ["PROGRAM_ARGS_JSON"])
payload = {
    "Label": os.environ["LAUNCHD_LABEL"],
    "ProgramArguments": program_arguments,
    "WorkingDirectory": os.environ["WORKING_DIRECTORY"],
    "RunAtLoad": True,
    "KeepAlive": False,
    "ProcessType": "Background",
    "StandardOutPath": os.environ["LAUNCHD_STDOUT_PATH"],
    "StandardErrorPath": os.environ["LAUNCHD_STDERR_PATH"],
}
plist_path.write_bytes(plistlib.dumps(payload, sort_keys=False))
PY
  launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
  LAUNCHCTL_EXIT_CODE="$?"
  if [[ "${LAUNCHCTL_EXIT_CODE}" -ne 0 ]]; then
    write_json "${RUN_DIR}/launchd.json" \
      "RUN_ID=${RUN_ID}" \
      "STATUS=launchd_failed" \
      "PROFILE=${PROFILE}" \
      "MODE=${MODE}" \
      "SOAK_HOURS=${SOAK_HOURS}" \
      "RUNNER=${RESOLVED_RUNNER}" \
      "OUTPUT_ROOT=${OUTPUT_ROOT}" \
      "STATE_ROOT=${STATE_ROOT}" \
      "RUN_DIR=${RUN_DIR}" \
      "COMMAND_DISPLAY=${COMMAND_DISPLAY}" \
      "CWD=${REPO_ROOT}" \
      "SUPERVISOR_PID=0" \
      "CHILD_PID=" \
      "EXIT_CODE=${LAUNCHCTL_EXIT_CODE}" \
      "CAFFEINATE_ENABLED=0" \
      "STDOUT_PATH=${STDOUT_PATH}" \
      "STDERR_PATH=${STDERR_PATH}" \
      "HEARTBEAT_PATH=${HEARTBEAT_PATH}"
    cat "${RUN_DIR}/launchd.json" >&2
    exit "${LAUNCHCTL_EXIT_CODE}"
  fi
  write_json "${RUN_DIR}/launchd.json" \
    "RUN_ID=${RUN_ID}" \
    "STATUS=launchd_submitted" \
    "PROFILE=${PROFILE}" \
    "MODE=${MODE}" \
    "SOAK_HOURS=${SOAK_HOURS}" \
    "RUNNER=${RESOLVED_RUNNER}" \
    "OUTPUT_ROOT=${OUTPUT_ROOT}" \
    "STATE_ROOT=${STATE_ROOT}" \
    "RUN_DIR=${RUN_DIR}" \
    "COMMAND_DISPLAY=${COMMAND_DISPLAY}" \
    "CWD=${REPO_ROOT}" \
    "SUPERVISOR_PID=0" \
    "CHILD_PID=" \
    "EXIT_CODE=" \
    "CAFFEINATE_ENABLED=0" \
    "STDOUT_PATH=${STDOUT_PATH}" \
    "STDERR_PATH=${STDERR_PATH}" \
    "HEARTBEAT_PATH=${HEARTBEAT_PATH}"
  cat "${RUN_DIR}/launchd.json"
  exit 0
fi

if [[ "${DETACH}" -eq 1 ]]; then
  mkdir -p "${RUN_DIR}"
  nohup "${SCRIPT_PATH}" \
    --hours "${SOAK_HOURS}" \
    --profile "${PROFILE}" \
    --mode "${MODE}" \
    --output-root "${OUTPUT_ROOT}" \
    --state-root "${STATE_ROOT}" \
    --run-id "${RUN_ID}" \
    --runner "${RESOLVED_RUNNER}" \
    > "${SUPERVISOR_LOG_PATH}" 2>&1 &
  DETACHED_PID="$!"
  write_json "${RUN_DIR}/launch.json" \
    "RUN_ID=${RUN_ID}" \
    "STATUS=detached" \
    "PROFILE=${PROFILE}" \
    "MODE=${MODE}" \
    "SOAK_HOURS=${SOAK_HOURS}" \
    "RUNNER=${RESOLVED_RUNNER}" \
    "OUTPUT_ROOT=${OUTPUT_ROOT}" \
    "STATE_ROOT=${STATE_ROOT}" \
    "RUN_DIR=${RUN_DIR}" \
    "COMMAND_DISPLAY=${COMMAND_DISPLAY}" \
    "CWD=${REPO_ROOT}" \
    "SUPERVISOR_PID=${DETACHED_PID}" \
    "CHILD_PID=" \
    "EXIT_CODE=" \
    "CAFFEINATE_ENABLED=0" \
    "STDOUT_PATH=${STDOUT_PATH}" \
    "STDERR_PATH=${STDERR_PATH}" \
    "HEARTBEAT_PATH=${HEARTBEAT_PATH}"
  cat "${RUN_DIR}/launch.json"
  exit 0
fi

mkdir -p "${STATE_ROOT}" "${RUN_DIR}"
if [[ -d "${LOCK_DIR}" ]]; then
  LOCK_PID=""
  if [[ -f "${LOCK_DIR}/supervisor.pid" ]]; then
    LOCK_PID="$(cat "${LOCK_DIR}/supervisor.pid" 2>/dev/null || true)"
  fi
  if [[ -n "${LOCK_PID}" ]] && kill -0 "${LOCK_PID}" 2>/dev/null; then
    echo "Another qualification soak supervisor is already running: ${LOCK_PID}" >&2
    exit 3
  fi
  rm -rf "${LOCK_DIR}"
fi
mkdir "${LOCK_DIR}"
printf "%s\n" "$$" > "${LOCK_DIR}/supervisor.pid"

CAFFEINATE_ENABLED=0
RUN_COMMAND=("${COMMAND[@]}")
if [[ "$(uname -s)" == "Darwin" ]] && command -v caffeinate >/dev/null 2>&1; then
  CAFFEINATE_ENABLED=1
  RUN_COMMAND=(caffeinate -dimsu "${COMMAND[@]}")
fi

CHILD_PID=""
HEARTBEAT_PID=""

cleanup() {
  local exit_code="$?"
  if [[ -n "${HEARTBEAT_PID}" ]] && kill -0 "${HEARTBEAT_PID}" 2>/dev/null; then
    kill "${HEARTBEAT_PID}" 2>/dev/null || true
  fi
  if [[ -n "${CHILD_PID}" ]] && kill -0 "${CHILD_PID}" 2>/dev/null; then
    kill "${CHILD_PID}" 2>/dev/null || true
    write_status "interrupted" "${exit_code}"
  fi
  rm -rf "${LOCK_DIR}"
}
trap cleanup EXIT
trap 'exit 130' INT TERM
trap '' HUP

write_status "running" ""
"${RUN_COMMAND[@]}" > "${STDOUT_PATH}" 2> "${STDERR_PATH}" &
CHILD_PID="$!"
printf "%s\n" "${CHILD_PID}" > "${RUN_DIR}/child.pid"
write_status "running" ""

(
  while kill -0 "${CHILD_PID}" 2>/dev/null; do
    date -u +"%Y-%m-%dT%H:%M:%SZ" > "${HEARTBEAT_PATH}"
    sleep 60
  done
) &
HEARTBEAT_PID="$!"

wait "${CHILD_PID}"
EXIT_CODE="$?"

if [[ -n "${HEARTBEAT_PID}" ]] && kill -0 "${HEARTBEAT_PID}" 2>/dev/null; then
  kill "${HEARTBEAT_PID}" 2>/dev/null || true
  wait "${HEARTBEAT_PID}" 2>/dev/null || true
fi
date -u +"%Y-%m-%dT%H:%M:%SZ" > "${HEARTBEAT_PATH}"

if [[ "${EXIT_CODE}" -eq 0 ]]; then
  write_status "completed_success" "${EXIT_CODE}"
else
  write_status "completed_nonzero" "${EXIT_CODE}"
fi

exit "${EXIT_CODE}"
