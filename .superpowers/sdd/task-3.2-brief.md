# Task 3.2 — Adopt the IMPERAOS environment namespace

## Goal

Move every active, project-owned environment variable from `IMPERAOS_` or
`IMPERAOS_` to the canonical `IMPERAOS_` prefix. This is a strict rename: the
old prefixes must not be read, forwarded, documented as active, or retained as
compatibility aliases.

## Canonical contract

- `branding/identity.json` remains the source of truth and declares
  `envPrefix: "IMPERAOS"`.
- `RuntimeConfig.env_prefix` and TOML defaults are `IMPERAOS`.
- Preserve every existing suffix exactly; only replace the product prefix.
- Keep provider-standard variables such as `OPENAI_API_KEY`,
  `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, and `COMPANY_LLM_API_KEY` unchanged.
- The Tauri environment allow-list accepts `IMPERAOS_` and rejects
  `IMPERAOS_`/`IMPERAOS_`.
- A legacy-only environment must not affect resolved configuration.
- Secret values must remain redacted from resolved configuration output and
  must never be asserted or printed in test output.

## Scope

- `imperaos/runtime/config.py` and all Python environment lookups/messages.
- Computer-use qualification and opt-in flags.
- Provider canary, provider API-key aliases, audit signing/redaction, identity,
  and bridge configuration variables.
- `apps/operator-panel/src/bridge.ts` and
  `apps/operator-panel/src-tauri/src/bridge.rs`.
- Active workflows, scripts, configuration profiles, examples, operator
  guides, runbooks, and tests.
- Rename local build-script variables such as `IMPERAOS_VERSION` where they
  are active implementation details, without changing deferred manifest/schema
  field names owned by later phases.

## Explicit boundaries

- Do not change state roots, package/distribution/CLI names, dependencies, or
  lock-file dependency graphs.
- Do not change runtime kinds/enums (`IMPERAOS_CORE`, `IMPERAOS_TEAM`) or their
  serialized values; Task 4 owns those domain contracts.
- Do not change generated schemas, metrics, event names, team identifiers, or
  bundled-runtime manifest field names that are assigned to later phases.
- Do not edit signed evidence, immutable snapshots, historical reports, or
  archived artifacts. Record remaining historical matches in the task report.
- Do not add fallbacks, aliases, shims, or dual-read behavior.

## TDD requirements

Write failing tests first for at least:

1. `IMPERAOS_` values override profile/default configuration.
2. `IMPERAOS_` and `IMPERAOS_` values are ignored in strict mode.
3. `IMPERAOS_CONFIG_ROOT` is honored and the old config-root variable is not.
4. The Rust bridge allow-list accepts canonical project variables and rejects
   both legacy prefixes while retaining approved provider-standard keys.
5. Redaction masks secret-bearing `IMPERAOS_` keys without exposing their
   values.

## Verification

- Targeted Python configuration/environment tests.
- Relevant computer-use, provider, enterprise, and CLI tests.
- Operator Panel Vitest suite and Rust bridge tests.
- Full Python test suite with the known Windows short `--basetemp` workaround.
- Static scan of active source/config/workflow/script/test paths for project
  legacy environment prefixes. Any remaining `IMPERAOS_` match must be a
  Task-4 enum/domain identifier or classified immutable historical evidence.
- Run the repository brand inventory and report the before/after counts.

## Commit

Use the exact implementation commit subject:

`refactor: adopt IMPERAOS environment namespace`

Create a separate verification/report commit if needed.
