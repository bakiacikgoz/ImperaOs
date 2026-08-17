#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/5] Triggering a governance-protected request"
uv run imperaos chat \
  --profile default \
  --once "python kodunu düzelt ve test et" \
  --json > /tmp/imperaos_v03_demo.json

echo "[2/5] Parsing approval id"
APPROVAL_ID=$(uv run python - <<'PY'
import json
payload = json.load(open('/tmp/imperaos_v03_demo.json', 'r', encoding='utf-8'))
metrics = payload.get('metrics', {})
print(metrics.get('approval_id') or '')
PY
)

if [[ -z "$APPROVAL_ID" ]]; then
  echo "No approval id produced. Raw payload:"
  cat /tmp/imperaos_v03_demo.json
  exit 1
fi

echo "approval_id=$APPROVAL_ID"

echo "[3/5] Pending approvals"
uv run imperaos approval pending --json

echo "[4/5] Approve ticket"
uv run imperaos approval decide --id "$APPROVAL_ID" --approve --actor demo-operator --reason "demo approval"

echo "[5/5] Execute approved ticket"
uv run imperaos approval execute --id "$APPROVAL_ID" --actor demo-operator

echo "Demo completed."
