# Governed Memory Layer

Governed Memory v1 adds an additive `memory.v3` authority layer over the existing local memory subsystem.

Default posture:

- `memory.v3_enabled=false` in every profile.
- Raw prompt, raw response, raw artifact content, and primary UI raw-content display are disabled.
- Writes are policy evaluated before persistence.
- Organization-scoped writes return `approval_required`; they are not committed by default.
- Secret-like content is denied before store or index writes.
- Retrieval returns redacted summaries only when explicitly requested.

Main surfaces:

- CLI: `imperaos memory doctor`, `memory propose`, `memory retrieve`, `memory stats`, `memory index status`, `memory eval`.
- Control Plane snapshot: `memoryGovernance`.
- Operator Panel route: `Memory Governance`.
- Gates: `make governed-memory-v1-gate`.

Artifacts are hash-only/redacted under `artifacts/memory-governance/`.
