# Computer-Use Security Boundary

## Denied By Default

The vision-first computer-use runtime denies or stops before:

- terminal control unless policy changes from `deny`
- sensitive surfaces such as passwords, keychains, wallets, payments, and security settings
- stale approval snapshots
- invalid strict-JSON provider responses
- invalid, unsupported, or low-confidence candidate vision actions
- repeated action digests and consecutive wait loops
- missing provider or missing permissions
- stale or mismatched qualification reports

The candidate action planner is a hygiene and selection layer only. Policy
remains the source of truth for sensitive surfaces, terminal control, approval
requirements, and platform qualification.

Approval resume requires an executed, unconsumed ticket and a matching
vision-step snapshot. An `approved` ticket alone does not authorize execution,
and stale or mismatched snapshots fail closed before input is applied.

Multi-step vision runs stop before input execution when the same action digest is
selected again or when consecutive `wait` actions exceed
`max_consecutive_wait_actions`. These guards do not replace semantic
verification or approval policy.

## macOS Permission Boundary

ImperaOS can detect and report permission blockers. It must not grant permissions automatically or bypass macOS consent controls.

## Platform Boundary

macOS has a supervised qualification path. Windows and Linux remain:

```text
not_qualified / liveEnabled=false
```

No documentation or UI should claim unrestricted or cross-platform live desktop automation.
