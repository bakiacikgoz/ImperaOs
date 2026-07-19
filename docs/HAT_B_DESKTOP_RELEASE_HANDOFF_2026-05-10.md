# Hat B Desktop Release Handoff - 2026-05-10

## Current Status

Hat B is blocked by external credentials and clean-machine evidence. No public
desktop installer release has been made, and no desktop release claim should be
published from the current evidence.

Tracking issue: https://github.com/bakiacikgoz/ImperaOS/issues/4

Local evidence already captured:

- Operator Panel UI gate: PASS.
- Operator Panel Rust/Tauri tests: PASS.
- Local unsigned macOS `.app` and `.dmg` build: PASS.
- macOS release workflow now preflights signing/notarization credentials before
  checkout/build and uploads `operator-panel-macos-credential-preflight-<arch>`
  evidence when blocked.
- GitHub Actions run `25638420468` verified the macOS preflight behavior:
  both `arm64` and `x86_64` lanes stopped at credential preflight with
  `status=blocked_external_credentials`, uploaded preflight evidence, skipped
  checkout/build/sign/notarize steps, and wrote no secret material.
- GitHub Actions run `25751802651` rechecked the macOS release workflow on
  2026-05-12. Both macOS jobs failed before any workflow step started because
  GitHub Actions could not allocate runners: "recent account payments have
  failed or your spending limit needs to be increased." No credential preflight
  artifacts were produced in that run.
- GitHub Actions run `25755093728` verified on 2026-05-12 that the billing /
  spending-limit blocker was cleared. Both macOS lanes started runners, failed
  at `Validate signing and notarization credentials`, uploaded credential
  preflight evidence, and skipped checkout/build/sign/notarize steps.
  `arm64` and `x86_64` both report `status=blocked_external_credentials`,
  missing `MACOS_SIGNING_IDENTITY`, `MACOS_SIGNING_CERT_P12_B64`,
  `MACOS_SIGNING_CERT_PASSWORD`, and missing notarization credentials.
- GitHub Actions run `25638465677` verified Windows CI: `windows-2022`
  required lane and `windows-2025` canary lane both completed with
  `conclusion=success`. Evidence was downloaded under
  `artifacts/readiness/2026-05-10/github_windows_ci_25638465677/`.
- GitHub Actions run `25638818041` verified the Windows signed-RC workflow in
  missing-secret mode. The workflow completed and uploaded unsigned CI smoke
  evidence, but did not upload signed release-candidate artifacts.
  `windows-release-status.json` reports `status=blocked_external_credentials`,
  `signed=false`, `timestamped=false`, `signed_rc_allowed=false`, and
  `secret_material_written=false`. The public gate reports
  `public_release_allowed=false`.
- Windows release gate ownership verification PASS:
  `tests/test_windows_release_gate.py` and
  `tests/test_windows_release_workflows_static.py` confirm
  `windows-release-status.json` stays scoped to signed-RC status and
  `windows-public-release-gate.json` remains the public release authority.
- GitHub Actions run `25752181105` rechecked the Windows signed-RC workflow on
  2026-05-12. The `windows-2022` job failed before any workflow step started
  because GitHub Actions could not allocate a runner: "recent account payments
  have failed or your spending limit needs to be increased." No credential
  preflight or signed-RC artifacts were produced in that run.
- GitHub Actions run `25755177376` verified on 2026-05-12 that the billing /
  spending-limit blocker was cleared for Windows too. The `windows-2022` job
  started, failed at `Validate Windows signing credentials`, uploaded
  `operator-panel-windows-credential-preflight`, and skipped checkout/build/
  signing/public-gate steps. The preflight artifact reports
  `status=blocked_external_credentials`, missing
  `WINDOWS_SIGNING_CERT_PFX_B64` and `WINDOWS_SIGNING_CERT_PASSWORD`,
  `timestamp_url_configured=true`, `signed=false`, `timestamped=false`,
  `signed_rc_allowed=false`, and `secret_material_written=false`.
- If signing/notarization credentials cannot be provided, the only supported
  alternate path is internal unsigned desktop build evidence. Workflow
  `operator-panel-internal-unsigned-build.yml` is manual-only, uses no signing
  secrets or release environments, and uploads no-bundle debug binary artifacts
  explicitly labeled `internal_unsigned`. These artifacts are for local
  QA/evaluation only and are not public release eligible.
- 2026-05-13 fallback validation: GitHub Actions run `25814422248` passed for
  macOS `arm64`, macOS `x86_64`, and Windows `x64`. Downloaded local evidence:
  `artifacts/readiness/2026-05-13/operator_panel_internal_unsigned_25814422248/`.
  Manifests report `status=internal_unsigned`, `release_eligible=false`,
  `public_release_allowed=false`, and `packaging=no_bundle_debug_binary`.
- Windows release gate evaluator tests: PASS.
- Windows public release gate fail-closed evidence: `status=blocked`,
  `public_release_allowed=false`.
- macOS notarization fail-closed evidence:
  `status=blocked_external_credentials`.

GitHub inventory observed on 2026-05-10:

- Repository secrets: none listed.
- Repository variables: none listed.
- Existing environments: `release-macos`, `release-windows`,
  `clean-smoke-windows`, and `promote-windows`.
- Environment protection reviewer/wait-timer rules were attempted but rejected
  by the repository billing plan (`HTTP 422`). Current environments therefore
  have empty `protection_rules`.
- `release-windows` environment variable configured:
  `WINDOWS_TIMESTAMP_URL=http://timestamp.digicert.com`.
- 2026-05-12 recheck: repository secrets and variables remain empty,
  `release-macos` environment secrets and variables remain empty, and
  `release-windows` still only has
  `WINDOWS_TIMESTAMP_URL=http://timestamp.digicert.com`.
- macOS and Windows signing secrets remain missing.
- 2026-05-12 billing/spending limit recheck passed: macOS and Windows release
  runners now start and produce credential preflight evidence.
- macOS and Windows signing/notarization credentials must be provisioned before
  signing, notarization, clean-machine smoke, or promote evidence can pass.

## macOS Blocker

Required GitHub environment: `release-macos`.

Required signing secrets:

- `MACOS_SIGNING_IDENTITY`
- `MACOS_SIGNING_CERT_P12_B64`
- `MACOS_SIGNING_CERT_PASSWORD`

Required notarization secrets, using one mode only.

API key mode:

- `APPLE_NOTARY_KEY_ID`
- `APPLE_NOTARY_ISSUER_ID`
- `APPLE_NOTARY_KEY_P8_B64`

Apple ID mode:

- `APPLE_ID`
- `APPLE_TEAM_ID`
- `APPLE_APP_PASSWORD`

Workflow to run after secrets are provisioned:

```bash
gh workflow run operator-panel-release-macos.yml \
  --repo bakiacikgoz/ImperaOS
```

If secrets are still missing or partial, the workflow should fail before
checkout/build with `status=blocked_external_credentials`; this is expected
blocked evidence, not a desktop release failure.

macOS PASS criteria:

- `codesign --verify --deep --strict` PASS.
- `xcrun notarytool submit --wait` PASS.
- Stapler PASS.
- Clean-machine Gatekeeper open test PASS.
- Evidence JSON records all of the above without secret material.

## Windows Blocker

Required GitHub environment: `release-windows`.

Required secrets:

- `WINDOWS_SIGNING_CERT_PFX_B64`
- `WINDOWS_SIGNING_CERT_PASSWORD`

Configured variable:

- `WINDOWS_TIMESTAMP_URL`

2026-05-11 recheck:

- Repository-level secrets: absent.
- `release-windows` environment secrets: absent.
- `release-windows` environment variable: `WINDOWS_TIMESTAMP_URL` present.
- Clean smoke remains blocked until a signed RC artifact exists.
- The Windows release workflow now preflights signing credentials before
  checkout/build and uploads `operator-panel-windows-credential-preflight`
  evidence when credentials are missing.
- GitHub Actions run `25654446077` verified that behavior. The preflight
  artifact reports `status=blocked_external_credentials`, missing
  `WINDOWS_SIGNING_CERT_PFX_B64` and `WINDOWS_SIGNING_CERT_PASSWORD`,
  `secret_material_written=false`, `signed_rc_allowed=false`, and skipped
  checkout/build/signing/public-gate steps. Artifact
  `operator-panel-windows-credential-preflight` id `6911820950` has digest
  `sha256:6c13170009f6098bfce55203c54294d5824b60b6cc18bf2a1609e5bd431bfb00`.

2026-05-12 recheck:

- `release-windows` environment secrets remain absent.
- `release-windows` environment variable `WINDOWS_TIMESTAMP_URL` remains
  configured.
- GitHub Actions run `25752181105` failed before workflow steps started because
  account billing/spending limit blocked runner allocation. No credential
  preflight artifact was produced.
- GitHub Actions run `25755177376` confirmed runners now start. The workflow
  stops at credential preflight with `status=blocked_external_credentials`
  because `WINDOWS_SIGNING_CERT_PFX_B64` and
  `WINDOWS_SIGNING_CERT_PASSWORD` are missing.
- Provision Windows signing secrets before rerunning Windows signed-RC
  evidence.

Workflow sequence after secrets are provisioned:

```bash
gh workflow run operator-panel-release-windows.yml \
  --repo bakiacikgoz/ImperaOS

gh workflow run operator-panel-windows-clean-smoke.yml \
  --repo bakiacikgoz/ImperaOS \
  -f signed_rc_run_id=<SIGNED_RC_RUN_ID> \
  -f installer_sha256=<SIGNED_RC_INSTALLER_SHA256>

gh workflow run operator-panel-promote-windows.yml \
  --repo bakiacikgoz/ImperaOS \
  -f signed_rc_run_id=<SIGNED_RC_RUN_ID> \
  -f clean_smoke_run_id=<CLEAN_SMOKE_RUN_ID> \
  -f expected_installer_sha256=<SIGNED_RC_INSTALLER_SHA256>
```

Windows PASS criteria:

- Signed RC artifact exists.
- Artifact is timestamped.
- `signtool verify /pa /v` PASS.
- Clean Windows VM install/open/runtime/capabilities/doctor smoke PASS.
- `windows-public-release-gate.json` reports:
  `status=pass`, `public_release_allowed=true`, and
  `blocking_reasons=[]`.
- Windows live computer-use remains disabled with
  `WINDOWS_COMPUTER_USE_NOT_QUALIFIED` unless separate signed qualification
  evidence enables it.

## No-Ship Rule

Do not publish a Hat B desktop release until every macOS or Windows target being
claimed has green signing, notarization/signature, clean-machine smoke, and
public release gate evidence. Hat A may remain published as a source/CLI/
enterprise self-hosted candidate without desktop installer claims.

Unsigned internal binary artifacts from
`operator-panel-internal-unsigned-build.yml` must never be renamed, promoted, or
described as installers or release candidates. They do not close macOS
notarization, Windows signed-RC, clean-machine smoke, or promote gates.
