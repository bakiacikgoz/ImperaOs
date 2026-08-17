# UI RFC-001: ImperaOS Operator Panel v0.5

## Status
Accepted (2026-03-03)

## Scope
Desktop operator panel (Tauri 2 + React) for approvals, runs, replay, artifacts, diagnostics, and settings.

## Decisions
- Architecture: mutations via CLI bridge, observability via artifacts (`status.json`, `events.jsonl`, `tasks.json`, `handoffs.json`, `audit_envelope.json`).
- Packaging: hybrid.
  - Dev: external CLI (`imperaos` on PATH or configured path).
  - Release: bundled runtime at `Contents/Resources/imperaos-runtime/python/bin/python`.
- Runtime hardening:
  - command allowlist only
  - no shell passthrough
  - env isolation (`PYTHONNOUSERSITE=1`, `PYTHONDONTWRITEBYTECODE=1`, no `PYTHONPATH`, allowlisted `IMPERAOS_*`).
- Compatibility handshake:
  - `imperaos --version`
  - `imperaos operator capabilities --json`
  - `imperaos doctor --profile <profile>`.
- Contract:
  - `BridgeResult<T>` with `ok/data` or `ok=false/error`.
  - error codes: `INVALID_INPUT`, `PATH_VIOLATION`, `TIMEOUT`, `CLI_NOT_FOUND`, `CLI_FAILED`, `PARSE_FAILED`, `SCHEMA_FAILED`, `CANCELLED`.
- Operator identity:
  - `operator_id` required for approve/reject/execute.
  - actor format is always `ui:<operator_id>`.
- Event tail contract (`events.jsonl`):
  - cursor is byte offset
  - partial lines are buffered (no event emission)
  - file shrink resets cursor and returns `reset=true`
  - bounded reads with `maxBytes` + `maxLines`
  - parse errors keep stream alive and return `truncated=true` + `badLineCount`.

## UI Behavior
- Default redaction-first view.
- Raw payload exposure requires `debugRaw` setting + explicit confirm.
- AI Assistant is a first-class shell route that preserves the existing ImperaOS
  sidebar, logo, topbar, right rail structure, and theme tokens.
- Assistant suggested prompts only seed the composer; they do not execute.
- Assistant turns stream through `assistant://event` and render status, token,
  activity, referenced run/artifact, warning, error, final, and approval states.
- Assistant approvals keep the governance lifecycle explicit:
  pending -> approved -> executed -> consumed. `Approve` and `Execute` are
  separate actions.
- Adaptive polling cadence:
  - running: 1.5s
  - blocked: 3.5s
  - completed/failed: 6s.

## Localization
- Bilingual (`tr`, `en`).
- Default language from OS locale (`tr` if locale starts with `tr`, otherwise `en`).

## Non-goals (v0.5)
- Workflow builder
- Policy IDE/editor
- IAM/SSO
- Windows builds
- Long-lived interactive assistant process. The initial integration uses one
  CLI process per assistant turn.
