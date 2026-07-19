# RFC_COMPUTER_USE_001

## Status
Accepted for `v0.8-pilot`

## Framing

Computer use is a supervised execution subsystem, not a generic tool call and not a consumer-facing autonomy claim.

Pilot scope:

- macOS-first
- browser allowlist only
- authenticated session required
- `dry_run` and `step_approval` only
- replayable, auditable, fail-closed

Out of scope for the pilot:

- generic desktop automation
- login, MFA, password managers
- banking, billing, payments
- admin/security panes
- unrestricted OCR-first execution

## Subsystem

The subsystem lives under `imperaos/computer_use/` and is split into:

- `session.py`: orchestrates guarded dry-run and step-approval sessions
- `planner.py`: emits bounded browser task plans
- `perception.py`: perception source priority and fingerprinting
- `actions.py`: device action hash and approval snapshot payload construction
- `guards.py`: fail-closed hard-stop evaluation
- `policy.py`: browser allowlist policy and risk mapping
- `recorder.py`: redacted evidence artifact generation
- `models.py`: typed pilot contracts
- `adapters/browser_adapter.py`: browser adapter interface

## Approval Contract

Device/browser approvals reuse the existing approval store and approval lifecycle.

`ApprovalTicket.snapshot` for device actions contains:

- `kind=device_action`
- `target_ref`
- `window_or_tab_identity`
- `window_identity`
- `app_identity`
- `selector_context`
- `perception_fingerprint`
- `action_plan`
- `execution_contract`

## Hard Stops

The pilot must stop on:

- `unknown_visual`
- `selector_ambiguous`
- `unexpected_modal`
- `focus_drift`
- `sensitive_surface_detected`
- `confidence_below_threshold`
- `policy_denied`

## Evidence

Default evidence is minimized and redacted:

- screenshot hash
- selector trace
- redacted fingerprint
- minimal accessibility/DOM subset

Raw screenshot retention is pilot/debug only and must remain policy-gated.
