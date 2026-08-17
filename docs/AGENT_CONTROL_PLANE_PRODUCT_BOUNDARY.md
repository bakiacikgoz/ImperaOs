# Agent Control Plane Product Boundary

ImperaOS / ImperaOS is a constrained, self-hosted Agent Control Plane for
governed AI agent production readiness. Its product promise is policy
evaluation, approval lifecycle, verified identity, audit/replay, signed
evidence, qualification gates, and fail-closed execution boundaries before an
agent is trusted in production-like workflows.

## Supported Direction

| Surface | Boundary |
|---|---|
| Control Plane Core | Agent registry, run coordination, policy simulation, claim guard, readiness and evidence contracts. |
| Governed Runtime | Existing core and team runtime remain the execution backends behind policy and approval gates. |
| Operator Console | Operator Panel is the control-plane console for agents, runs, approvals, evidence, policy and execution surfaces. |
| Governed External Provider Boundary | OpenAI Responses and Anthropic Messages may be exercised through offline conformance and dry-run/canary-live guarded invocation. Evidence is hash-only, raw persistence is off, server tools are denied, and custom tools stay proposal-only. |
| Qualified Execution Surfaces | Computer-use remains fail-closed, opt-in, supervised and qualification-gated. |

## No-Ship Claims

The project must not claim unrestricted desktop automation, unrestricted
external provider execution, public desktop release readiness, cross-platform
live computer-use qualification, multi-tenant SaaS readiness, or safe
irreversible action execution without explicit approval evidence.

## Hat A / Hat B

Hat A is the self-hosted source/CLI/enterprise control-plane boundary. Hat B is
the public desktop installer boundary and remains blocked until signing,
notarization and clean-machine evidence are present.
