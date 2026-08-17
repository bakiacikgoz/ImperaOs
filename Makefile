.PHONY: bootstrap bootstrap-macos bootstrap-windows install lint test check doctor chat benchmark benchmark-team benchmark-ablation benchmark-energy brand-consistency-gate pilot-gate enterprise-gate qualification-run vision-gate provider-native-gate provider-runtime-gate provider-workflow-proof-gate provider-governance-gate provider-v1-1-closure-gate provider-native-adapter-gate provider-governance-pr-readiness target-evidence-rehearsal-gate operator-attestation-gate design-partner-pilot-candidate-gate design-partner-rc-audit-gate design-partner-field-evidence-gate design-partner-handoff-gate mainline-rc-freeze-gate rc-evidence-orchestrator-gate rc-release-decision-gate enterprise-workspace-onboarding-gate enterprise-workspace-release-closure-gate product-complete-scope-gate assistant-real-runtime-gate first-run-readiness-gate governed-agent-workflow-product-gate product-complete-closure-gate product-desktop-smoke-gate memory-governance-gate memory-index-gate memory-authority-gate memory-operator-panel-gate memory-runtime-gate memory-runtime-policy-gate memory-context-pack-gate memory-sync-gate governed-memory-v1-gate workspace-memory-authority-gate memory-rbac-gate memory-workspace-sync-gate memory-migration-dry-run-gate memory-authority-operator-gate semantic-memory-index-gate memory-retrieval-quality-gate memory-privacy-leakage-gate memory-backend-benchmark-gate governed-pilot-workflow-gate control-plane-schemas control-plane-snapshot-gate control-plane-gate evidence-pack-gate enterprise-hat-a-evidence-gate evidence-corpus-gate install-rehearsal-gate external-agent-pilot-gate external-agent-v1-1-gate pilot-operations-gate governance-admin-gate security-review-pack-gate operator-panel-fallow-report operator-panel-boundary-gate operator-panel-fallow-gate ci-node24-inventory design-partner-beta-pack design-partner-beta-gate design-partner-pilot-gate agent-control-plane-v1-gate operator-panel-i18n-gate operator-panel-productization-gate operator-panel-tauri-smoke pilot-readiness-gate design-partner-rc-gate ui-gate ui-e2e-gate rust-gate mainline-gate ui-install ui-dev ui-build ui-tauri-build
.PHONY: macos-local-trial-gate operator-panel-bridge-parity-gate macos-bundled-runtime-gate artifact-contract-gate artifact-storage-gate artifact-rpc-gate artifact-security-gate artifact-ui-gate artifact-e2e-gate artifact-export-gate artifact-license-gate artifact-workspace-release-gate

artifact-contract-gate:
	uv run python scripts/run_artifact_workspace_release_gate.py --gate contract --profile enterprise --json

artifact-storage-gate:
	uv run python scripts/run_artifact_workspace_release_gate.py --gate storage --profile enterprise --json

artifact-rpc-gate:
	uv run python scripts/run_artifact_workspace_release_gate.py --gate rpc --profile enterprise --json

artifact-security-gate:
	uv run python scripts/run_artifact_workspace_release_gate.py --gate security --profile enterprise --json

artifact-ui-gate:
	uv run python scripts/run_artifact_workspace_release_gate.py --gate ui --profile enterprise --json

artifact-e2e-gate:
	uv run python scripts/run_artifact_workspace_release_gate.py --gate e2e --profile enterprise --json

artifact-export-gate:
	uv run python scripts/run_artifact_workspace_release_gate.py --gate export --profile enterprise --json

artifact-license-gate:
	uv run python scripts/run_artifact_workspace_release_gate.py --gate license --profile enterprise --json

artifact-workspace-release-gate:
	uv run python scripts/run_artifact_workspace_release_gate.py --gate workspace-release --profile enterprise --json

bootstrap: bootstrap-macos

bootstrap-macos:
	bash scripts/bootstrap_macos.sh

bootstrap-windows:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap_windows.ps1

install:
	uv sync --python 3.11 --extra dev

lint:
	uv run ruff check .

test:
	uv run pytest -q

check: lint test

brand-consistency-gate:
	uv run python scripts/run_brand_consistency_gate.py \
		--mode enforce \
		--output-root artifacts/rebrand/ci \
		--json

doctor:
	uv run imperaos doctor --profile balanced

chat:
	uv run imperaos chat --profile lite

benchmark:
	uv run imperaos benchmark smoke --mode all --profile balanced

benchmark-team:
	uv run imperaos benchmark team --profile balanced --suite smoke --spec team.yaml

benchmark-ablation:
	uv run imperaos benchmark ablation --mode all --profile balanced

benchmark-energy:
	uv run imperaos benchmark energy --profile balanced --energy-mode measured

pilot-gate:
	uv run pytest -q \
		tests/test_team_bounded_concurrency.py \
		tests/test_team_governance.py \
		tests/test_team_memory_fail_closed.py \
		tests/test_team_audit_envelope.py \
		tests/test_team_cli.py \
		tests/test_team_pilot_gate.py
	uv run imperaos team validate --spec examples/team/restricted_pilot.yaml --json
	uv run imperaos team pilot-check \
		--spec examples/team/restricted_pilot.yaml \
		--profile restricted \
		--mode deterministic \
		--report artifacts/team_pilot_report.json \
		--json

enterprise-gate:
	uv run pytest -q tests/test_enterprise_cli.py tests/test_enterprise_qualification.py
	rm -rf .imperaos/enterprise/keys .imperaos/enterprise/identity
	rm -f artifacts/qualification_report.json artifacts/QUALIFICATION_REPORT.md
	uv run python scripts/prepare_enterprise_fixture.py --root .
	uv run imperaos security baseline --profile enterprise --json
	uv run imperaos auth whoami --profile enterprise --json
	uv run imperaos auth check --profile enterprise --permission runtime.run --json
	uv run imperaos keys verify --profile enterprise --path artifacts/security_posture.json --json
	uv run imperaos metrics snapshot --profile enterprise --json
	uv run imperaos ga readiness --profile enterprise --report artifacts/ga_readiness_report.json --json
	uv run imperaos keys verify --profile enterprise --path artifacts/ga_readiness_report.json --json
	uv run imperaos support bundle export --profile enterprise --json

vision-gate:
	uv run --extra dev pytest -q \
		tests/test_computer_use_vision_contracts.py \
		tests/test_computer_use_vision_provider.py \
		tests/test_computer_use_vision_planner.py \
		tests/test_computer_use_vision_policy.py \
		tests/test_computer_use_vision_approval.py \
		tests/test_computer_use_vision_verifier.py \
		tests/test_computer_use_vision_runtime.py \
		tests/test_computer_use_vision_qualification.py \
		tests/test_computer_use_vision_replay.py \
		tests/test_computer_use_macos_supervised_v2_gate.py
	uv run python -m imperaos computer-use doctor --json
	uv run python scripts/evaluate_computer_use_platform_matrix.py \
		--profile balanced \
		--output artifacts/computer_use/platform_matrix.json \
		--markdown artifacts/computer_use/PLATFORM_MATRIX.md
	uv run python scripts/evaluate_macos_supervised_vision_gate.py \
		--evidence-root artifacts/computer_use \
		--output artifacts/computer_use/macos_supervised_v2_gate.json \
		--markdown artifacts/computer_use/MACOS_SUPERVISED_V2_GATE.md \
		--json

provider-native-gate:
	uv run python scripts/run_provider_native_adapter_gate.py --profile enterprise --json

provider-runtime-gate:
	uv run pytest -q tests/test_provider_runtime_evidence.py tests/test_provider_invocation_coordinator.py
	uv run imperaos provider invoke \
		--provider openai_responses \
		--model gpt-placeholder \
		--profile enterprise \
		--mode dry-run \
		--once "Inspect service alerts and draft read-only triage summary" \
		--json

provider-workflow-proof-gate:
	uv run pytest -q tests/test_provider_runtime_workflow_proof.py
	uv run python scripts/run_provider_runtime_workflow_proof.py \
		--profile enterprise \
		--provider openai_responses \
		--mode dry-run \
		--output-root artifacts/provider-runtime/workflow-proof \
		--json

provider-governance-gate:
	uv run --extra dev python scripts/generate_model_provider_contract_schemas.py
	uv run --extra dev python -m pytest -q \
		tests/test_model_provider_contracts.py \
		tests/test_model_provider_registry.py \
		tests/test_model_provider_policy.py \
		tests/test_model_provider_redaction.py \
		tests/test_model_provider_envelope.py \
		tests/test_model_provider_openai_compatible.py \
		tests/test_model_provider_cli.py \
		tests/test_model_provider_no_secret_leak.py \
		tests/test_model_provider_budget.py \
		tests/test_model_provider_network_guard.py \
		tests/test_model_provider_canary_evidence.py \
		tests/test_model_provider_canary.py \
		tests/test_model_provider_router_shadow.py \
		tests/test_model_provider_native_contracts.py \
		tests/test_model_provider_tool_policy.py \
		tests/test_openai_responses_adapter.py \
		tests/test_provider_native_anthropic_messages.py \
		tests/test_provider_native_adapter_gate.py \
		tests/test_provider_governance_gate.py
	uv run --extra dev python scripts/run_provider_governance_gate.py --profile enterprise --json
	uv run --extra dev python scripts/run_provider_canary_fixture.py --profile enterprise --json
	uv run --extra dev python scripts/generate_provider_canary_evidence.py --profile enterprise --json
	uv run --extra dev python -m imperaos provider canary verify \
		--evidence-root artifacts/model-provider-governance/canary \
		--json
	uv run --extra dev python scripts/generate_model_provider_governance_evidence.py --profile enterprise --json

provider-v1-1-closure-gate: provider-governance-gate
	uv run --extra dev python scripts/generate_provider_conformance_matrix.py \
		--profile enterprise \
		--mode offline \
		--output-root artifacts/model-provider-governance/conformance \
		--json
	uv run --extra dev python scripts/verify_provider_release_closure.py \
		--profile enterprise \
		--evidence-root artifacts/model-provider-governance/v1_1 \
		--json
	uv run --extra dev python scripts/run_provider_native_adapter_gate.py \
		--profile enterprise \
		--output-root artifacts/model-provider-governance/native-v2 \
		--json

provider-native-adapter-gate:
	uv run --extra dev python scripts/generate_model_provider_contract_schemas.py
	uv run --extra dev python -m pytest -q \
		tests/test_model_provider_native_contracts.py \
		tests/test_model_provider_tool_policy.py \
		tests/test_openai_responses_adapter.py \
		tests/test_provider_native_anthropic_messages.py \
		tests/test_provider_native_adapter_gate.py
	uv run --extra dev python scripts/run_provider_native_adapter_gate.py \
		--profile enterprise \
		--output-root artifacts/model-provider-governance/native-v2 \
		--json
	uv run --extra dev python -m imperaos provider native conformance run \
		--profile enterprise \
		--provider-kind anthropic_messages \
		--offline \
		--json
	uv run --extra dev python -m imperaos provider native conformance verify \
		--input artifacts/model-provider-governance/native-v2/anthropic_messages_native_adapter_report.json \
		--json

design-partner-rc-audit-gate:
	uv run python scripts/run_design_partner_rc_audit_gate.py \
		--profile enterprise \
		--allow-expected-conditionals \
		--output artifacts/design-partner-rc/rc_audit_gate.json \
		--json

memory-governance-gate:
	uv run python scripts/run_memory_governance_gate.py

memory-index-gate:
	uv run python scripts/run_memory_index_gate.py

memory-authority-gate:
	uv run python scripts/run_memory_authority_gate.py

memory-operator-panel-gate:
	uv run python scripts/run_memory_operator_panel_gate.py

memory-runtime-gate:
	uv run pytest -q tests/test_memory_runtime_bridge.py tests/test_orchestrator_memory_runtime.py tests/test_team_memory_runtime_bridge.py tests/test_control_plane_snapshot_memory_runtime.py
	uv run python scripts/run_memory_runtime_gate.py

memory-runtime-policy-gate:
	uv run python scripts/generate_memory_runtime_policy_contract_schemas.py
	uv run --extra dev pytest -q \
		tests/test_memory_runtime_policy_models.py \
		tests/test_memory_principal_resolver.py \
		tests/test_memory_runtime_policy_gateway.py \
		tests/test_memory_runtime_policy_semantic.py \
		tests/test_orchestrator_memory_policy_enforcement.py \
		tests/test_team_memory_policy_enforcement.py \
		tests/test_control_plane_snapshot_memory_policy.py \
		tests/test_memory_runtime_policy_cli.py \
		tests/test_memory_runtime_policy_privacy.py
	uv run imperaos memory runtime policy evaluate \
		--suite benchmarks/tasks/memory/runtime_policy_cases.jsonl \
		--output artifacts/memory-runtime-policy/evaluation.json \
		--profile enterprise
	uv run python scripts/run_memory_runtime_policy_gate.py
	pnpm -C apps/operator-panel exec vitest run src/memory-runtime/MemoryRuntimePolicyView.test.tsx

memory-context-pack-gate:
	uv run pytest -q tests/test_memory_context_pack.py
	uv run python scripts/run_memory_context_pack_gate.py

memory-sync-gate:
	uv run pytest -q tests/test_memory_sync_pack.py tests/test_memory_sync_importer.py tests/test_memory_sync_cli.py
	uv run python scripts/run_memory_sync_gate.py

workspace-memory-authority-gate:
	uv run pytest -q \
		tests/test_memory_workspace_authority.py \
		tests/test_memory_access_evaluator.py \
		tests/test_memory_workspace_sync.py \
		tests/test_memory_migration_planner.py \
		tests/test_memory_authority_cli.py \
		tests/test_memory_runtime_workspace_integration.py \
		tests/test_memory_authority_snapshot.py \
		tests/test_memory_authority_no_raw_leakage.py
	uv run python scripts/generate_memory_workspace_contract_schemas.py
	uv run python scripts/run_workspace_memory_authority_gate.py
	$(MAKE) memory-rbac-gate
	$(MAKE) memory-workspace-sync-gate
	$(MAKE) memory-migration-dry-run-gate
	$(MAKE) memory-authority-operator-gate

memory-rbac-gate:
	uv run pytest -q tests/test_memory_access_evaluator.py
	uv run python scripts/run_memory_rbac_gate.py

memory-workspace-sync-gate:
	uv run pytest -q tests/test_memory_workspace_sync.py
	uv run python scripts/run_memory_workspace_sync_gate.py

memory-migration-dry-run-gate:
	uv run pytest -q tests/test_memory_migration_planner.py
	uv run python scripts/run_memory_migration_dry_run_gate.py

memory-authority-operator-gate:
	uv run pytest -q tests/test_memory_authority_snapshot.py
	uv run python scripts/run_memory_authority_operator_gate.py
	pnpm --dir apps/operator-panel install --frozen-lockfile
	pnpm --dir apps/operator-panel exec vitest run src/memory-authority/MemoryAuthorityView.test.tsx src/routeRegistry.test.ts

semantic-memory-index-gate:
	uv run pytest -q \
		tests/test_memory_semantic_models.py \
		tests/test_memory_embedding_provider.py \
		tests/test_memory_semantic_index_manifest.py \
		tests/test_memory_semantic_index_router.py \
		tests/test_memory_hybrid_retriever.py \
		tests/test_memory_turbovec_backend_optional.py \
		tests/test_memory_semantic_cli.py \
		tests/test_control_plane_memory_semantic_snapshot.py
	uv run python scripts/generate_memory_semantic_contract_schemas.py
	uv run python scripts/run_semantic_memory_index_gate.py
	pnpm --dir apps/operator-panel install --frozen-lockfile
	pnpm --dir apps/operator-panel exec vitest run src/memory-semantic/MemorySemanticIndexView.test.tsx src/routeRegistry.test.ts

memory-retrieval-quality-gate:
	uv run pytest -q tests/test_memory_retrieval_quality.py
	uv run python scripts/run_memory_retrieval_quality_gate.py

memory-privacy-leakage-gate:
	uv run pytest -q tests/test_memory_privacy_leakage.py
	uv run python scripts/run_memory_privacy_leakage_gate.py

memory-backend-benchmark-gate:
	uv run python scripts/run_memory_backend_benchmark.py

governed-pilot-workflow-gate:
	uv run python scripts/generate_pilot_workflow_contract_schemas.py
	uv run python scripts/generate_control_plane_contract_schemas.py
	uv run --extra dev pytest -q \
		tests/test_governed_pilot_workflow.py \
		tests/test_governed_pilot_workflow_cli.py \
		tests/test_control_plane_governed_pilot_workflow_snapshot.py
	uv run python scripts/run_governed_pilot_workflow_gate.py --json
	pnpm --dir apps/operator-panel exec vitest run src/governed-pilot-workflow/GovernedPilotWorkflowView.test.tsx src/routeRegistry.test.ts

design-partner-field-evidence-gate:
	uv run python scripts/generate_control_plane_contract_schemas.py
	uv run --extra dev pytest -q \
		tests/test_design_partner_field_evidence.py \
		tests/test_operator_attestation_field_binding.py \
		tests/test_design_partner_strict_rc_promotion.py \
		tests/test_control_plane_snapshot_field_evidence.py \
		tests/test_design_partner_field_evidence_cli.py
	uv run python scripts/run_design_partner_field_evidence_gate.py --json
	pnpm --dir apps/operator-panel exec vitest run src/provider-governance/DesignPartnerFieldEvidenceView.test.tsx src/routeRegistry.test.ts
	pnpm --dir apps/operator-panel exec playwright test e2e/design-partner-field-evidence.spec.ts
	git diff --check

design-partner-handoff-gate:
	uv run --extra dev ruff check .
	uv run --extra dev pytest -q \
		tests/test_release_train.py \
		tests/test_design_partner_handoff.py \
		tests/test_pilot_ops_drill.py \
		tests/test_design_partner_handoff_cli.py
	uv run python scripts/generate_control_plane_contract_schemas.py
	uv run python scripts/run_design_partner_handoff_gate.py --profile enterprise --json
	$(MAKE) design-partner-field-evidence-gate
	$(MAKE) governed-pilot-workflow-gate
	$(MAKE) design-partner-rc-audit-gate
	$(MAKE) control-plane-gate
	corepack pnpm --dir apps/operator-panel test
	corepack pnpm --dir apps/operator-panel lint
	corepack pnpm --dir apps/operator-panel build
	corepack pnpm --dir apps/operator-panel exec playwright test e2e/design-partner-handoff.spec.ts --pass-with-no-tests
	git diff --check

mainline-rc-freeze-gate:
	uv run --extra dev ruff check .
	uv run --extra dev python -m pytest -q \
		tests/test_mainline_stack.py \
		tests/test_release_artifact_scan.py \
		tests/test_rc_freeze_manifest.py \
		tests/test_mainline_rc_freeze_cli.py \
		tests/test_control_plane_snapshot_mainline_rc_freeze.py
	uv run python scripts/generate_control_plane_contract_schemas.py
	git diff --exit-code contracts/control_plane contracts/operator_panel/schemas
	uv run imperaos release mainline stack-verify \
		--stack examples/release/design_partner_rc_stack.yaml \
		--json
	uv run imperaos release mainline rehearse \
		--base main \
		--head codex/design-partner-rc-handoff-ops-readiness-v1 \
		--mode dry-run \
		--output-root artifacts/mainline-rc-freeze \
		--json
	uv run python scripts/generate_mainline_rc_freeze_pack.py \
		--profile enterprise \
		--stack examples/release/design_partner_rc_stack.yaml \
		--evidence-root artifacts \
		--output-root artifacts/mainline-rc-freeze \
		--json
	uv run imperaos release rc-freeze verify \
		--manifest artifacts/mainline-rc-freeze/manifest.json \
		--json
	uv run python scripts/run_mainline_rc_freeze_gate.py --profile enterprise --json
	corepack pnpm --dir apps/operator-panel exec vitest run src/mainline-rc-freeze/MainlineRcFreezeView.test.tsx
	corepack pnpm --dir apps/operator-panel exec playwright test e2e/mainline-rc-freeze.spec.ts --pass-with-no-tests
	git diff --check

rc-evidence-orchestrator-gate:
	uv run python scripts/run_rc_evidence_orchestrator_gate.py --profile enterprise --json

rc-release-decision-gate:
	uv run python scripts/run_rc_release_decision_gate.py --profile enterprise --json

enterprise-workspace-onboarding-gate:
	uv run --extra dev ruff check .
	uv run python scripts/generate_enterprise_workspace_contract_schemas.py
	uv run python scripts/generate_control_plane_contract_schemas.py
	uv run --extra dev python -m pytest -q \
		tests/test_enterprise_workspace_models.py \
		tests/test_enterprise_workspace_rbac.py \
		tests/test_agent_enrollment.py \
		tests/test_enterprise_workspace_contracts.py \
		tests/test_enterprise_workspace_store.py \
		tests/test_enterprise_workspace_cli.py \
		tests/test_agent_enrollment_cli.py \
		tests/test_agent_enrollment_evidence.py \
		tests/test_agent_registry_workspace_binding.py \
		tests/test_external_gateway_enrollment_guard.py \
		tests/test_memory_enterprise_workspace_binding.py \
		tests/test_control_plane_snapshot_enterprise_workspace.py \
		tests/test_enterprise_workspace_onboarding_gate.py
	uv run python scripts/run_enterprise_workspace_onboarding_gate.py --profile enterprise --json
	corepack pnpm --dir apps/operator-panel exec vitest run src/enterprise-workspace/EnterpriseWorkspaceView.test.tsx src/enterprise-workspace/AgentEnrollmentView.test.tsx src/routeRegistry.test.ts
	corepack pnpm --dir apps/operator-panel lint
	corepack pnpm --dir apps/operator-panel build
	corepack pnpm --dir apps/operator-panel exec playwright test e2e/enterprise-workspace.spec.ts --pass-with-no-tests
	git diff --check

enterprise-workspace-release-closure-gate:
	uv run python scripts/run_enterprise_workspace_release_closure_gate.py --profile enterprise --json

product-complete-scope-gate:
	uv run python scripts/run_product_complete_scope_gate.py --json

assistant-real-runtime-gate:
	uv run python scripts/run_assistant_real_runtime_gate.py --profile enterprise --json

first-run-readiness-gate:
	uv run python scripts/run_first_run_readiness_gate.py --profile enterprise --json

governed-agent-workflow-product-gate:
	uv run python scripts/run_governed_agent_workflow_product_gate.py --profile enterprise --json

product-complete-closure-gate:
	uv run python scripts/run_product_complete_closure_gate.py --profile enterprise --json

product-desktop-smoke-gate:
	corepack pnpm --dir apps/operator-panel build
	cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml --target-dir apps/operator-panel/src-tauri/target-codex-test

enterprise-workspace-pr-readiness-gate:
	uv run python scripts/run_enterprise_workspace_pr_readiness_gate.py --profile enterprise --expected-branch $$(git branch --show-current) --json

enterprise-workspace-remote-pr-ci-gate:
	uv run python scripts/run_enterprise_workspace_remote_pr_ci_gate.py --profile enterprise --branch $$(git branch --show-current) --json

governed-memory-v1-gate:
	uv run pytest -q tests/test_memory_v3_governance.py tests/test_memory_cli_v3.py tests/test_control_plane_snapshot_memory_v3.py
	uv run python scripts/generate_memory_contract_schemas.py
	$(MAKE) memory-governance-gate
	$(MAKE) memory-index-gate
	$(MAKE) memory-authority-gate
	$(MAKE) memory-operator-panel-gate

provider-governance-pr-readiness:
	uv run python scripts/check_provider_governance_pr_readiness.py \
		--profile enterprise \
		--branch $$(git branch --show-current) \
		--output artifacts/provider-governance-pr/readiness.json \
		--json

target-evidence-rehearsal-gate:
	uv run --extra dev pytest -q tests/test_target_evidence_session.py tests/test_target_evidence_rehearsal.py
	uv run python scripts/prepare_target_evidence_session.py \
		--profile enterprise \
		--mode rehearsal \
		--environment-label local-enterprise-rehearsal \
		--output-root artifacts/design-partner-target-evidence \
		--json
	uv run python scripts/collect_target_evidence_rehearsal.py \
		--session artifacts/design-partner-target-evidence/session.json \
		--output-root artifacts/design-partner-target-evidence \
		--json
	uv run python scripts/verify_target_evidence_bundle.py \
		--bundle artifacts/design-partner-target-evidence/target_evidence_bundle.json \
		--json

operator-attestation-gate:
	uv run --extra dev pytest -q tests/test_operator_attestation.py
	uv run python scripts/prepare_target_evidence_session.py \
		--profile enterprise \
		--mode rehearsal \
		--environment-label local-enterprise-rehearsal \
		--output-root artifacts/design-partner-target-evidence \
		--json
	uv run python scripts/generate_operator_attestation.py \
		--session artifacts/design-partner-target-evidence/session.json \
		--operator-display-name local-operator \
		--output-root artifacts/design-partner-target-evidence \
		--json

design-partner-pilot-candidate-gate:
	uv run --extra dev pytest -q tests/test_pilot_candidate_pack.py tests/test_pr_readiness_gate.py
	$(MAKE) target-evidence-rehearsal-gate
	$(MAKE) operator-attestation-gate
	uv run python scripts/generate_design_partner_rc_pack.py \
		--profile enterprise \
		--output artifacts/design-partner-rc \
		--target-evidence-root artifacts/design-partner-target-evidence \
		--json
	uv run python scripts/generate_design_partner_pilot_candidate_pack.py \
		--profile enterprise \
		--target-evidence-root artifacts/design-partner-target-evidence \
		--rc-root artifacts/design-partner-rc \
		--output-root artifacts/design-partner-pilot-candidate \
		--json

control-plane-schemas:
	uv run python scripts/generate_control_plane_contract_schemas.py

control-plane-snapshot-gate:
	uv run imperaos control-plane snapshot --json
	uv run pytest -q tests/test_control_plane_snapshot.py
	corepack pnpm --dir apps/operator-panel test -- controlPlaneSnapshot

control-plane-gate:
	uv run pytest -q \
		tests/test_control_plane_models.py \
		tests/test_control_plane_registry.py \
		tests/test_control_plane_policy_simulator.py \
		tests/test_control_plane_evidence_pack.py \
		tests/test_control_plane_claim_guard.py \
		tests/test_control_plane_cli.py \
		tests/test_control_plane_snapshot.py
	uv run python scripts/generate_control_plane_contract_schemas.py
	git diff --exit-code contracts/control_plane
	uv run imperaos control-plane doctor --profile enterprise --json
	uv run imperaos control-plane snapshot --profile enterprise --json
	uv run python scripts/evaluate_control_plane_claims.py --profile enterprise --json

evidence-pack-gate:
	uv run pytest -q tests/test_control_plane_evidence_pack.py
	corepack pnpm --dir apps/operator-panel test -- EvidencePackView
	corepack pnpm --dir apps/operator-panel test:e2e -- evidence.spec.ts

enterprise-hat-a-evidence-gate:
	uv run pytest -q tests/test_control_plane_qualification_closure.py tests/test_control_plane_claim_guard.py
	uv run python scripts/prepare_enterprise_fixture.py --root .
	uv run python scripts/generate_enterprise_hat_a_fixture.py --json
	uv run imperaos control-plane qualification close \
		--profile enterprise \
		--qualification-root artifacts/enterprise-hat-a/qualification \
		--output-root artifacts/enterprise-hat-a \
		--json
	uv run imperaos control-plane qualification verify \
		--profile enterprise \
		--input artifacts/enterprise-hat-a/enterprise_hat_a_closure.json \
		--json
	uv run imperaos control-plane claims verify --profile enterprise --evidence-root artifacts --json

evidence-corpus-gate:
	uv run pytest -q tests/test_control_plane_evidence_corpus.py tests/test_evidence_index.py
	uv run python scripts/prepare_enterprise_fixture.py --root .
	uv run python scripts/evaluate_evidence_corpus.py --json
	uv run imperaos control-plane evidence index \
		--profile enterprise \
		--evidence-root artifacts/evidence-corpus/valid \
		--root-dir artifacts/evidence-corpus/index-state \
		--json

install-rehearsal-gate:
	uv run pytest -q tests/test_control_plane_install_rehearsal.py
	uv run python scripts/prepare_enterprise_fixture.py --root .
	uv run imperaos control-plane install rehearsal \
		--profile enterprise \
		--target-root .imperaos/rehearsal/design-partner \
		--mode source-cli \
		--output artifacts/install-rehearsal/report.json \
		--json

external-agent-pilot-gate:
	uv run pytest -q tests/test_control_plane_external_agent_client.py tests/test_external_agent_gateway.py
	uv run python scripts/prepare_enterprise_fixture.py --root .
	uv run python scripts/run_external_agent_pilot.py --json

external-agent-v1-1-gate:
	uv run pytest -q tests/test_external_agent_gateway.py tests/test_external_agent_gateway_v1_1.py
	uv run python scripts/generate_control_plane_contract_schemas.py
	test -f contracts/control_plane/external_agent_request_v1_1.schema.json
	test -f contracts/control_plane/external_agent_result_v1_1.schema.json
	uv run python scripts/run_external_agent_v1_1_pilot.py --json

pilot-operations-gate:
	uv run pytest -q tests/test_pilot_operations.py tests/test_control_plane_snapshot.py
	uv run imperaos pilot first-run --json
	uv run imperaos control-plane snapshot --profile enterprise --json
	corepack pnpm --dir apps/operator-panel test -- controlPlaneSnapshot

governance-admin-gate:
	uv run pytest -q tests/test_control_plane_admin_store.py tests/test_control_plane_policy_pack_lifecycle.py tests/test_rbac_admin.py tests/test_policy_packs.py
	uv run python scripts/prepare_enterprise_fixture.py --root .
	uv run python scripts/evaluate_governance_admin.py --json

security-review-pack-gate:
	uv run pytest -q tests/test_control_plane_security_review.py
	uv run python scripts/prepare_enterprise_fixture.py --root .
	uv run imperaos control-plane security review \
		--profile enterprise \
		--output-root artifacts/security-review \
		--evidence-root artifacts/evidence-corpus/valid \
		--json

operator-panel-fallow-report:
	FALLOW_TELEMETRY_DISABLED=1 DO_NOT_TRACK=1 corepack pnpm --dir apps/operator-panel fallow:report

operator-panel-boundary-gate: operator-panel-fallow-report
	BOUNDARY_GATE_MODE=enforce corepack pnpm --dir apps/operator-panel fallow:boundary

operator-panel-fallow-gate: operator-panel-fallow-report
	BOUNDARY_GATE_MODE=enforce corepack pnpm --dir apps/operator-panel fallow:boundary
	FALLOW_GATE_MODE=$${FALLOW_GATE_MODE:-warn} corepack pnpm --dir apps/operator-panel fallow:policy
	corepack pnpm --dir apps/operator-panel test -- scripts/fallow-policy

ci-node24-inventory:
	uv run pytest -q tests/test_ci_node_action_inventory.py
	uv run python scripts/collect_ci_node_action_inventory.py --workflow-root .github/workflows --output-root artifacts/ci --json

design-partner-beta-pack:
	uv run pytest -q tests/test_design_partner_beta_pack.py
	uv run python scripts/generate_design_partner_beta_pack.py --json

design-partner-beta-gate:
	$(MAKE) design-partner-pilot-gate
	$(MAKE) operator-panel-fallow-gate
	$(MAKE) ci-node24-inventory
	$(MAKE) external-agent-v1-1-gate
	$(MAKE) pilot-operations-gate
	$(MAKE) design-partner-beta-pack
	uv run ruff check .
	uv run pytest -q
	corepack pnpm --dir apps/operator-panel test
	corepack pnpm --dir apps/operator-panel lint
	corepack pnpm --dir apps/operator-panel build
	corepack pnpm --dir apps/operator-panel test:e2e
	cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml
	git diff --check

design-partner-pilot-gate:
	uv run ruff check .
	uv run pytest -q
	corepack pnpm --dir apps/operator-panel test
	corepack pnpm --dir apps/operator-panel lint
	corepack pnpm --dir apps/operator-panel build
	corepack pnpm --dir apps/operator-panel pilot-launch:assert
	corepack pnpm --dir apps/operator-panel test:e2e
	cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml
	$(MAKE) enterprise-hat-a-evidence-gate
	$(MAKE) evidence-corpus-gate
	$(MAKE) install-rehearsal-gate
	$(MAKE) external-agent-pilot-gate
	$(MAKE) governance-admin-gate
	$(MAKE) security-review-pack-gate
	uv run python scripts/generate_design_partner_pilot_pack.py --output-root artifacts/design-partner-pilot --json
	git diff --check

ui-gate:
	corepack pnpm --dir apps/operator-panel qa:frontend

operator-panel-i18n-gate:
	corepack pnpm --dir apps/operator-panel i18n:coverage

operator-panel-productization-gate:
	corepack pnpm --dir apps/operator-panel qa:productization

operator-panel-tauri-smoke:
	corepack pnpm --dir apps/operator-panel tauri:smoke

operator-panel-bridge-parity-gate:
	corepack pnpm --dir apps/operator-panel bridge:parity

macos-local-trial-gate:
	uv run python scripts/run_macos_local_trial_gate.py --profile enterprise --json

macos-bundled-runtime-gate:
	apps/operator-panel/scripts/build_bundled_runtime_macos.sh arm64
	apps/operator-panel/scripts/verify_bundled_runtime_macos.sh arm64

pilot-readiness-gate:
	uv run ruff check .
	uv run pytest -q
	uv run python -m compileall imperaos
	uv run python -m imperaos control-plane snapshot --json
	corepack pnpm --dir apps/operator-panel test
	corepack pnpm --dir apps/operator-panel lint
	corepack pnpm --dir apps/operator-panel build
	corepack pnpm --dir apps/operator-panel test:e2e
	corepack pnpm --dir apps/operator-panel exec tsx scripts/assert-productized-pages.ts
	corepack pnpm --dir apps/operator-panel exec tsx scripts/assert-no-primary-raw-json.ts
	corepack pnpm --dir apps/operator-panel exec tsx scripts/assert-i18n-coverage.ts
	cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml
	$(MAKE) agent-control-plane-v1-gate
	$(MAKE) operator-panel-tauri-smoke
	corepack pnpm --dir apps/operator-panel pilot:assert
	$(MAKE) evidence-pack-gate
	git diff --check

design-partner-rc-gate:
	uv run ruff check .
	uv run pytest -q \
		tests/test_design_partner_rc.py \
		tests/test_design_partner_rc_pack.py \
		tests/test_external_agent_gateway.py \
		tests/test_agent_registry_v2.py \
		tests/test_policy_packs.py \
		tests/test_rbac_admin.py \
		tests/test_evidence_index.py \
		tests/test_reports_alerts.py \
		tests/test_operations_runner.py \
		tests/test_control_plane_snapshot.py
	uv run python scripts/generate_control_plane_contract_schemas.py
	corepack pnpm --dir apps/operator-panel test -- controlPlaneMappers controlPlaneSnapshot
	$(MAKE) enterprise-hat-a-evidence-gate
	uv run python scripts/run_external_agent_gateway_smoke.py
	uv run python scripts/evaluate_policy_pack_promotion.py
	uv run python scripts/evaluate_evidence_index.py --profile enterprise --evidence-root artifacts/control-plane/evidence --select-latest-valid --staged-evidence-root artifacts/design-partner-rc/evidence-sample --root-dir artifacts/design-partner-rc/evidence-index/state --output artifacts/design-partner-rc/evidence_index.json
	uv run python scripts/evaluate_reports_alerts.py --profile enterprise --root-dir .imperaos/control-plane --evidence-root artifacts --output-dir artifacts/design-partner-rc/reports-alerts-logs
	uv run python scripts/generate_design_partner_rc_pack.py --profile enterprise --state-root .imperaos/control-plane --evidence-root artifacts --output artifacts/design-partner-rc --fail-on-conditional --json
	git diff --check

ui-e2e-gate:
	corepack pnpm --dir apps/operator-panel test:e2e

rust-gate:
	cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml

mainline-gate:
	uv run --extra dev ruff check .
	uv run --extra dev pytest -q
	$(MAKE) provider-native-gate
	$(MAKE) provider-runtime-gate
	$(MAKE) provider-workflow-proof-gate
	$(MAKE) provider-governance-gate
	$(MAKE) design-partner-pilot-candidate-gate
	$(MAKE) design-partner-rc-audit-gate
	$(MAKE) control-plane-gate
	$(MAKE) vision-gate
	$(MAKE) ui-gate
	$(MAKE) rust-gate
	git diff --check

agent-control-plane-v1-gate:
	$(MAKE) control-plane-gate
	$(MAKE) enterprise-gate
	$(MAKE) pilot-gate
	$(MAKE) ui-gate
	$(MAKE) rust-gate
	uv run python scripts/build_control_plane_release_pack.py --profile enterprise --output artifacts/release-pack/control-plane-v1 --json

qualification-run:
	uv run imperaos qualification run \
		--profile enterprise \
		--mode mixed \
		--soak-hours 6 \
		--output-root artifacts/qualification \
		--json

ui-install:
	cd apps/operator-panel && pnpm install

ui-dev:
	cd apps/operator-panel && pnpm tauri:dev

ui-build:
	cd apps/operator-panel && pnpm build

ui-tauri-build:
	cd apps/operator-panel && pnpm tauri:build
