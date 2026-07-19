# ADR_ARTIFACT_005: Dynamic Form Validation

- Status: Accepted
- Owner: MAIN / Artifact Workspace
- Authoritative sources: approved artifact workspace plan sections 9.5, 12.12, 13 and Task 1.2; RJSF validation documentation
- Last verified: 2026-07-16 at Git commit `d1bb6c0097399064fc578976c466d2a8c693d482`
- Open decisions: final allowlisted Draft-07 keyword/format table and measured client validator limits

## Context

RJSF requires a `ValidatorType`. AJV normally compiles schemas at runtime, while AI-generated schemas are not known at build time. Enabling global `unsafe-eval` to support dynamic code generation would weaken the desktop CSP.

## Decision

Global `unsafe-eval` is forbidden. Form capability remains forced off until a CSP-safe custom `ValidatorType` passes production-build and no-network probes. The client validator implements only an allowlisted Draft-07 subset with bounded depth, node count, string length, regex complexity, and validation time. Remote `$ref`, executable content, script/event attributes, arbitrary formats, and runtime code generation are rejected.

RJSF is a renderer, not the authority. Every draft and submit request sends the schema version and data to the backend, which revalidates with the same allowlist plus workspace, classification, policy, and approval rules. A client PASS can never override a backend denial. Validation errors return bounded paths and reason codes without echoing sensitive values.

External continuation is a distinct governed action: saving a form submission record does not send email, call a webhook, or invoke another system. Continuation requires explicit policy and, when required, approval.

## Consequences

- `@rjsf/validator-ajv8` is probe/reference-only until no-eval behavior is proven for the dynamic subset.
- Backend/client parity fixtures and adversarial schema tests are mandatory.
- Unsupported schemas fail closed with an explainable reason and remain exportable as safe JSON where policy permits.
- Form GA is blocked until this ADR is implemented and CSP evidence is green.

## Rejected alternatives

- Global CSP weakening: rejected.
- Build-time precompiled validators alone: rejected because runtime AI schemas are not fixed at build time.
- Client-only validation: rejected because the renderer is outside the authoritative policy boundary.
