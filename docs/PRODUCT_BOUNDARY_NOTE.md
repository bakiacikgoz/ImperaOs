# Product Boundary Note

## Supported Positioning

ImperaOS is positioned as a:

> chat-first operator-grade AI workstation with a governed computer-use runtime

This implies:

- natural-language chat as a first-class control surface
- local or self-hosted capable operation
- policy-governed execution
- approval-aware mutations
- replayable and auditable traces
- visible action timelines and operator interrupts
- bounded execution surfaces in the current release, with expansion toward full device control
- enterprise qualification discipline

## Not Supported

ImperaOS should not be presented as:

- a consumer novelty chatbot
- a generic autonomous agent framework
- an uncontrolled browser/computer agent
- a digital worker that autonomously does everything without visibility or control

## UI Product Boundary

The operator panel is now a chat-first operator workspace. It is not a thin shell for every CLI command and not a hidden-autonomy surface.

Parity means workflow completion with transcript, approvals, state, timeline, and artifacts visible in one place.

## Computer Use Boundary

Computer use remains a supervised execution subsystem with:

- approval gates
- bounded allowlists
- replay and evidence
- fail-closed defaults
- opt-in real Safari execution that depends on local macOS automation permissions

The current codebase still ships a bounded browser-first foundation. The product target is a broader desktop/browser/file runtime, but it must remain observable, interruptible, and fail-closed.

Real Safari qualification is not zero-config. Local validation still requires Safari automation permissions, System Events / Accessibility access, and Safari's manual Developer setting `Allow JavaScript from Apple Events`.

The currently qualified download path is scoped and fail-closed, but it is only qualified for direct-link browser artifacts. Authenticated or session-bound download flows still need deeper qualification.

## Provider Governance Layer Boundary

The model provider governance layer is a fail-closed registry, policy, redaction, and evidence boundary for model calls. It may be described as experimental/gated provider governance with local-first defaults and OpenAI-compatible adapter support.

It must not be described as:

- a key manager
- a cloud provider broker
- an unrestricted model proxy
- proof that remote/cloud providers are enabled by default
- proof that confidential data can automatically leave the local or self-hosted boundary

Remote/cloud provider calls require explicit configuration and remain disabled by default.

## Vision-First Runtime Boundary

The vision-first runtime is a supervised foundation, not an unrestricted autonomous desktop agent. It may be described as a universal vision-first runtime foundation with policy, approval, replay, and deterministic test coverage.

It must not be described as:

- uncontrolled full-computer autonomy
- qualified Windows live desktop automation
- a password, payment, wallet, or MFA automation agent
- reliable across arbitrary real-world apps without platform qualification evidence

The safe product claim is: the runtime can observe via hash-addressed visual contracts, plan typed actions, classify risk, require approval, record redacted replay evidence, and fail closed when a provider or qualification is missing.
## Vision-First Computer-Use Boundary

The current claim is limited to a supervised macOS vision-first pilot in step-approval mode. Deterministic mock qualification supports development confidence, not a broad real-world reliability claim. Live macOS qualification requires local permissions and a configured provider. Windows live computer-use remains disabled until signed qualification evidence exists.
