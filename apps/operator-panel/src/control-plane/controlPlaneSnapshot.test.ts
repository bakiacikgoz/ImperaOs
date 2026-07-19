import { beforeEach, describe, expect, it } from 'vitest';

import { assertNoSilentMockFallback, describeDataSource, SilentMockFallbackError } from './dataSource';
import { clearControlPlaneSnapshotCache, loadControlPlaneSnapshot } from './snapshot';
import type { ControlPlaneSnapshot } from './types';

describe('controlPlaneSnapshot runtime truth', () => {
  beforeEach(() => {
    clearControlPlaneSnapshotCache();
  });

  it('loads a live snapshot into a page view model', async () => {
    const snapshot = makeSnapshot();
    const vm = await loadControlPlaneSnapshot({
      getControlPlaneSnapshot: async () => snapshot,
    });

    expect(vm.error).toBeUndefined();
    expect(vm.data.contractVersion).toBe('control-plane.snapshot/v1');
    expect(vm.dataSource.mode).toBe('cli_live');
    expect(vm.subtitle).toBe('Partial pilot readiness.');
    expect(vm.empty).toBeUndefined();
  });

  it('fails closed when live mode silently falls back to mock data', async () => {
    const snapshot = makeSnapshot({
      dataSource: {
        ...makeSnapshot().dataSource,
        mode: 'preview_fixture',
        isMock: true,
        isSilentFallback: true,
      },
    });

    expect(() => assertNoSilentMockFallback(snapshot.dataSource)).toThrow(SilentMockFallbackError);
    const vm = await loadControlPlaneSnapshot({
      getControlPlaneSnapshot: async () => snapshot,
    });

    expect(vm.error?.code).toBe('SilentMockFallbackError');
    expect(vm.dataSource.mode).toBe('error');
    expect(describeDataSource(snapshot.dataSource)).toContain('fail closed');
  });

  it('reuses cached snapshots until force refresh is requested', async () => {
    let calls = 0;
    const bridge = {
      getControlPlaneSnapshot: async () => {
        calls += 1;
        return makeSnapshot({
          dashboard: {
            ...makeSnapshot().dashboard,
            runCount: calls,
          },
        });
      },
    };

    const first = await loadControlPlaneSnapshot(bridge);
    const cached = await loadControlPlaneSnapshot(bridge);
    const refreshed = await loadControlPlaneSnapshot(bridge, { forceRefresh: true });

    expect(first.data.dashboard.runCount).toBe(1);
    expect(cached.data.dashboard.runCount).toBe(1);
    expect(refreshed.data.dashboard.runCount).toBe(2);
  });
});

function makeSnapshot(overrides: Partial<ControlPlaneSnapshot> = {}): ControlPlaneSnapshot {
  const generatedAtUtc = '2026-06-01T12:00:00.000Z';
  return {
    contractVersion: 'control-plane.snapshot/v1',
    generatedAtUtc,
    dataSource: {
      mode: 'cli_live',
      isMock: false,
      isSilentFallback: false,
      lastRefreshUtc: generatedAtUtc,
      ageMs: 0,
      freshness: 'fresh',
      contractVersion: 'control-plane.snapshot/v1',
      sourceReason: 'CLI generated live snapshot',
    },
    system: {
      profile: 'lite',
      rootDir: '.imperaos/control-plane',
      coreVersion: '0.5.0',
      contractVersion: '3.0',
      health: {
        status: 'partial',
        confidence: 'medium',
        missingSignals: ['metrics_snapshot'],
        blockingReasons: [],
        lastDoctorStatus: 'healthy',
        humanSummary: 'Partial pilot readiness.',
      },
      doctor: { status: 'healthy' },
      capabilities: { controlPlaneSnapshot: true },
      configSummary: { governanceEnabled: true },
      sourceMap: { runs: 'control-plane run store' },
      warnings: ['metrics_snapshot'],
    },
    dashboard: {
      agentCount: 1,
      runCount: 1,
      pendingApprovalCount: 1,
      evidencePackCount: 0,
      activeAlertCount: 1,
      blockedClaimCount: 3,
      conditionalClaimCount: 1,
    },
    agents: [
      {
        agentId: 'governed-ops',
        displayName: 'Governed Ops',
        runtimeKind: 'imperaos_team',
        agentType: 'internal',
        status: 'registered',
        readiness: 'policy_simulated',
        ownerTeam: 'platform',
        policyPackId: 'active-runtime-policy',
        riskProfile: 'guarded',
        lastRunId: 'cp-run-preview',
        lastEvidencePackId: null,
        lastEvidenceStatus: 'missing',
      },
    ],
    runs: [
      {
        runId: 'cp-run-preview',
        agentId: 'governed-ops',
        profile: 'lite',
        status: 'approval_pending',
        submittedBy: 'cli:operator',
        identityRef: 'identity:disabled',
        inputHash: 'sha256:input',
        policyHash: 'sha256:policy',
        startedAt: generatedAtUtc,
        completedAt: null,
        approvalIds: ['approval-preview'],
        artifactRefs: [],
        evidencePackId: null,
        blockingReasons: [],
        nextActions: ['approval.show'],
      },
    ],
    approvals: [
      {
        approvalId: 'approval-preview',
        runId: 'cp-run-preview',
        status: 'pending',
        targetKind: 'control_plane_action',
        targetRef: 'governed-ops:inspect_queue',
        actionHash: 'sha256:action',
        policyHash: 'sha256:policy',
        requestHash: 'sha256:request',
        snapshotHash: 'sha256:snapshot',
        executionStatus: 'not_executed',
        createdAt: generatedAtUtc,
        expiresAt: '2026-06-02T12:00:00.000Z',
        actor: null,
        disabledReason: null,
      },
    ],
    evidencePacks: [],
    policyPacks: [],
    executionSurfaces: [],
    logs: [],
    alerts: [],
    reports: [],
    operations: [],
    admin: {
      users: [],
      roles: [],
      policyPacks: [],
      permissionMatrix: {},
      source: 'local_fixture',
    },
    designPartnerRc: {
      schemaVersion: 'control-plane.design-partner-rc/v1',
      generatedAtUtc,
      status: 'conditional',
      checks: [],
      blockers: [],
      warnings: ['evidence-index'],
      artifactRoot: 'artifacts/design-partner-rc',
    },
    pilotLaunch: {
      schemaVersion: 'control-plane.pilot-launch-readiness/v1',
      generatedAtUtc,
      status: 'conditional',
      headline: 'Pilot launch candidate is conditional.',
      artifactRoot: 'artifacts',
      enterpriseHatA: pilotTile('enterprise-hat-a', 'Enterprise Hat A', 'conditional'),
      installRehearsal: pilotTile('install-rehearsal', 'Install rehearsal', 'ready'),
      externalAgentPilot: pilotTile('external-agent-pilot', 'External agent pilot', 'ready'),
      governanceAdmin: pilotTile('governance-admin', 'Governance admin', 'ready'),
      securityReview: pilotTile('security-review', 'Security review', 'ready'),
      claimGuard: pilotTile('claim-guard', 'Claim guard', 'conditional'),
      evidenceCorpus: pilotTile('evidence-corpus', 'Evidence corpus', 'ready'),
      pilotMetrics: pilotTile('pilot-metrics', 'Pilot metrics', 'ready'),
      adminProposals: [],
      nextActions: [{ label: 'enterprise-hat-a', severity: 'warning', target: 'Reports' }],
      blockers: [],
      warnings: ['enterprise-hat-a'],
    },
    codeIntelligence: codeIntelligence(generatedAtUtc),
    pilotOperations: pilotOperations(generatedAtUtc),
    designPartnerBeta: designPartnerBeta(generatedAtUtc),
    providerGovernance: {
      contractVersion: 'control-plane.provider-governance/v1',
      generatedAtUtc,
      overallStatus: 'conditional',
      blockingReasons: ['blocked_external_credentials'],
      providers: [
        {
          providerKind: 'openai_responses',
          displayName: 'OpenAI Responses Native Preview',
          status: 'blocked',
          credentialState: 'missing',
          canaryOnly: true,
          supportsStreaming: true,
          serverToolsPolicy: 'denied',
          customToolsPolicy: 'proposal_only',
          retentionPolicy: 'hash_only_store_false',
          lastConformanceStatus: 'pass',
          blockingReasons: ['blocked_external_credentials'],
        },
      ],
    },
    providerRuntime: {
      contractVersion: 'control-plane.provider-runtime/v1',
      generatedAtUtc,
      enabled: false,
      latestInvocations: [],
      workflowProofs: [],
      blockingReasons: [],
    },
    targetEvidenceClosure: {
      contractVersion: 'control-plane.target-evidence-closure/v1',
      generatedAtUtc,
      status: 'conditional',
      sessionId: 'target-evidence-test',
      mode: 'rehearsal',
      evidenceMode: 'hash_only',
      rawPersistence: false,
      blockingReasons: [],
      warnings: ['TARGET_ENVIRONMENT_REHEARSAL_ONLY'],
      blockedClaims: [
        'public-desktop-installer',
        'live-macos-computer-use',
        'live-windows-computer-use',
        'live-linux-computer-use',
      ],
      attestationStatus: 'present',
    },
    quickActions: [],
    partialReasons: ['metrics_snapshot'],
    ...overrides,
  };
}

function pilotTile(tileId: string, label: string, status: 'ready' | 'conditional' | 'blocked' | 'missing') {
  return {
    tileId,
    label,
    status,
    detail: label,
    path: `artifacts/${tileId}.json`,
    blockingReasons: status === 'ready' ? [] : [tileId.toUpperCase().replaceAll('-', '_')],
  };
}

function codeIntelligence(generatedAtUtc: string) {
  return {
    schemaVersion: 'control-plane.code-intelligence-summary/v1' as const,
    generatedAtUtc,
    status: 'conditional' as const,
    verdict: 'warn',
    tool: 'fallow',
    toolVersion: '2.88.3',
    artifactRoot: 'artifacts/code-intelligence/fallow',
    telemetryDisabled: true,
    boundaryViolations: 0,
    secretScanStatus: 'pass',
    buckets: [
      {
        bucketId: 'boundaries',
        label: 'Architecture boundaries',
        status: 'ready' as const,
        count: 0,
        errors: 0,
        warnings: 0,
        path: 'artifacts/code-intelligence/fallow/boundaries.json',
        detail: 'no violations',
      },
    ],
    blockers: [],
    warnings: ['dead_code:1'],
  };
}

function pilotOperations(generatedAtUtc: string) {
  return {
    schemaVersion: 'control-plane.pilot-operations/v1' as const,
    generatedAtUtc,
    status: 'conditional' as const,
    headline: 'Pilot operations are conditional.',
    artifactRoot: 'artifacts/pilot-ops',
    checklist: [
      {
        itemId: 'pilot-launch-pack',
        label: 'Pilot launch pack',
        status: 'ready' as const,
        detail: 'status=ready',
        path: 'artifacts/design-partner-pilot/manifest.json',
        blocking: false,
      },
    ],
    timeline: [
      {
        eventId: 'pilot-launch-pack',
        label: 'Pilot launch pack',
        status: 'completed' as const,
        detail: 'status=ready',
        artifactRef: 'artifacts/design-partner-pilot/manifest.json',
        occurredAtUtc: generatedAtUtc,
      },
    ],
    acceptanceMetrics: { privacy: 'aggregate_only_no_pii' },
    feedbackBundlePath: 'artifacts/pilot-ops/pilot_feedback_bundle.json',
    nextActions: [{ label: 'feedback-bundle', severity: 'warning' as const, target: 'Pilot Ops' }],
    blockers: [],
    warnings: ['feedback-bundle'],
  };
}

function designPartnerBeta(generatedAtUtc: string) {
  return {
    schemaVersion: 'control-plane.design-partner-beta/v1' as const,
    generatedAtUtc,
    status: 'conditional' as const,
    headline: 'Design Partner Beta Operations Candidate is conditional.',
    artifactRoot: 'artifacts/design-partner-beta',
    codeIntelligence: codeIntelligence(generatedAtUtc),
    pilotOperations: pilotOperations(generatedAtUtc),
    checks: [
      {
        itemId: 'code-intelligence',
        label: 'Code intelligence',
        status: 'conditional' as const,
        detail: 'Fallow verdict warn',
        path: 'artifacts/code-intelligence/fallow/summary.json',
        blocking: false,
      },
    ],
    blockers: [],
    warnings: ['code-intelligence'],
  };
}
