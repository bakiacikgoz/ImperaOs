# Qualification Matrix

This matrix now applies to the self-hosted Agent Control Plane product boundary:
agent registry, governed run coordination, policy simulation, approval
lifecycle, replay/audit, signed evidence, support bundle and claim guard.

## Purpose

This document defines the evidence required before ImperaOS / ImperaOS can be described as `enterprise deployment-ready under defined constraints`.
It does not claim that evidence already exists.

## Current Evidence Status - 2026-05-16

Hat A source/CLI/enterprise self-hosted readiness has published signed
qualification evidence for a 6h candidate smoke-soak, a 24h
release-candidate soak addendum, and a completed 72h final pre-GA soak:

- `artifacts/qualification_report.json`: `qualification_status=pass`,
  `recommended_status=green`, `go_no_go=go`.
- `artifacts/ga_readiness_report.json`: `overall_status=green`,
  `go_no_go=go`, `pending_evidence=[]`, `blocking_findings=[]`.
- 6h soak evidence: `duration_seconds=21600`, `iterations=73`,
  replay verification PASS, signing verification PASS.
- 24h soak evidence: run `rc24h-20260511T153314Z`,
  `supervisor_status=completed_success`, aligned signed qualification
  verification PASS, GA readiness green/go, and `24h_soak_flow=pass`.
- 72h final pre-GA soak evidence: run `final72h-20260513T194220Z`,
  `supervisor_status=completed_success`, `exit_code=0`, empty stderr,
  observed soak duration `259203` seconds, signed qualification verification
  PASS, GA readiness green/go, `pending_evidence=[]`, and evidence summary
  `artifacts/readiness/2026-05-16/final_72h_soak/summary.json`.
- Computer-use deterministic boundary evidence: PASS with raw screenshot
  persisted count `0`, terminal control default `deny`, sensitive surface
  blocked, and public live claim `false` for macOS, Windows, and Linux.

This supports a Hat A candidate release under the support boundaries below.
It is not a desktop installer release.
The remaining qualification residual risks are:

- Operator proxy validation dry-run is published, and the independent
  non-developer operator attestation template/validator path is documented.
  The actual independent human attestation is still pending.
- Hardware HSM/PKCS#11 breadth remains deferred beyond the managed KMS adapter
  drill.

## Supported Deployment Classes

- `Linux Standard`: primary GA runtime reference
- `macOS Operator`: secondary operator tooling surface
- `Windows Standard`: core runtime, operator panel build/test surface, and
  bundled runtime evidence. Public/enterprise Windows desktop installer release
  remains blocked until Authenticode signed RC, clean VM smoke, and promote gate
  evidence pass.

## Workload Families

- mixed bounded-concurrency workflow
- approval-heavy workflow
- conflict-heavy shared-state workflow
- long-running workflow
- provider transient-failure workflow
- supervised macOS vision-first computer-use deterministic smoke

## Qualification Windows

- `6h` candidate smoke-soak
- `24h` release-candidate soak
- `72h` final pre-GA soak

## Blocking Pass Criteria

- `0` replay or audit integrity failures
- `0` duplicate side effects
- `0` restore verification failures after checkpointed restart drills
- no silent shared-state overwrite
- no unclassified provider/runtime failures
- sqlite integrity passes before and after soak
- artifact growth remains inside retention forecast
- Windows Standard additionally requires green `windows-2022` CI, bundled runtime
  manifest verification, external and bundled bridge handshake proof, clean VM
  install/open/handshake smoke, no shell passthrough, no path traversal or symlink
  escape, no unsupported computer-use overclaim, and signed release gate before
  any public release. Windows live computer-use remains disabled until signed
  qualification evidence exists.

## Computer-Use Vision Pilot

- `deterministic` qualification uses `computer_use_vision_qualification/v1`.
- `live` qualification is macOS-only and opt-in.
- Raw screenshots must remain disabled by default with persisted count `0`.
- Replay verifies integrity and policy invariants, not business correctness.
- Windows desktop release evidence additionally requires schema drift gate PASS,
  recursive resource bundle proof, runtime hash manifest, signed RC release
  status JSON, bundle hash evidence, `docs/WINDOWS_INSTALLER_SMOKE.md` clean VM
  smoke report, installed runtime/capabilities/doctor evidence, and
  `windows-public-release-gate.json` with `status=pass`,
  `public_release_allowed=true`, and no blocking reasons.
- Internal unsigned no-bundle Operator Panel desktop binaries are QA/evaluation
  evidence only. They do not satisfy macOS notarization, Windows signed-RC,
  clean-machine smoke, or promote gates.
- Windows live computer-use automation remains disabled with
  `WINDOWS_COMPUTER_USE_NOT_QUALIFIED` unless a separate signed Windows
  qualification report explicitly enables that surface.

## Phase 4A Platform Status

| Platform | Stage | Live Enabled | Reason |
|---|---:|---:|---|
| macOS | not_qualified until fresh supervised local evidence exists | false by default | `MACOS_COMPUTER_USE_NOT_QUALIFIED` |
| Windows | not_qualified | false | `WINDOWS_COMPUTER_USE_NOT_QUALIFIED` |
| Linux | not_qualified | false | `LINUX_COMPUTER_USE_NOT_QUALIFIED` |

macOS can move to `fixture_qualified` after a fresh matching supervised local
fixture report, but live execution still remains off until explicit config
enablement and current doctor pass. Phase 4C separates
`qualificationPassed=false` from `replayIntegrityVerified=true` for blocked
preflight reports, so no-op evidence can be audit-valid without being
qualification-valid.

Deterministic mock qualification is useful for CI contracts. It is not proof of
real-world desktop reliability.

## Required Report Outputs

At minimum publish:

- supported concurrent team task envelope
- supported approval-heavy rate
- supported artifact retention window
- fallback thresholds where serial execution becomes expected
- provider failure classification summary

## Blocking Test Set Before RC / Final GA Claim

- role boundary negative tests
- key rotation and revocation drills
- backup/restore partial-upgrade drill
- replay and signature tamper drills
- 24h approval-heavy soak
- conflict-heavy bounded-concurrency soak
- provider failure classification soak

## Evidence Artifact

Run qualification through the canonical runner:

```bash
uv run imperaos qualification run \
  --profile enterprise \
  --mode mixed \
  --soak-hours 6 \
  --output-root artifacts/qualification \
  --json
```

This publishes:

- `artifacts/qualification/<run_id>/qualification_report.json`
- `artifacts/qualification/<run_id>/QUALIFICATION_REPORT.md`
- latest pointers at `artifacts/qualification_report.json` and `artifacts/QUALIFICATION_REPORT.md`

The JSON artifact is signed. `ga readiness` must verify that signature, require
the mandatory workload set, enforce the `6h` soak threshold for `green/go`, and
use the published support-boundary table before any enterprise-ready claim.
