# Agent Control Plane Architecture

The control-plane layer is additive. It does not replace the existing
governance, team runtime, enterprise identity/signing, support bundle or
computer-use implementations.

```text
Operator Console / CLI
      |
      v
Control Plane
  - Agent Registry
  - Run Coordinator
  - Policy Simulation
  - Evidence Pack Builder
  - Claim Guard
  - External Adapter Contracts
      |
      +--> Governance Runtime
      +--> Team/Core Runtime
      +--> Enterprise Identity and Signing
      +--> Replay, Artifacts, Support Bundle
      +--> Computer-Use Adapter, disabled unless qualified
```

State is local by default:

```text
.imperaos/control-plane/agents.json
.imperaos/control-plane/runs/<run_id>.json
artifacts/control-plane/evidence/<run_id>/manifest.json
```
