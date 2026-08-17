# Task 4.2 — Migrate serialized contracts to ImperaOS

## Goal

Atomically migrate all active product-branded serialized contract fields,
contract identities, runtime/team/session identifiers, and Operator Panel
contract-version values to the canonical ImperaOS namespace. This is a breaking,
strict migration with no aliases or dual-read compatibility.

## Canonical contract

- Runtime manifest field: `imperaos_version`.
- Provider retention metadata: `imperaos_retention`.
- OpenAI structured-output name: `imperaos_provider_response`.
- Default team IDs: `imperaos-team` and `imperaos-computer-use`.
- Test/mock session namespace: `imperaos_session`.
- Non-developer operator-attestation identity:
  `imperaos-non-developer-operator-attestation/v2`.
- Operator-validation drill identity:
  `imperaos-operator-validation-drill/v2`.
- Managed-KMS adapter drill identity:
  `imperaos-managed-kms-adapter-drill/v2`.
- Operator Panel contract version: `3.0` in Python, TypeScript, Rust, CLI,
  fixtures, and current contract documentation.

## Scope

- `imperaos/control_plane/field_evidence.py` and active attestation producers.
- Anthropic retention metadata and OpenAI structured-output producers.
- macOS/Windows bundled-runtime manifest build, verify, and release-gate logic.
- Python Operator Panel contract models/version constants, team artifacts/models,
  CLI/computer-use/snapshot payloads, and their tests.
- Operator Panel TypeScript bridge, capabilities, assistant/session mappers,
  preview fixtures, UI consumers, and tests.
- Tauri bridge contract-version constant and tests.
- Active team/session defaults, examples/templates, current operator contract
  documentation, scripts, and unsigned test/preview fixtures.
- Replace active former fixtures/expectations; do not leave an active legacy
  contract fixture in the final task state.

## Explicit boundaries

- Do not hand-edit generated JSON schemas. Task 4.3 owns deterministic
  regeneration after this task. Precisely classify all stale generated-schema
  values left behind.
- Do not edit signed evidence, hash-chain artifacts, historical finalization or
  release reports, RFCs, prior task reports, or archives.
- Do not rename the bundled-runtime directory, Tauri crate/package/binary/bundle
  identity, npm package, UI product copy, metrics, service labels, domains, repo
  URLs, or storage keys assigned to later phases.
- Do not change unrelated generic contract versions.
- Do not add dependencies or modify lock-file dependency graphs.
- Do not introduce field aliases, fallback reads, `_missing_` behavior, or
  compatibility shims for former names/versions.

## TDD requirements

Write failing tests first for at least:

1. The three canonical branded serialized field/name values and absence of their
   former counterparts.
2. All three `/v2` schema identities; validation rejects the former attestation
   identity.
3. Operator Panel version `3.0` across Python models, TypeScript capability/
   bridge behavior, and Rust constant/handshake behavior; former `2.0` payloads
   are rejected wherever the contract model or handshake validates versions.
4. Canonical default team and session identifiers in backend and preview/UI
   behavior.
5. macOS/Windows runtime manifests emit and verify only `imperaos_version`.

Construct former values dynamically in new negative tests where practical so
the active test tree does not reintroduce legacy product tokens. Record RED
commands/failure reasons before implementation.

## Verification

- Focused field-evidence, provider-native, operator-contract, team,
  computer-use, CLI, release-gate, TypeScript bridge/capability/preview, and Rust
  contract tests.
- Parse/validate active templates and fixtures.
- Full Python, full Vitest, Rust, and frontend production build.
- macOS/Windows build/verify script static or smoke tests available on Windows.
- Static scan proves former branded fields/IDs/schema identities are limited to
  generated schemas assigned to Task 4.3 and immutable historical records.
- Static scan classifies any remaining `2.0` contract versions, because unrelated
  generic contracts must not be changed accidentally.
- `git diff --check`, changed-file lint/format checks, no dependency/lock drift,
  brand inventory delta.

## Commit

Use the exact implementation commit subject:

`refactor: migrate serialized contracts to ImperaOS`

Create a separate verification/report commit if needed.
