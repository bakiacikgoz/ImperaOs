# ImperaOS

## Core integrity invariants

- Product readiness starts at `not_run`; only an executed check with evidence may become `pass`.
- Provider credentials are configured in the trusted host environment. The Operator Panel never accepts or persists raw API keys.
- Governed execution follows `pending -> approved -> executing -> executed -> consumed`. A process interruption after the atomic `executing` claim is reconciliation-required and is never retried automatically.
- `imperaos` is the canonical CLI and Python package. `binliquid` and `aegis` are temporary compatibility aliases and emit a deprecation warning.
- The default state root is `.imperaos`. Legacy `.binliquid` state is copied only by the explicit `imperaos migrate legacy-state` dry-run/copy/verify workflow; the source is never deleted.
- Computer-use remains blocked when platform qualification, observation freshness, or policy proof is missing.

Legacy state migration preview:

```bash
imperaos migrate legacy-state --source .binliquid --destination .imperaos --dry-run --json
```

Verified non-destructive copy:

```bash
imperaos migrate legacy-state --source .binliquid --destination .imperaos --copy --verify --json
```

**ImperaOS** is a self-hosted Agent Control Plane for governed AI
agent production readiness. It helps operators register agents, simulate policy
decisions, enforce approval lifecycle, bind runs to verified identity, preserve
audit/replay artifacts, export signed evidence packs, and block unsupported
release claims before agents are trusted in production-like workflows.

Product boundary: [Agent Control Plane Product Boundary](docs/AGENT_CONTROL_PLANE_PRODUCT_BOUNDARY.md).
Governed Memory v1 is documented in [Governed Memory Layer](docs/GOVERNED_MEMORY_LAYER.md).

ImperaOS currently provides four control-plane surfaces:

1. **Control Plane Core** — agent registry, run coordination, policy simulation, evidence pack export/verify, readiness checks and claim guard.
2. **Governed Runtime** — existing core and team runtime execution backends with planning, routing, scoped memory, policy decisions, approvals, checkpointing and replayable audit traces.
3. **Operator Console** — a Tauri-based control surface for dashboard, agents, runs, approvals, evidence, policy, system state and execution surfaces.
4. **Qualified Execution Surfaces** — fail-closed execution adapters. Computer-use is retained only as a supervised, opt-in, qualification-gated surface and is disabled by default for live desktop operation.

> **Status summary**
>
> Control Plane Core is the primary product direction. Governed Runtime and Team
> Runtime are the execution backends. Enterprise deployment readiness remains a
> constrained self-hosted envelope that requires signed qualification and GA
> readiness evidence for broader claims. Computer-use is a fail-closed,
> qualification-gated execution surface; live desktop automation is disabled by
> default and must not be described as generally available across platforms.

---

## Current Status

### Supported baseline

| Area | Status | Notes |
|---|---:|---|
| Linux x64 core runtime | Supported | Primary runtime and server-side validation target. |
| macOS tooling | Supported | Operator tooling, Tauri release proof, and local validation workflows. |
| Windows x64 tooling | Supported | Core CLI, operator panel, bundled runtime, and release-candidate validation paths. |
| Team Runtime | Pilot-hardened | Controlled/restricted profiles only; bounded concurrency and replay verification are implemented. |
| Enterprise profile | Constrained readiness | Self-hosted single-tenant profile with identity/RBAC, signing, baseline checks, metrics, support bundle, and GA readiness reporting. |
| Model provider governance | Experimental/gated | Registry, policy simulation, redacted envelopes, and OpenAI-compatible adapter are present. Remote/cloud providers are disabled by default. |
| Vision-first computer-use foundation | Implemented behind gates | Platform model, policy, approval, replay, qualification schema, and fail-closed platform gates exist. |
| Live macOS vision computer-use | Not qualified | Disabled until local provider, permissions, and qualification evidence are present. |
| Live Windows computer-use | Not qualified | Disabled with `WINDOWS_COMPUTER_USE_NOT_QUALIFIED`. |
| Live Linux computer-use | Not qualified | Disabled with `LINUX_COMPUTER_USE_NOT_QUALIFIED`; Wayland/X11/session qualification is required. |

### What ImperaOS is not yet

ImperaOS should **not** currently be marketed as:

- an unrestricted enterprise-wide multi-agent orchestration system,
- a universally production-ready high-concurrency agent platform,
- a fully qualified live desktop automation product across macOS, Windows, and Linux,
- a system that can safely execute irreversible user actions without explicit approval,
- a public desktop release without signing/notarization/clean-machine evidence,
- a cloud-hosted multi-tenant control plane.

---

## Architecture Overview

```text
User / Operator
      |
      v
Operator Panel / CLI / Thin Shell
      |
      v
Core Runtime
  - planner
  - router
  - provider chain
  - specialist experts
  - memory
  - governance policy
      |
      +--> Team Runtime
      |      - DAG execution
      |      - handoff
      |      - scoped memory
      |      - bounded concurrency
      |      - checkpoint/replay
      |
      +--> Computer-Use Runtime
             - observe
             - interpret
             - decide
             - classify risk
             - approve if needed
             - execute
             - verify
             - checkpoint
             - replay/audit
```

### Core design principles

- **Local-first and private by default**: web access and persistent traces are disabled unless explicitly configured.
- **Fail-closed governance**: unsafe, unknown, stale, or unqualified paths stop instead of guessing.
- **Approval lifecycle discipline**: approvals follow `pending -> approved -> executed -> consumed`; approval alone does not authorize execution.
- **Typed contracts**: planner outputs, expert payloads, operator-panel schemas, computer-use actions, and qualification reports are validated.
- **Replayable operations**: key runtime paths produce audit-grade traces and replay verification artifacts.
- **Qualification before claims**: implementation alone is not enough; platform support requires executed evidence.

---

## Feature Status

| Feature | Status | Notes |
|---|---:|---|
| Provider chain | Working | `auto -> ollama -> transformers`; doctor checks active/fallback chain. |
| Planner strict schema | Working | Deterministic fallback and adversarial tests included. |
| Orchestrator controls | Working | Timeout, retry, circuit breaker, and tool budget enforcement. |
| Rule router | Working | Active by default in `balanced`. |
| sLTC router | Shadow/Research | Used for research and calibration workflows. |
| Fast-path chat | Working | Realtime stream and regret metrics enabled. |
| Expert contracts | Working | Typed code/research/plan expert payloads with partial failover. |
| Memory v2 | Working | Deduplication, TTL, ranked retrieval, and privacy-safe defaults. |
| Governance | Working | Policy, approvals, audit, fail-closed handling. |
| Provider governance | Experimental/gated | Fail-closed registry and policy layer for model providers. OpenAI-compatible support is a gated adapter path, not broad cloud enablement. |
| Team Runtime | Pilot-hardened | Restricted/controlled profiles with bounded concurrency and replay verification. |
| Enterprise profile | Constrained readiness | Requires signed evidence and deployment drills for broader GA claims. |
| Operator Panel | Beta | Tauri desktop surface for operator workflows. |
| External Provider Governance | Preview | OpenAI Responses and Anthropic Messages are governed behind offline conformance, dry-run invocation, hash-only evidence, server-tool denial, and proposal-only custom tools. This is not unrestricted external provider execution. |
| Vision-first computer-use | Gated foundation | Strict policy, replay, qualification gates, deterministic mocks, CLI/Operator Panel summary; no default live OS automation. |

Computer-use operator control surfaces:

```bash
uv run python -m imperaos computer-use doctor --platform all --json
uv run python -m imperaos computer-use summary --root-dir .imperaos/team/jobs --limit 20 --json
uv run python -m imperaos operator capabilities --json
```

Operator capabilities advertise `computerUseSummaryJson=true` when the summary
bridge is available. In the Agent Control Plane product boundary, computer-use
appears under **Qualified Execution Surfaces** and live start remains disabled
until the vision runtime reports a fail-closed qualified capability.

Control Plane quick commands:

```bash
uv run imperaos control-plane doctor --profile enterprise --json
uv run imperaos control-plane agent register --spec examples/control_plane/agent_governed_ops.yaml --profile enterprise --json
uv run imperaos control-plane policy simulate --agent-id governed-ops --profile enterprise --json
uv run imperaos control-plane run submit --agent-id governed-ops --once "Inspect queue and draft remediation" --profile enterprise --json
uv run imperaos control-plane claims verify --profile enterprise --json
uv run imperaos provider invoke --provider openai_responses --profile enterprise --mode dry-run --once "Inspect service alerts and draft read-only triage summary" --json
```

Provider governance quick commands:

```bash
uv run python -m imperaos provider registry list --profile enterprise --json
uv run python -m imperaos provider policy simulate --profile enterprise --provider-id openai-public --data-class confidential --json
uv run python scripts/run_provider_governance_gate.py --profile enterprise --json
```

Remote/cloud providers remain disabled by default. Provider configs store
environment variable names for secrets, never key values.

---

## Quickstart

### Requirements

- Python `3.11`
- [`uv`](https://github.com/astral-sh/uv)
- Node.js + Corepack + pnpm for the operator panel
- Rust toolchain for Tauri builds
- Ollama or another configured local model provider when using local LLM execution

### First 5 minutes

```bash
make bootstrap
make install
uv run ruff check .
uv run pytest -q
uv run imperaos doctor --profile balanced
```

Product-complete local closure:

```bash
uv run imperaos setup first-run --profile enterprise --mode local-enterprise --json
uv run python scripts/run_product_complete_closure_gate.py --profile enterprise --json
```

See [Product-Complete Closure](docs/PRODUCT_COMPLETE_CLOSURE.md),
[First-Run Setup](docs/FIRST_RUN_SETUP.md), and
[AI Assistant Real Runtime Guide](docs/AI_ASSISTANT_REAL_RUNTIME_GUIDE.md).

### Windows developer quickstart

```powershell
winget install --id=astral-sh.uv -e
uv sync --python 3.11 --extra dev
uv run python -m imperaos --version
uv run python -m imperaos doctor --profile balanced --json
uv run python -m imperaos operator capabilities --json
```

Optional Windows bootstrap:

```powershell
pwsh scripts/bootstrap_windows.ps1
```

> Windows support currently covers the core CLI, operator panel, bundled runtime, and validation workflows. Windows live computer-use remains disabled unless a signed Windows qualification report explicitly enables that surface.

---

## Profiles

| Profile | Router | Shadow Router | Memory | Fallback | Telemetry | Intended use |
|---|---|---|---|---|---|---|
| `lite` | rule | off | off | off | minimal | Small/local low-overhead runs. |
| `balanced` | rule | sLTC | on | on | short | Default daily profile. |
| `research` | sLTC | rule | on | on | debug-friendly | Research and calibration. |
| `restricted` | rule | sLTC | on | on | short | Controlled pilot workflows. |
| `enterprise` | rule | sLTC | on | on | signed + file metrics | Self-hosted secure-default deployment. |

Config precedence:

```text
defaults < profile < environment variables < CLI flags
```

Resolve effective config:

```bash
uv run imperaos config resolve --profile balanced --json
uv run imperaos config resolve --profile balanced --provider ollama --fallback-provider transformers
uv run imperaos config resolve --profile balanced --provider auto --model qwen3.5:4b --hf-model-id Qwen/Qwen3.5-4B-Instruct
```

---

## CLI Usage

### Chat

```bash
uv run imperaos chat --profile balanced --once "selam" --stream --fast-path
uv run imperaos chat --profile balanced --once "kodu düzelt" --no-fast-path
uv run imperaos chat --profile balanced --once "plan çıkar" --model qwen3.5:4b
```

Structured output for UI/thin-shell integrations:

```bash
uv run imperaos chat --profile balanced --once "selam" --json
uv run imperaos chat --profile balanced --once "selam" --json-stream --stream
uv run imperaos chat --profile balanced --once "selam" --stdio-json --stream
```

### Provider recipes

Default profile:

```bash
uv run imperaos chat --profile balanced --once "selam"
```

Ollama model:

```bash
ollama pull qwen3.5:4b
uv run imperaos doctor --profile balanced --provider ollama --model qwen3.5:4b
uv run imperaos chat --profile balanced --provider ollama --model qwen3.5:4b --once "uzun plan çıkar"
```

Transformers custom model:

```bash
uv run imperaos doctor --profile balanced --provider transformers --hf-model-id Qwen/Qwen3.5-4B-Instruct
uv run imperaos chat --profile balanced --provider transformers --hf-model-id Qwen/Qwen3.5-4B-Instruct --once "özetle"
```

Auto provider chain:

```bash
uv run imperaos doctor --profile balanced --provider auto --model qwen3.5:4b --hf-model-id Qwen/Qwen3.5-4B-Instruct
uv run imperaos chat --profile balanced --provider auto --model qwen3.5:4b --hf-model-id Qwen/Qwen3.5-4B-Instruct --once "adım adım anlat"
```

### Native provider previews

OpenAI Responses and Anthropic Messages native adapters are present as disabled,
canary-only preview surfaces. They are used for offline conformance, Operator
Panel trust metadata, and future graduation review; they do not enable production
cloud routing by default.

```bash
uv run python scripts/run_provider_native_adapter_gate.py --profile enterprise --json
uv run python -m imperaos provider native conformance run --profile enterprise --provider-kind all --offline --json
```

Show model override source:

```bash
IMPERAOS_MODEL_NAME=qwen3.5:4b uv run imperaos config resolve --profile balanced --json
```

---

## Governance and Approvals

ImperaOS treats mutating or risky execution as a governed operation. Approval-gated flows must pass through the lifecycle:

```text
pending -> approved -> executed -> consumed
```

Common commands:

```bash
uv run imperaos approval pending --json
uv run imperaos approval show --id <approval_id> --json
uv run imperaos approval decide --id <approval_id> --approve --actor ops-user
uv run imperaos approval execute --id <approval_id> --actor ops-user
uv run imperaos operator capabilities --json
```

Important invariants:

- `approved` alone is not an execution permit.
- Stale approval snapshots are rejected.
- Resume and pilot gates only consume approvals that are both `executed` and not yet `consumed`.
- Terminal, payment, password, wallet, legal-consent, security-setting, and destructive surfaces are denied or stopped unless a qualified policy explicitly allows a supervised path.

---

## Team Runtime

Team Runtime adds governed multi-agent execution with DAG-style scheduling, handoff, scoped memory, checkpointing, and audit/replay support.

```bash
uv run imperaos team init --output team.yaml
uv run imperaos team init --output team-regulated.yaml --template regulated
uv run imperaos team validate --spec team.yaml --json
uv run imperaos team run --spec team.yaml --once "Build a compliance-aware rollout plan" --json
uv run imperaos team resume --spec team.yaml --job-id <blocked_job_id> --root-dir .imperaos/team/jobs --json
uv run imperaos team status --job-id <id> --root-dir .imperaos/team/jobs --json
uv run imperaos team list --root-dir .imperaos/team/jobs --json
uv run imperaos team logs --job-id <id> --root-dir .imperaos/team/jobs --json-stream
uv run imperaos team replay --job-id <id> --root-dir .imperaos/team/jobs --verify --json
uv run imperaos team artifacts --job-id <id> --root-dir .imperaos/team/jobs --export ./team-artifacts
```

Restricted pilot gates:

```bash
uv run imperaos team pilot-check --spec examples/team/restricted_pilot.yaml --profile restricted --mode deterministic --report artifacts/team_pilot_report.json --json
uv run imperaos team pilot-check --spec examples/team/restricted_pilot_live.yaml --profile restricted --mode live-provider --provider auto --report artifacts/team_pilot_live_report.json --json
```

Team Runtime is currently best described as:

- pilot-ready under controlled/restricted profiles,
- bounded-concurrency capable with safety degradation,
- governable and auditable by design.

It should not yet be described as unrestricted enterprise-wide orchestration.

---

## Vision-First Computer Use

ImperaOS includes a vision-first computer-use foundation for desktop/web/file workflows. The design goal is a universal runtime that can observe the active screen, interpret UI state, decide the next safe action, execute controlled input, verify progress, and record replayable audit evidence.

Current runtime loop:

```text
observe -> interpret -> decide -> classify_risk -> approve_if_needed -> execute -> verify -> checkpoint
```

### Current computer-use status

| Platform | Status | Live execution | Reason code |
|---|---:|---:|---|
| macOS | Not qualified | `false` | `MACOS_COMPUTER_USE_NOT_QUALIFIED` |
| Windows | Not qualified | `false` | `WINDOWS_COMPUTER_USE_NOT_QUALIFIED` |
| Linux | Not qualified | `false` | `LINUX_COMPUTER_USE_NOT_QUALIFIED` |

### Safety defaults

```toml
[computer_use]
vision_enabled = false
vision_provider = "none"
raw_screenshot_persistence = false
raw_screenshot_max_count = 0
terminal_policy = "deny"
macos_live_enabled = false
windows_live_enabled = false
linux_live_enabled = false
```

### Computer-use commands

Doctor:

```bash
uv run imperaos computer-use doctor --json
uv run python -m imperaos computer-use doctor --json
```

Qualification fixture/schema verification:

```bash
uv run python -m imperaos computer-use qualification verify \
  --schema contracts/computer_use/platform_qualification.schema.json \
  --input contracts/computer_use/fixtures/windows_platform_qualification_pass_fixture.json \
  --json
```

Platform matrix evaluation:

```bash
uv run python scripts/evaluate_computer_use_platform_matrix.py \
  --profile balanced \
  --output artifacts/computer_use_platform_matrix.json \
  --markdown artifacts/COMPUTER_USE_PLATFORM_MATRIX.md
```

### Computer-use safety boundaries

- Screen text is treated as **untrusted observed content**, not as an instruction.
- Raw screenshots are not persisted by default.
- Sensitive surfaces stop or deny before execution.
- Risky actions require fresh matching approval snapshots.
- Terminal control is denied by default.
- Replay verifies trace integrity, not business correctness.
- Deterministic mock qualification is useful for regression testing, but it is not proof of real-world desktop reliability.

### Platform qualification requirement

A platform may only claim live computer-use support after a platform-specific qualification report proves:

- required permissions are granted manually,
- capture and input backends behave as expected,
- sensitive/risky surfaces fail closed,
- approval freshness is enforced,
- replay integrity passes,
- raw screenshot persistence remains disabled unless explicitly configured,
- destructive or irreversible actions do not execute without a valid approval path,
- signed or otherwise trusted evidence is available for the target release envelope.

---

## Operator Panel

The Operator Panel is a Tauri-based beta desktop UI located under:

```text
apps/operator-panel
```

Common commands:

```bash
make ui-install
make ui-dev
make ui-build
make ui-tauri-build
make ui-gate
```

Direct pnpm usage:

```bash
corepack pnpm --dir apps/operator-panel qa:frontend
corepack pnpm --dir apps/operator-panel qa:frontend:static
corepack pnpm --dir apps/operator-panel test:e2e
```

`qa:frontend` is the full merge-oriented UI gate: control audit, unit/component
tests, lint, build, Playwright preview E2E, accessibility smoke, responsive
smoke, and final QA summary generation. Reports are written under
`artifacts/operator-panel-ui/`.

Tauri checks:

```bash
cargo test --manifest-path apps/operator-panel/src-tauri/Cargo.toml
cargo fmt --manifest-path apps/operator-panel/src-tauri/Cargo.toml --check
```

Packaging and release scripts live under:

```text
apps/operator-panel/scripts/
```

---

## Benchmarks and Research

Smoke, team, ablation, and energy benchmarks:

```bash
uv run imperaos benchmark smoke --mode all --profile balanced
uv run imperaos benchmark team --profile balanced --suite smoke --spec team.yaml
uv run imperaos benchmark team --profile restricted --suite smoke --spec team.yaml --deterministic-mock
uv run imperaos benchmark ablation --mode all --profile balanced --suite smoke
uv run imperaos benchmark ablation --mode all --profile balanced --suite quality
uv run imperaos benchmark energy --profile balanced --energy-mode measured
```

Router research workflows:

```bash
uv run imperaos research train-router \
  --dataset .imperaos/research/router_dataset.jsonl \
  --output-dir research/sltc_experiments/artifacts \
  --seed 42

uv run imperaos research eval-router \
  --dataset .imperaos/research/router_dataset.jsonl \
  --model research/sltc_experiments/artifacts/router_model.json \
  --output-dir research/sltc_experiments/artifacts

uv run imperaos research calibrate-router \
  --dataset .imperaos/research/router_dataset.jsonl \
  --output-dir research/sltc_experiments/artifacts \
  --seed 42
```

Generated research artifacts include:

```text
research/sltc_experiments/artifacts/router_calibration_candidates.json
research/sltc_experiments/artifacts/router_calibration_report.json
research/sltc_experiments/artifacts/router_calibration_report.md
```

---

## Enterprise Profile

The `enterprise` profile is the secure-default self-hosted deployment path. It adds:

- verified identity assertions,
- RBAC checks for mutating operations,
- asymmetric signing for audit and operational artifacts,
- security baseline preflight and startup abort rules,
- backup and restore verification,
- migration planning,
- support bundle export,
- file-based metrics snapshots,
- GA readiness reporting.

Prepare a local enterprise fixture:

```bash
uv run python scripts/prepare_enterprise_fixture.py --root .
```

Validation commands:

```bash
uv run imperaos auth whoami --profile enterprise --json
uv run imperaos auth check --profile enterprise --permission runtime.run --json
uv run imperaos security baseline --profile enterprise --json
uv run imperaos metrics snapshot --profile enterprise --json
uv run imperaos qualification run --profile enterprise --mode mixed --soak-hours 6 --output-root artifacts/qualification --json
uv run imperaos ga readiness --profile enterprise --report artifacts/ga_readiness_report.json --json
```

`ga readiness` evaluates signed qualification evidence from `artifacts/qualification_report.json`. Without the required workload set and soak threshold, the result should remain conditional.

---

## Artifacts

Machine-readable outputs are written under `artifacts/`, including:

```text
status.json
test_summary.json
benchmark_summary.json
router_shadow_summary.json
research_summary.json
governance_summary.json
team_summary.json
security_posture.json
metrics_snapshot.json
ga_readiness_report.json
computer_use_platform_matrix.json
COMPUTER_USE_PLATFORM_MATRIX.md
```

Computer-use contracts and fixtures live under:

```text
contracts/computer_use/
contracts/operator_panel/schemas/
```

---

## Privacy and Security Defaults

Default posture:

- `privacy_mode=true`
- web access off by default
- persistent traces disabled unless debug is enabled and privacy is explicitly off
- raw screenshots not persisted by default
- terminal control denied by default
- risky actions approval-gated
- sensitive surfaces fail closed
- enterprise artifacts require asymmetric signing

`IMPERAOS_AUDIT_SIGNING_KEY` is compatibility-only and is not acceptable for enterprise artifact signing.

---

## Development and Validation

Recommended local validation before PR/merge:

```bash
uv run ruff check .
uv run python -m pytest -q
uv run python -m compileall imperaos
uv run python scripts/generate_operator_contract_schemas.py
corepack pnpm --dir apps/operator-panel test
corepack pnpm --dir apps/operator-panel lint
corepack pnpm --dir apps/operator-panel build
cargo test --manifest-path apps/operator-panel/src-tauri/Cargo.toml
cargo fmt --manifest-path apps/operator-panel/src-tauri/Cargo.toml --check
git diff --check
```

Computer-use-specific validation:

```bash
uv run python -m imperaos computer-use doctor --json
uv run python -m imperaos operator capabilities --json
uv run python scripts/evaluate_computer_use_platform_matrix.py \
  --profile balanced \
  --output artifacts/computer_use_platform_matrix.json \
  --markdown artifacts/COMPUTER_USE_PLATFORM_MATRIX.md
```

---

## Release and Qualification Notes

Windows public/enterprise release remains blocked until the release gate proves:

- Authenticode signing,
- timestamp verification,
- clean VM installer smoke evidence,
- installed runtime/capabilities/doctor evidence,
- runtime manifest and bundle hash evidence,
- `windows-public-release-gate.json` pass status,
- no blocking reasons.

Computer-use live automation remains blocked per platform until platform qualification passes and signed/trusted evidence exists.

---

## Known Limits

- `transformers` fallback is for continuity, not quality parity.
- Measured energy depends on platform permissions such as macOS `powermetrics`.
- sLTC gains vary by workload distribution.
- Operator Panel is beta and release artifacts may depend on signing/notary credentials.
- Internal unsigned Operator Panel desktop binaries are QA/evaluation artifacts only; they are not public desktop installers or release candidates.
- Model assets are not auto-installed; `ollama pull` remains operator-driven.
- Team runs intentionally fail closed when governance requires approval in a blocking dependency chain.
- `team replay --verify` checks ordering, causal continuity, handoff consistency, and trace integrity; it does not guarantee external business correctness.
- Enterprise deployment is scoped to self-hosted single-tenant environments; multi-tenant control plane work is deferred.
- Vision-first computer-use is not generally available live automation; it is qualification-gated and disabled by default.

---

## Computer-Use Vision Pilot

ImperaOS includes a supervised macOS vision-first computer-use pilot behind fail-closed flags. It supports deterministic mock qualification, redacted replay/audit artifacts, strict local vision-provider parsing, and approval-gated risky actions. Raw screenshots are not persisted by default.

Windows live computer-use is not qualified and remains disabled with `WINDOWS_COMPUTER_USE_NOT_QUALIFIED`.

```bash
uv run imperaos computer-use qualify --runtime vision-first --suite smoke --mode deterministic --json
uv run imperaos computer-use vision doctor --profile balanced --json
```

## Documentation Index

Key documents:

```text
docs/ARCHITECTURE.md
docs/CONFIGURATION.md
docs/OPERATIONS_RUNBOOK.md
docs/OPERATOR_CONTRACT_BEHAVIOR.md
docs/PRIVACY_MODEL.md
docs/PRODUCT_BOUNDARY_NOTE.md
docs/HAT_B_DESKTOP_RELEASE_HANDOFF_2026-05-10.md
docs/RELEASE_CHECKLIST.md
docs/RELEASE_GATE_v0.5.md
docs/RELEASE_NOTES_HAT_A_2026-05-10.md
docs/RELEASE_NOTES_HAT_A_CLOSURE_2026-05-13.md
docs/SECURITY_MODEL.md
docs/RFC_COMPUTER_USE_001.md
docs/RFC_COMPUTER_USE_002_full_runtime_foundation.md
docs/RFC_COMPUTER_USE_003_vision_first_runtime.md
docs/RFC_COMPUTER_USE_004_SUPERVISED_MACOS_VISION_PILOT.md
docs/RFC_COMPUTER_USE_005_INTEGRATION_GATE.md
docs/RFC_COMPUTER_USE_006_CROSS_PLATFORM_QUALIFICATION_GATES.md
docs/RFC_COMPUTER_USE_007_MACOS_LIVE_QUALIFICATION.md
docs/RFC_COMPUTER_USE_008_MACOS_LIVE_FIXTURE_QUALIFICATION.md
docs/RFC_COMPUTER_USE_009_MACOS_LIVE_READINESS_AND_SAFE_RERUN.md
docs/RFC_COMPUTER_USE_010_MACOS_ONE_RUN_LIVE_FIXTURE_QUALIFICATION.md
docs/RFC_COMPUTER_USE_011_MACOS_PROVIDER_PERMISSION_AND_ONE_RUN_QUALIFICATION.md
docs/RFC_COMPUTER_USE_012_REAL_VISION_ACTION_PLANNER.md
docs/RFC_COMPUTER_USE_013_SEMANTIC_STEP_VERIFICATION.md
docs/RFC_COMPUTER_USE_014_APPROVAL_RESUME_SNAPSHOT_BINDING.md
docs/RFC_COMPUTER_USE_015_MULTI_STEP_LOOP_HARDENING.md
docs/RFC_COMPUTER_USE_016_VISION_RUNTIME_SAFETY_SUMMARY.md
docs/RFC_COMPUTER_USE_017_MACOS_SUPERVISED_VISION_QUALIFICATION_V2.md
docs/RFC_COMPUTER_USE_WINDOWS_QUALIFICATION.md
docs/WINDOWS_RELEASE_HARDENING_REPORT.md
docs/WINDOWS_INSTALLER_SMOKE.md
docs/WINDOWS_SIGNED_RC_GATE_REPORT.md
docs/WINDOWS_PUBLIC_RELEASE_EVIDENCE_CLOSURE_REPORT.md
docs/WINDOWS_RELEASE_FINALIZATION_REPORT.md
SECURITY_BASELINE.md
KEY_MANAGEMENT.md
UPGRADE_AND_RECOVERY.md
OBSERVABILITY_AND_SLO.md
QUALIFICATION_MATRIX.md
INSTALL.md
DEPLOYMENT_GUIDE.md
SUPPORT_BUNDLE.md
```

---

## Suggested Project Description

> ImperaOS is a private, local-first, security-governed agentic runtime for enterprise-controlled environments. It combines a production-grade core assistant runtime, pilot-hardened multi-agent Team Runtime, beta operator panel, and qualification-gated vision-first computer-use foundation with strict approval, replay, audit, and fail-closed safety controls.
