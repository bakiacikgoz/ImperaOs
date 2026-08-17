# Approval execution reconciliation

Approval execution first claims a ticket atomically as `executing` with a unique attempt ID. Only that attempt may finalize it as `executed` or `execution_failed`.

If a process stops while the ticket is `executing`:

1. Find audit and evidence records by approval ID and execution attempt ID.
2. For an external system, use its idempotency/result lookup; do not submit again.
3. Verify proposal, request, policy, and result hashes.
4. If the outcome remains uncertain, leave the ticket reconciliation-required. Never move it back to `approved`.
5. A privileged reconciler may finalize only with execution evidence or non-execution/failure proof. A new attempt requires a new approval/run.

Generic external-agent execution is blocked without an idempotent gateway. Generic device execution is blocked without the qualified vision resume path.
