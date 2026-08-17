#!/usr/bin/env bash
set -euo pipefail

MODEL_TAG="lfm2.5-thinking:1.2b"

log() {
  printf "[bootstrap] %s\n" "$*"
}

fail() {
  printf "[bootstrap][error] %s\n" "$*" >&2
  exit "${2:-1}"
}

if [[ "$(uname -s)" != "Darwin" ]]; then
  fail "This bootstrap script is only for macOS." 2
fi

if ! command -v brew >/dev/null 2>&1; then
  fail "Homebrew is required. Install from https://brew.sh first." 3
fi

if ! command -v uv >/dev/null 2>&1; then
  log "Installing uv..."
  brew install uv || fail "Failed to install uv." 4
fi

if ! command -v ollama >/dev/null 2>&1; then
  log "Installing Ollama..."
  brew install ollama || fail "Failed to install Ollama." 5
fi

if ! pgrep -x ollama >/dev/null 2>&1; then
  log "Starting Ollama daemon..."
  nohup ollama serve >/tmp/imperaos-ollama.log 2>&1 &
  sleep 2
fi

for _ in {1..10}; do
  if ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

ollama list >/dev/null 2>&1 || fail "Ollama daemon is not responding." 6

log "Pulling model ${MODEL_TAG}..."
ollama pull "${MODEL_TAG}" || fail "Model pull failed for ${MODEL_TAG}." 7

log "Syncing Python environment..."
uv sync --python 3.11 --extra dev || fail "uv sync failed." 8

log "Bootstrap completed successfully."
