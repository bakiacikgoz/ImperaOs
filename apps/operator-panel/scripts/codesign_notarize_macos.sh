#!/usr/bin/env bash
set -euo pipefail

APP_PATH="${1:?usage: codesign_notarize_macos.sh <App.app> <artifact.dmg>}"
DMG_PATH="${2:?usage: codesign_notarize_macos.sh <App.app> <artifact.dmg>}"

: "${SIGNING_IDENTITY:?SIGNING_IDENTITY is required}"

NOTARY_AUTH_MODE=""
if [[ -n "${APPLE_NOTARY_KEY_FILE:-}" || -n "${APPLE_NOTARY_KEY_ID:-}" || -n "${APPLE_NOTARY_ISSUER_ID:-}" ]]; then
  : "${APPLE_NOTARY_KEY_FILE:?APPLE_NOTARY_KEY_FILE is required for API key mode}"
  : "${APPLE_NOTARY_KEY_ID:?APPLE_NOTARY_KEY_ID is required for API key mode}"
  NOTARY_AUTH_MODE="api-key"
elif [[ -n "${APPLE_ID:-}" || -n "${APPLE_TEAM_ID:-}" || -n "${APPLE_APP_PASSWORD:-}" ]]; then
  : "${APPLE_ID:?APPLE_ID is required for Apple ID mode}"
  : "${APPLE_TEAM_ID:?APPLE_TEAM_ID is required for Apple ID mode}"
  : "${APPLE_APP_PASSWORD:?APPLE_APP_PASSWORD is required for Apple ID mode}"
  NOTARY_AUTH_MODE="apple-id"
else
  echo "[release] missing notarization auth. Provide API key or Apple ID credentials." >&2
  exit 5
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "[release] macOS only" >&2
  exit 2
fi

if [[ ! -d "${APP_PATH}" ]]; then
  echo "[release] app not found: ${APP_PATH}" >&2
  exit 3
fi

if [[ ! -f "${DMG_PATH}" ]]; then
  echo "[release] dmg not found: ${DMG_PATH}" >&2
  exit 4
fi

submit_notary() {
  local no_s3="${1:-0}"
  local cmd=(xcrun notarytool submit "${DMG_PATH}")

  if [[ "${NOTARY_AUTH_MODE}" == "api-key" ]]; then
    cmd+=(--key "${APPLE_NOTARY_KEY_FILE}" --key-id "${APPLE_NOTARY_KEY_ID}")
    if [[ -n "${APPLE_NOTARY_ISSUER_ID:-}" ]]; then
      cmd+=(--issuer "${APPLE_NOTARY_ISSUER_ID}")
    fi
  else
    cmd+=(--apple-id "${APPLE_ID}" --team-id "${APPLE_TEAM_ID}" --password "${APPLE_APP_PASSWORD}")
  fi

  if [[ "${no_s3}" == "1" ]]; then
    cmd+=(--no-s3-acceleration)
  fi

  cmd+=(--wait)
  "${cmd[@]}"
}

echo "[release] codesigning app"
codesign --force --deep --options runtime --timestamp --sign "${SIGNING_IDENTITY}" "${APP_PATH}"
codesign --verify --deep --strict --verbose=2 "${APP_PATH}"

echo "[release] codesigning dmg"
codesign --force --timestamp --sign "${SIGNING_IDENTITY}" "${DMG_PATH}"
codesign --verify --verbose=2 "${DMG_PATH}"

echo "[release] notarizing dmg (mode=${NOTARY_AUTH_MODE})"
if ! submit_notary 0; then
  echo "[release] notarization failed, retrying with --no-s3-acceleration"
  submit_notary 1
fi

echo "[release] stapling"
xcrun stapler staple "${APP_PATH}"
xcrun stapler validate "${APP_PATH}"
xcrun stapler staple "${DMG_PATH}"
xcrun stapler validate "${DMG_PATH}"

echo "[release] local quarantine/spctl check"
QUARANTINE_TAG="0081;$(date +%s);ImperaOS;"
xattr -w com.apple.quarantine "${QUARANTINE_TAG}" "${APP_PATH}"
spctl --assess --type execute --verbose=4 "${APP_PATH}"

echo "[release] PASS: codesign + notarize + staple + quarantine check"
echo "[release] NOTE: clean-machine Gatekeeper check is still required as final manual gate."
