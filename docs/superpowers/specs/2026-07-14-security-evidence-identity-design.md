# ImperaOS Security and Evidence Identity Design

Date: 2026-07-14
Status: Approved by delegated user authority
Plan task: Phase 7, Task 7.2

## Objective

Remove former product identity from active security defaults and evidence-producing gates while preserving redaction, signature, revocation, no-ship, and approval semantics. Keep historical evidence and serialized contract versions unchanged.

## Current State

The Task 7.1 inventory leaves six active security/evidence consumers with former identity:

- the development fallback for `IMPERAOS_AUDIT_SECRET`;
- the deterministic enterprise-fixture signing seed;
- the managed-KMS drill temporary-directory prefix;
- the organization owner emitted by the memory-governance gate;
- the manual pull-request URL emitted by enterprise workspace readiness;
- the product-complete PR body description.

The environment variable and managed-KMS schema version are already canonical. These remaining literals influence development hashes, generated fixture keys, temporary paths, evidence payloads, and operator-facing command packs, so they must move together and receive a dedicated regression contract.

## Chosen Approach

Apply an atomic six-consumer identity migration:

- `imperaos-dev-secret` becomes `imperaos-dev-secret` only as the no-environment development fallback;
- the fixture seed domain becomes `imperaos-enterprise-fixture`;
- the KMS temp prefix becomes `imperaos-managed-kms-`;
- the organization owner becomes `imperaos`;
- the prepared manual PR URL targets `bakiacikgoz/ImperaOS`;
- the product-complete summary names only `ImperaOS`.

Add a generic former-brand scan over these active files plus behavioral assertions for the default audit HMAC and operator-facing generated text. This closes the generic-scan coverage opportunity recorded in Task 7.1 for the new Task 7.2 boundary.

## Security and Evidence Contract

| Surface | Canonical value |
|---|---|
| Audit development fallback | `imperaos-dev-secret` |
| Audit environment override | `IMPERAOS_AUDIT_SECRET` (unchanged) |
| Enterprise fixture seed domain | `imperaos-enterprise-fixture:<key-id>` |
| Managed-KMS temporary prefix | `imperaos-managed-kms-` |
| Memory governance organization owner | `imperaos` |
| Prepared repository URL | `https://github.com/bakiacikgoz/ImperaOS` |
| Product-complete description | `Product-complete closure gate for ImperaOS.` |

The fallback secret is explicitly a development default, not a production credential. Production behavior continues to use the environment override. Changing the fallback intentionally changes deterministic development audit HMACs when no override is supplied; it does not weaken the algorithm or expose raw content.

## Components and Data Flow

`redact_audit_payload()` continues to HMAC sensitive text with SHA-256. The environment override retains priority; only the fallback key's identity changes. The enterprise fixture generator continues to derive an Ed25519 private key deterministically from SHA-256 of a namespaced seed, but the namespace becomes ImperaOS.

The managed-KMS drill still creates an isolated temporary directory, generates current/next keys, verifies revocation behavior, writes hash-only evidence, and deletes the directory through `TemporaryDirectory`. Only the OS-visible prefix changes.

The memory-governance gate emits the same organization-scoped proposal with a canonical owner. The readiness gate still prepares, but never executes, push/PR commands. Its manual URL becomes canonical; no remote repository is renamed or contacted. The product-complete gate retains the same no-ship and external-requirement text with a canonical product summary.

## Test Design

Follow RED-GREEN-REFACTOR:

1. Add `tests/test_security_evidence_identity.py` before production edits.
2. Construct former tokens in the test and reject them generically across all six active files.
3. Assert every exact canonical identity.
4. With `IMPERAOS_AUDIT_SECRET` absent, verify the redacted audit hash equals HMAC-SHA256 using `imperaos-dev-secret`; separately prove an explicit environment override still wins.
5. Call the readiness command builder and product-complete PR renderer to verify generated text, not only source literals.
6. Observe RED, then apply only the six identity replacements.
7. Run the new contract and existing governance, fixture/enrollment, managed-KMS, memory-governance, readiness, and product-complete suites.
8. Run Ruff and compile checks for modified Python files.
9. Run inventory at the committed implementation SHA and record later-phase findings.

## Phase Boundaries

Task 7.2 does not change:

- `IMPERAOS_AUDIT_SECRET` or any other environment-variable name;
- HMAC-SHA256, Ed25519, integrity, signature, key rotation, or revocation algorithms;
- serialized schema versions, purpose strings, JSON field names, evidence filenames, or compatibility contracts already free of former identity;
- committed historical evidence, release decisions, old reports, or compatibility documentation;
- the actual Git remote, GitHub repository name, secrets, branches, pull requests, or releases;
- broad documentation, examples, fixtures, and binary metadata assigned to later phases.

## Error and Safety Behavior

- Explicit audit secrets still override the development fallback.
- Redacted raw values remain absent from evidence.
- Fixture signatures and KMS revocation verification remain fail-closed.
- Readiness output still contains no force-push or merge command and performs no remote action.
- Product closure retains all no-ship conditions.
- Temporary test and drill paths must be cleaned and must never be created directly under `C:\`.

## Acceptance Criteria

- All six active files contain their canonical identity and no former brand token.
- Default audit HMAC uses the ImperaOS fallback; environment override behavior passes.
- Enterprise fixtures, enrollment evidence, managed-KMS drill, memory governance, readiness, and product closure tests pass.
- Generated readiness and product-complete text contains ImperaOS and no former brand.
- Ruff and Python compilation pass.
- No external GitHub, KMS, signing, monitoring, or release action occurs.
- Remaining inventory is documented without weakening the brand gate.

## Commit Boundary

The implementation commit subject must be exactly:

`refactor: secure evidence under ImperaOS identity`
