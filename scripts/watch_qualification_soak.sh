#!/usr/bin/env bash
set -u

RUN_DIR=""
INTERVAL_SECONDS="10"
TAIL_LINES="12"
ONCE=0
CLEAR_SCREEN=1

usage() {
  cat <<'EOF'
Usage: scripts/watch_qualification_soak.sh [options] [RUN_DIR]

Live terminal monitor for a supervised qualification soak.

Options:
  --run-dir PATH       Supervisor run directory to watch
  --interval SECONDS   Refresh interval (default: 10)
  --tail LINES         Number of stderr/stdout tail lines (default: 12)
  --once               Render once and exit
  --no-clear           Do not clear the terminal between refreshes
  -h, --help           Show this help

If RUN_DIR is omitted, the script searches for the newest supervised soak under
the current repo and /private/tmp/imperaos_soak_*.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir)
      RUN_DIR="${2:?missing value for $1}"
      shift 2
      ;;
    --interval)
      INTERVAL_SECONDS="${2:?missing value for $1}"
      shift 2
      ;;
    --tail)
      TAIL_LINES="${2:?missing value for $1}"
      shift 2
      ;;
    --once)
      ONCE=1
      shift
      ;;
    --no-clear)
      CLEAR_SCREEN=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 64
      ;;
    *)
      if [[ -n "${RUN_DIR}" ]]; then
        echo "Unexpected extra argument: $1" >&2
        usage >&2
        exit 64
      fi
      RUN_DIR="$1"
      shift
      ;;
  esac
done

if [[ -z "${RUN_DIR}" ]]; then
  RUN_DIR="$(
    python3 - <<'PY'
from __future__ import annotations

from pathlib import Path

roots = [
    Path.cwd() / "artifacts" / "qualification" / "supervisor",
    Path("/private/tmp"),
]
run_dirs: list[Path] = []
local_root = roots[0]
if local_root.exists():
    run_dirs.extend(path for path in local_root.iterdir() if path.is_dir())
tmp_root = roots[1]
if tmp_root.exists():
    for workspace in tmp_root.glob("imperaos_soak_*"):
        supervisor = workspace / "artifacts" / "qualification" / "supervisor"
        if supervisor.exists():
            run_dirs.extend(path for path in supervisor.iterdir() if path.is_dir())

def mtime(path: Path) -> float:
    candidates = [
        path / "status.json",
        path / "launchd.json",
        path / "launch.json",
        path,
    ]
    existing = [candidate for candidate in candidates if candidate.exists()]
    return max(candidate.stat().st_mtime for candidate in existing)

run_dirs = [path for path in run_dirs if (path / "status.json").exists() or (path / "launchd.json").exists()]
if run_dirs:
    print(max(run_dirs, key=mtime))
PY
  )"
fi

if [[ -z "${RUN_DIR}" || ! -d "${RUN_DIR}" ]]; then
  echo "No supervised qualification soak run directory found." >&2
  echo "Pass it explicitly, for example:" >&2
  echo "  scripts/watch_qualification_soak.sh --run-dir /private/tmp/imperaos_soak_.../artifacts/qualification/supervisor/rc24h-..." >&2
  exit 2
fi

render_once() {
  python3 - "${RUN_DIR}" "${TAIL_LINES}" <<'PY'
from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

run_dir = Path(sys.argv[1]).expanduser()
tail_lines = int(sys.argv[2])
status_path = run_dir / "status.json"
launchd_path = run_dir / "launchd.json"
launch_path = run_dir / "launch.json"

def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "unreadable", "error": str(exc), "path": str(path)}
    return payload if isinstance(payload, dict) else {}

status = load_json(status_path)
launch = load_json(launchd_path) or load_json(launch_path)
payload = {**launch, **status}

def parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None

def start_from_run_id(run_id: object) -> datetime | None:
    if not isinstance(run_id, str):
        return None
    match = re.search(r"(\d{8}T\d{6}Z)", run_id)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)

def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "unknown"
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

def resolve_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd) / path
    return run_dir / path

now = datetime.now(UTC)
run_id = payload.get("run_id", run_dir.name)
soak_hours = float(payload.get("soak_hours") or 0)
duration_seconds = max(1.0, soak_hours * 3600)
started_at = parse_utc(launch.get("updated_at_utc")) or start_from_run_id(run_id) or parse_utc(status.get("updated_at_utc"))
elapsed_seconds = (now - started_at).total_seconds() if started_at else 0.0
progress = min(100.0, max(0.0, (elapsed_seconds / duration_seconds) * 100.0))
remaining_seconds = max(0.0, duration_seconds - elapsed_seconds)
finished_at = started_at + timedelta(seconds=duration_seconds) if started_at else None

bar_width = 36
filled = int((progress / 100.0) * bar_width)
bar = "#" * filled + "-" * (bar_width - filled)

heartbeat_path = resolve_path(payload.get("heartbeat_path")) or (run_dir / "heartbeat.txt")
heartbeat_value = heartbeat_path.read_text(encoding="utf-8").strip() if heartbeat_path.exists() else ""
heartbeat_at = parse_utc(heartbeat_value)
heartbeat_age = (now - heartbeat_at).total_seconds() if heartbeat_at else None
heartbeat_state = "missing"
if heartbeat_age is not None:
    heartbeat_state = "fresh" if heartbeat_age <= 180 else "stale"

stderr_path = resolve_path(payload.get("stderr_path")) or (run_dir / "qualification.stderr.log")
stdout_path = resolve_path(payload.get("stdout_path")) or (run_dir / "qualification.stdout.json")
status_text = str(payload.get("status") or "unknown")
exit_code = payload.get("exit_code")
supervisor_pid = payload.get("supervisor_pid")
child_pid = payload.get("child_pid")
caffeinate = payload.get("caffeinate_enabled")

def pid_state(value: object) -> str:
    try:
        pid = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "unknown"
    if pid <= 0:
        return "unknown"
    try:
        import os

        os.kill(pid, 0)
    except ProcessLookupError:
        return "missing"
    except PermissionError:
        return "permission-denied"
    return "alive"

supervisor_state = pid_state(supervisor_pid)
child_state = pid_state(child_pid)

print("ImperaOS Qualification Soak Monitor")
print("=" * 72)
print(f"Run id      : {run_id}")
print(f"Status      : {status_text}    Exit: {exit_code}")
print(f"Progress    : [{bar}] {progress:6.2f}%")
print(f"Elapsed     : {fmt_duration(elapsed_seconds)} / {fmt_duration(duration_seconds)}")
print(f"Remaining   : {fmt_duration(remaining_seconds)}")
print(f"Started     : {fmt_dt(started_at)}")
print(f"ETA         : {fmt_dt(finished_at)}")
print(f"Heartbeat   : {heartbeat_value or 'missing'} ({heartbeat_state})")
if heartbeat_age is not None:
    print(f"HB age      : {fmt_duration(heartbeat_age)}")
print(
    "Supervisor  : "
    f"{supervisor_pid} ({supervisor_state})    "
    f"Child: {child_pid} ({child_state})    Caffeinate: {caffeinate}"
)
print(f"Run dir     : {run_dir}")
print(f"stderr log  : {stderr_path}")
print(f"stdout json : {stdout_path}")
if status_text == "running" and heartbeat_state != "fresh":
    print("WARNING    : running status has no fresh heartbeat")
if status_text == "running" and child_state == "missing":
    print("WARNING    : running status has a missing child process")

def tail(path: Path, lines: int) -> list[str]:
    if not path.exists():
        return ["<missing>"]
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return ["<empty>"]
    return text.splitlines()[-lines:]

print("")
print(f"Last {tail_lines} stderr lines")
print("-" * 72)
for line in tail(stderr_path, tail_lines):
    print(line)

if stdout_path.exists() and stdout_path.stat().st_size > 0:
    print("")
    print(f"Last {tail_lines} stdout lines")
    print("-" * 72)
    for line in tail(stdout_path, tail_lines):
        print(line)
PY
}

while true; do
  if [[ "${CLEAR_SCREEN}" -eq 1 ]]; then
    clear
  fi
  date
  render_once
  if [[ "${ONCE}" -eq 1 ]]; then
    break
  fi
  sleep "${INTERVAL_SECONDS}"
done
