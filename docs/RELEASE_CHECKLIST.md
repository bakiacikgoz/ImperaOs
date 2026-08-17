# RELEASE_CHECKLIST

## RC Release Decision

```bash
uv run python scripts/run_rc_release_decision_gate.py --profile enterprise --json
```

Treat `conditional` as expected until real human sign-off files verify. Do not promote public desktop, live computer-use, unsigned artifacts, or raw/secret-persisting evidence from this dossier.

## Current Closure Status - 2026-05-13

- [x] Hat A source/CLI/enterprise self-hosted candidate evidence published.
- [x] 24h release-candidate soak completed with signed aligned evidence.
- [x] Computer-use deterministic boundary evidence refreshed and fail-closed.
- [x] Internal unsigned Operator Panel fallback artifacts produced for
  QA/evaluation only.
- [ ] Hat B macOS public desktop installer release. Blocked by missing
  signing/notarization credentials and clean-machine Gatekeeper evidence.
- [ ] Hat B Windows public desktop installer release. Blocked by missing
  Authenticode signing credentials, signed RC, clean VM smoke, and promote gate
  evidence.
- [x] Managed KMS adapter live drill evidence.
- [ ] Hardware HSM/PKCS#11 breadth.
- [x] Operator proxy validation dry-run evidence.
- [x] Independent operator attestation template and validator path documented.
- [ ] Independent non-developer operator attestation.

## Quality Gates

- [ ] `uv run ruff check .`
- [ ] `uv run pytest -q`
- [ ] `make pilot-gate`
- [ ] `make enterprise-gate`
- [ ] `make qualification-run`
- [ ] `uv run imperaos team validate --spec examples/team/restricted_pilot.yaml --json`
- [ ] `uv run imperaos team pilot-check --spec examples/team/restricted_pilot.yaml --profile restricted --mode deterministic --report artifacts/team_pilot_report.json --json`
- [ ] `artifacts/team_pilot_report.json` shows `checks.bounded_concurrency.status=pass`
- [ ] `uv run imperaos config resolve --profile balanced --json`
- [ ] `uv run imperaos doctor --profile balanced`
- [ ] `uv run imperaos benchmark smoke --mode all --profile balanced`
- [ ] `uv run imperaos benchmark team --profile restricted --suite smoke --spec team.yaml --deterministic-mock`
- [ ] `uv run imperaos benchmark team --profile balanced --suite smoke --spec team.yaml`
- [ ] `uv run imperaos benchmark ablation --mode all --profile balanced --suite quality`
- [ ] `uv run imperaos benchmark energy --profile balanced --energy-mode measured`
- [ ] `uv run pytest -q tests/test_memory_concurrency.py`
- [ ] `uv run pytest -q tests/test_team_checkpoint_concurrency.py`

## Enterprise Gates

- [ ] `uv run python scripts/prepare_enterprise_fixture.py --root .`
- [ ] `uv run imperaos security baseline --profile enterprise --json`
- [ ] `uv run imperaos auth whoami --profile enterprise --json`
- [ ] `uv run imperaos auth check --profile enterprise --permission runtime.run --json`
- [ ] `uv run imperaos metrics snapshot --profile enterprise --json`
- [ ] `uv run imperaos qualification run --profile enterprise --mode mixed --soak-hours 6 --output-root artifacts/qualification --json`
- [ ] `uv run imperaos ga readiness --profile enterprise --report artifacts/ga_readiness_report.json --json`
- [ ] `artifacts/security_posture.json` exists and is signed
- [ ] `artifacts/metrics_snapshot.json` exists and is signed
- [ ] `artifacts/qualification_report.json` exists, is signed, and contains all required workloads
- [ ] `artifacts/QUALIFICATION_REPORT.md` exists
- [ ] `artifacts/ga_readiness_report.json` exists and is signed
- [ ] `artifacts/GA_READINESS_REPORT.md` exists
- [ ] key status reports asymmetric provider and trusted verification keys
- [ ] qualification evidence is published before any `enterprise deployment-ready` claim

## Research Gates

- [ ] `uv run imperaos research train-router --dataset .imperaos/research/router_dataset.jsonl`
- [ ] `uv run imperaos research eval-router --dataset .imperaos/research/router_dataset.jsonl`

## Operator Panel Gates (v0.5)

- [ ] `pnpm install --dir apps/operator-panel`
- [ ] `pnpm --dir apps/operator-panel lint`
- [ ] `pnpm --dir apps/operator-panel test`
- [ ] `pnpm --dir apps/operator-panel build`
- [ ] `cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml`
- [ ] `uv run imperaos operator capabilities --json`
- [ ] `uv run imperaos team list --root-dir .imperaos/team/jobs --json`
- [ ] `uv run imperaos approval show --id <approval_id> --json`

## Windows Operator Panel Gates

- [ ] `windows-2022` CI PASS
- [ ] `uv run python scripts/generate_operator_contract_schemas.py` produces no schema diff
- [ ] `tests/test_operator_schema_generation.py` PASS
- [ ] `uv run ruff check .` PASS on Windows
- [ ] `uv run pytest -q` PASS on Windows
- [ ] `pnpm --dir apps/operator-panel test` PASS on Windows
- [ ] `pnpm --dir apps/operator-panel lint` PASS on Windows
- [ ] `pnpm --dir apps/operator-panel build` PASS on Windows
- [ ] `cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml` PASS on Windows
- [ ] `pwsh apps/operator-panel/scripts/build_bundled_runtime_windows.ps1 -Arch x64` PASS
- [ ] `pwsh apps/operator-panel/scripts/verify_bundled_runtime_windows.ps1 -RuntimeDir apps/operator-panel/src-tauri/resources/imperaos-runtime` PASS
- [ ] `apps/operator-panel/src-tauri/resources/imperaos-runtime/python/Scripts/python.exe -m imperaos --version` PASS
- [ ] `apps/operator-panel/src-tauri/resources/imperaos-runtime/RUNTIME_MANIFEST.txt` exists and includes SHA256 evidence
- [ ] `pnpm --dir apps/operator-panel exec tauri build --debug --no-bundle` PASS
- [ ] Windows CI uploads `artifacts/windows-ci-evidence/**`
- [ ] Windows release workflow writes `windows-release-status.json`
- [ ] Authenticode signing + timestamp + `signtool verify /pa /v` PASS for signed RC artifact, or signed RC remains blocked
- [ ] `windows-release-status.json` reports `signed_rc_allowed=true` only after signing, timestamp, and verify pass
- [ ] `windows-release-status.json` does not grant `public_release_allowed=true`
- [ ] `runtime_manifest.txt` and `nsis_file_hashes.json` are present in signed RC evidence
- [ ] Clean Windows smoke workflow runs signed installer with `-RunInstall -CleanVm -LaunchAppSmoke -RunUninstall` and without `-AllowUnsignedSmoke`
- [ ] Clean Windows VM install/open/runtime/capabilities/doctor smoke PASS before public release claim, following `docs/WINDOWS_INSTALLER_SMOKE.md`
- [ ] Promote workflow runs `uv run python scripts/evaluate_windows_release_gate.py ... --fail-on-blocked`
- [ ] `windows-public-release-gate.json` reports `status=pass`, `public_release_allowed=true`, and `blocking_reasons=[]` before public/enterprise Windows release
- [ ] Unsigned/internal smoke reports `public_release_allowed=false`
- [x] `operator capabilities --json` reports Windows live computer-use disabled with `WINDOWS_COMPUTER_USE_NOT_QUALIFIED`
- [ ] `windows-installer-smoke.json` also reports `computer_use_live_enabled=false` and `computer_use_reason_code=WINDOWS_COMPUTER_USE_NOT_QUALIFIED`
- [ ] Do not ship if `windows-public-release-gate.json` is missing, blocked, failed, has blocking reasons, used unsigned smoke, has `clean_vm_claimed != true`, or has an installer hash mismatch

## macOS Signing + Notarization (v0.5)

- [ ] GitHub Environment `release-macos` exists and required reviewers/policies are configured
- [ ] Signing cert secrets set:
  - `MACOS_SIGNING_IDENTITY`
  - `MACOS_SIGNING_CERT_P12_B64`
  - `MACOS_SIGNING_CERT_PASSWORD`
- [ ] Notarization auth set (choose one, API key preferred):
  - API key: `APPLE_NOTARY_KEY_ID`, `APPLE_NOTARY_ISSUER_ID`, `APPLE_NOTARY_KEY_P8_B64`
  - Apple ID: `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD`
- [ ] `apps/operator-panel/scripts/codesign_notarize_macos.sh <App.app> <artifact.dmg>`
- [ ] `codesign --verify --deep --strict` PASS
- [ ] `xcrun notarytool submit --wait` PASS
- [ ] `xcrun stapler staple` + `xcrun stapler validate` PASS
- [ ] Clean-machine quarantine/Gatekeeper open test PASS

## Artifact Checks

- [ ] `artifacts/status.json` exists and valid JSON
- [ ] `artifacts/test_summary.json` exists and valid JSON
- [ ] `artifacts/benchmark_summary.json` exists and valid JSON
- [ ] `artifacts/router_shadow_summary.json` exists and valid JSON
- [ ] `artifacts/research_summary.json` exists and valid JSON
- [ ] `artifacts/team_summary.json` exists and valid JSON
- [ ] `artifacts/team_pilot_report.json` exists and reports `overall_status=pass`
- [ ] `artifacts/security_posture.json` exists and reports `overall_status=pass`
- [ ] `artifacts/metrics_snapshot.json` exists and valid JSON
- [ ] `artifacts/qualification_report.json` exists and reports a support boundary table
- [ ] `artifacts/ga_readiness_report.json` exists and reports no `red` blocker before GA review
- [ ] Benchmark JSON outputs exist under `benchmarks/results/`
- [ ] Ablation Markdown report exists
- [ ] Team run artifacts exist under `.imperaos/team/jobs/<job_id>/`
- [ ] `uv run imperaos team replay --job-id <id> --root-dir .imperaos/team/jobs --verify --json` passes on clean smoke traces
- [ ] `uv run imperaos team resume --spec team.yaml --job-id <id> --root-dir .imperaos/team/jobs --json` only works when approvals are `executed` and not yet `consumed`
- [ ] README command examples are current
- [ ] Pre-production: one real provider team E2E run completed in target environment

## Controlled Pilot Smoke

- [ ] `uv run imperaos team pilot-check --spec examples/team/restricted_pilot_live.yaml --profile restricted --mode live-provider --provider auto --report artifacts/team_pilot_live_report.json --json`
- [ ] live-provider report classifies failures (`failure_class`) and reports `bounded_concurrency_status=pass`
- [ ] live smoke emits audit envelope, replay verify passes, and tamper probe still fails under the same release candidate
- [ ] approval reuse probe remains blocked after the live smoke
