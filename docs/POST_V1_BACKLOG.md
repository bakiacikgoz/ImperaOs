# Post-v1 Backlog

## Design Partner Conditional Freeze Follow-Ups

- Run the real target-environment evidence session for the first design
  partner.
- Collect independent operator attestation for the target-environment run.
- Rerun `make design-partner-rc-gate` after target evidence and attestation are
  available, then promote conditional to ready only if the strict gate passes.
- Publish the promoted RC evidence bundle without treating rehearsal-only
  artifacts as target-environment proof.
- Keep public desktop installer, unrestricted live computer-use, and
  approval-free irreversible mutation claims blocked until their independent
  release evidence exists.

## Release Blockers For Hat B

Detailed operator handoff:
`docs/HAT_B_DESKTOP_RELEASE_HANDOFF_2026-05-10.md`.

Tracking issue: https://github.com/bakiacikgoz/ImperaOS/issues/4.

- GitHub Actions account billing/spending limit was fixed on 2026-05-12:
  macOS run `25755093728` and Windows run `25755177376` both started runners
  and produced credential preflight artifacts.
- Provision macOS signing and notarization credentials:
  `MACOS_SIGNING_IDENTITY`, `MACOS_SIGNING_CERT_P12_B64`,
  `MACOS_SIGNING_CERT_PASSWORD`, and either Apple notary API key secrets or
  Apple ID notarization secrets.
- Run `operator-panel-release-macos.yml` and capture codesign, notarytool,
  stapler, and clean-machine Gatekeeper evidence.
- Provision Windows signing credentials. `WINDOWS_TIMESTAMP_URL` is already
  configured on the `release-windows` environment.
- Run Windows signed RC, clean smoke, and promote workflows.
- Publish `windows-public-release-gate.json` with `status=pass`,
  `public_release_allowed=true`, and `blocking_reasons=[]`.
- If signing credentials remain unavailable, use
  `operator-panel-internal-unsigned-build.yml` only for internal QA/evaluation
  no-bundle debug binary artifacts. These artifacts are explicitly no-ship and
  do not satisfy Hat B release gates.
- 2026-05-13 internal unsigned fallback run `25814422248` passed for macOS
  `arm64`, macOS `x86_64`, and Windows `x64`. Keep treating those artifacts as
  no-ship QA/evaluation evidence only.

## Qualification Follow-Ups

- Run 24h release-candidate soak and publish signed evidence. **Completed
  2026-05-12:** run `rc24h-20260511T153314Z` completed successfully with
  signed qualification verification PASS and GA readiness green/go. Reporting
  alignment was fixed and aligned signed evidence was published with
  `24h_soak_flow=pass`.
  Use `scripts/run_qualification_soak_supervised.sh --detach --hours 24`
  so the soak is not tied to an interactive terminal session. Refresh the local
  enterprise identity assertion for more than 24 hours first if it has expired.
  2026-05-11: started as LaunchAgent from
  `/private/tmp/imperaos_soak_rc24h-20260511T153314Z` with run id
  `rc24h-20260511T153314Z`; expected completion is approximately
  `2026-05-12T15:34Z`.
- Run 72h final pre-GA soak if required by the release policy. **Completed
  2026-05-16:** run `final72h-20260513T194220Z` completed successfully with
  `status=completed_success`, `exit_code=0`, empty stderr, signed
  qualification verification PASS, GA readiness green/go, and
  `pending_evidence=[]`. Evidence summary:
  `artifacts/readiness/2026-05-16/final_72h_soak/summary.json`. The earlier run
  `final72h-20260513T192000Z` was intentionally stopped at user request and
  recorded `status=interrupted`, `exit_code=130`.
- Publish managed KMS adapter live drill evidence. **Completed 2026-05-13:**
  `artifacts/readiness/2026-05-13/managed_kms_adapter_drill/` reports
  `status=pass`, signed report verification PASS, sign/verify PASS, rotation
  dry-run PASS, revoked key reject PASS, restore-time historical artifact
  verification PASS, and no secret material persisted in evidence.
- Hardware HSM/PKCS#11 breadth remains deferred.
- Complete operator proxy validation dry-run. **Completed 2026-05-13:**
  `artifacts/readiness/2026-05-13/operator_validation_drill/` reports
  `status=pass`, `command_status=pass`, `evidence_status=pass`, and
  `validation_scope=operator_proxy_dry_run`.
- Prepare independent non-developer operator attestation workflow. **Completed
  2026-05-13:** `docs/NON_DEVELOPER_OPERATOR_ATTESTATION.md`,
  `docs/templates/non_developer_operator_attestation.template.json`, and
  `scripts/run_operator_validation_drill.py --operator-attestation` define and
  validate the handoff path.
- Collect independent non-developer operator attestation. This is not yet
  provided and cannot be substituted by automated proxy validation.

## Computer-Use Follow-Ups

- 2026-05-12 deterministic boundary evidence refreshed under
  `artifacts/readiness/2026-05-12/computer_use_faz6/`: qualification PASS,
  platform matrix PASS, raw screenshot persisted count `0`, terminal default
  `deny`, and public live claim `false` for macOS/Windows/Linux.
- 2026-05-13 Hat B Windows computer-use disabled evidence verified in the
  closure pack: `computer_use_platform_matrix.json` and
  `operator_capabilities.json` both keep Windows fail-closed with
  `WINDOWS_COMPUTER_USE_NOT_QUALIFIED`.
- Publish macOS supervised live qualification only after Screen Recording,
  Accessibility, local vision provider readiness, runtime summary, replay
  verification, and fresh qualification evidence all pass.
- Keep Windows and Linux live computer-use disabled until platform-specific
  qualification evidence exists.
- Do not market deterministic mock qualification as real-world desktop
  reliability evidence.

## Deferred Product Scope

- Multi-tenant control plane.
- Richer admin UI.
- Broader cloud-native integrations.
- Full PKCS#11/HSM breadth.
# Governed Pilot Workflow Follow-Ups

- Add signed target-environment attestation once a design partner has an approved evidence window.
- Promote target rehearsal from blocked validation to a signed, opt-in workflow with operator attestation.
- Add historical governed pilot workflow trend cards to the Operator Panel.
