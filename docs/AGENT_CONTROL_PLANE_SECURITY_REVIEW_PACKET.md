# Agent Control Plane Security Review Packet

## Boundary

ImperaOS / ImperaOS is self-hosted and local-first. The v1 control plane does
not start a network listener by default and does not claim multi-tenant cloud
readiness.

## Controls

- Policy unavailable paths fail closed.
- Enterprise mutations require identity assertions when enterprise identity is enabled.
- Approval tickets remain separate from execution and evidence.
- Evidence manifests include item SHA-256 hashes and enterprise signing metadata.
- Computer-use is disabled unless platform qualification evidence enables a supervised path.

## Operator Responsibilities

Operators must maintain trusted signing keys, protect identity assertions,
review approval context before execution, keep support bundles redacted, and
avoid public desktop/computer-use claims without release evidence.
