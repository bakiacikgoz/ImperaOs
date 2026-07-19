import { describe, expect, it } from 'vitest';

import {
  buildWorkspaceSnapshot,
  countTimelineByTone,
  deriveWorkspaceRuntimeState,
  listAttachmentLabels,
  readWorkspaceProgress,
  selectRecentRuns,
} from './workspace';

describe('workspace snapshot', () => {
  it('derives blocked state when drift is present', () => {
    const snapshot = buildWorkspaceSnapshot({
      runStatus: {
        job: {
          request: 'Inspect queue health',
          status: 'blocked',
        },
      },
      events: [
        { event: 'team_start', timestamp: '2026-03-08T09:10:00Z', phase: 'team', data: { request: 'Inspect queue health' } },
        { event: 'team.resume.snapshot_drift', timestamp: '2026-03-08T09:13:09Z', phase: 'team', data: { reason_code: 'STALE_APPROVAL_SNAPSHOT' } },
      ],
      pendingApprovals: [],
      linkedApprovals: [],
      artifactsByName: {},
    });

    expect(snapshot.stage).toBe('blocked');
    expect(snapshot.blockedReason).toBe('snapshot_drift');
    expect(countTimelineByTone(snapshot.timeline, 'warning')).toBe(1);
  });

  it('extracts live surface and approval context from linked approvals', () => {
    const snapshot = buildWorkspaceSnapshot({
      runStatus: {
        job: {
          request: 'Update the queue',
          status: 'blocked',
        },
      },
      events: [{ event: 'approval_requested', timestamp: '2026-03-08T09:11:05Z', phase: 'approval', data: { target: 'device_action' } }],
      pendingApprovals: [],
      linkedApprovals: [
        {
          approval_id: 'apr_1',
          status: 'pending',
          snapshot: {
            app_identity: 'browser:safari',
            window_identity: 'tab-17',
            target_ref: 'queue-row-17',
            risk_class: 'medium',
            selector_context: { selector: "[data-row-id='17']" },
            action_plan: { expected_effect: 'Update queue status.' },
          },
        },
      ],
      artifactsByName: {
        'status.json': {
          payload: {
            job_dir: '/tmp/run_1',
          },
        },
      },
    });

    expect(snapshot.stage).toBe('waiting_approval');
    expect(snapshot.liveSurface).toEqual({
      appIdentity: 'browser:safari',
      windowIdentity: 'tab-17',
      targetRef: 'queue-row-17',
      selector: "[data-row-id='17']",
      riskClass: 'medium',
      expectedEffect: 'Update queue status.',
      approvalId: 'apr_1',
    });
    expect(snapshot.artifacts[0]).toEqual({
      name: 'status.json',
      available: true,
      summary: '/tmp/run_1',
    });
  });

  it('reports progress and recent run selections', () => {
    const snapshot = buildWorkspaceSnapshot({
      runStatus: {
        job: {
          request: 'Inspect queue',
          status: 'running',
        },
      },
      events: [{ event: 'task_started', timestamp: '2026-03-08T09:10:15Z', phase: 'task', task_id: 'task-02', data: {} }],
      pendingApprovals: [],
      linkedApprovals: [],
      artifactsByName: {},
    });

    expect(readWorkspaceProgress(snapshot)).toBeGreaterThan(50);
    expect(listAttachmentLabels('run_1', 'examples/team/restricted_pilot.yaml', '/tmp/root')).toEqual([
      'Spec: examples/team/restricted_pilot.yaml',
      'Run: run_1',
      'Root: /tmp/root',
    ]);
    expect(
      selectRecentRuns([
        { job_id: 'run_1' },
        null,
        { job_id: 'run_2' },
      ]),
    ).toEqual([{ job_id: 'run_1' }, { job_id: 'run_2' }]);
  });

  it('maps computer-use world model and execution events into the workspace view', () => {
    const snapshot = buildWorkspaceSnapshot({
      runStatus: {
        job: {
          request: 'Open form and fill it',
          status: 'running',
          team_id: 'imperaos-computer-use',
        },
        computer_use: {
          lifecycle_state: 'running',
          stage: 'verify',
          current_url: 'https://preview.imperaos.local/form',
          active_app: 'browser:safari',
          active_window: 'safari:ImperaOS Preview Form',
          last_verified_effect: 'Open https://preview.imperaos.local/form.',
          world_model: {
            active_application_identity: 'browser:safari',
            current_url: 'https://preview.imperaos.local/form',
            active_window: {
              window_identity: 'safari:ImperaOS Preview Form',
              app_identity: 'browser:safari',
              surface_kind: 'browser',
              focused: true,
            },
            visible_target_set: ['#name', '#submit'],
            last_verified_effect: 'Open https://preview.imperaos.local/form.',
          },
        },
      },
      events: [
        {
          event: 'action_started',
          timestamp: '2026-03-08T09:10:03Z',
          phase: 'computer_use',
          data: { action_id: 'type_text', selector: '#name' },
        },
        {
          event: 'action_verified',
          timestamp: '2026-03-08T09:10:04Z',
          phase: 'computer_use',
          data: { action_id: 'type_text', verification: { verified: true } },
        },
      ],
      pendingApprovals: [],
      linkedApprovals: [],
      artifactsByName: {
        'status.json': {
          payload: {
            computer_use: {
              artifacts: {
                download_file: { download_path: '/tmp/report.csv' },
              },
            },
          },
        },
      },
    });

    expect(snapshot.stage).toBe('verifying');
    expect(snapshot.liveSurface?.appIdentity).toBe('browser:safari');
    expect(snapshot.liveSurface?.selector).toBe('#name');
    expect(snapshot.transcript.some((item) => item.title === 'Current URL')).toBe(true);
    expect(snapshot.timeline[1]?.tone).toBe('success');
    expect(snapshot.artifacts[0]?.summary).toContain('runtime artifacts');
  });

  it('keeps awaiting approval distinct from paused and disables resume until approval is ready', () => {
    const snapshot = buildWorkspaceSnapshot({
      runStatus: {
        job: {
          request: 'Submit the preview form',
          status: 'blocked',
          team_id: 'imperaos-computer-use',
        },
        computer_use: {
          session_state: 'awaiting_approval',
          lifecycle_state: 'awaiting_approval',
          stage: 'require_approval',
          pending_approval_id: 'apr_1',
          resume_allowed: false,
        },
      },
      sessionState: {
        registry: {
          state: 'awaiting_approval',
        },
      },
      events: [
        {
          event: 'approval_required',
          timestamp: '2026-03-08T09:10:05Z',
          phase: 'computer_use',
          data: { approval_id: 'apr_1', action_id: 'submit' },
        },
      ],
      pendingApprovals: [{ approval_id: 'apr_1', status: 'pending' }],
      linkedApprovals: [],
      artifactsByName: {},
    });

    expect(snapshot.stage).toBe('waiting_approval');
    expect(snapshot.runtimeState.displayState).toBe('awaiting_approval');
    expect(snapshot.runtimeState.canPause).toBe(false);
    expect(snapshot.runtimeState.canResume).toBe(false);
    expect(snapshot.runtimeState.canStop).toBe(true);
  });

  it('separates operator stop from generic failure semantics', () => {
    const snapshot = buildWorkspaceSnapshot({
      runStatus: {
        job: {
          request: 'Stop after checkpoint',
          status: 'failed',
          team_id: 'imperaos-computer-use',
        },
        computer_use: {
          session_state: 'stopped',
          lifecycle_state: 'stopped',
          stopped_by_user: true,
          last_control_result: {
            command_type: 'stop',
            outcome: 'applied',
          },
        },
      },
      events: [],
      pendingApprovals: [],
      linkedApprovals: [],
      artifactsByName: {},
    });

    expect(snapshot.runtimeState.displayState).toBe('stopped');
    expect(snapshot.blockedReason).toBe('stopped_by_user');
  });

  it('renders control command rejection in timeline order', () => {
    const snapshot = buildWorkspaceSnapshot({
      runStatus: {
        job: {
          request: 'Resume after approval',
          status: 'blocked',
          team_id: 'imperaos-computer-use',
        },
        computer_use: {
          session_state: 'awaiting_approval',
          lifecycle_state: 'awaiting_approval',
        },
      },
      events: [
        {
          event: 'computer_use.control_command_received',
          timestamp: '2026-03-08T09:10:08Z',
          phase: 'computer_use',
          data: {
            command: { command_type: 'resume' },
            session_state: 'awaiting_approval',
          },
        },
        {
          event: 'computer_use.control_command_rejected',
          timestamp: '2026-03-08T09:10:09Z',
          phase: 'computer_use',
          data: {
            command: { command_type: 'resume' },
            result: { reason: 'approval_not_executed' },
          },
        },
      ],
      pendingApprovals: [],
      linkedApprovals: [],
      artifactsByName: {},
    });

    expect(snapshot.timeline.map((item) => item.summary)).toEqual([
      'Resume command received.',
      'Resume was rejected: approval_not_executed.',
    ]);
    expect(snapshot.timeline[1]?.tone).toBe('warning');
  });

  it('maps recovery snapshots into resumable and non-resumable UI states', () => {
    const recovered = deriveWorkspaceRuntimeState({
      runStatus: {
        job: { status: 'blocked' },
        computer_use: {
          session_state: 'paused',
        },
      },
      sessionState: {
        registry: {},
        recovery: {
          recoverable_state: 'paused',
          resume_allowed: true,
          control_history: [{ command_type: 'pause' }],
        },
      },
      pendingApprovals: [],
      linkedApprovals: [],
    });
    const nonResumable = deriveWorkspaceRuntimeState({
      runStatus: {
        job: { status: 'failed' },
        computer_use: {
          session_state: 'failed',
        },
      },
      sessionState: {
        registry: {},
        recovery: {
          recoverable_state: 'failed',
          resume_allowed: false,
          control_history: [{ command_type: 'stop' }],
        },
      },
      pendingApprovals: [],
      linkedApprovals: [],
    });

    expect(recovered.displayState).toBe('recovered');
    expect(recovered.canResume).toBe(false);
    expect(recovered.controlHistoryCount).toBe(1);
    expect(nonResumable.displayState).toBe('non_resumable');
    expect(nonResumable.recoverySummary).toContain('cannot continue');
  });

  it('maps vision-first action and verifier state without raw screenshot paths', () => {
    const snapshot = buildWorkspaceSnapshot({
      runStatus: {
        job: {
          request: 'Click the submit button',
          status: 'awaiting_approval',
          team_id: 'imperaos-computer-use',
        },
        computer_use: {
          status: 'awaiting_approval',
          stop_reason: 'COMPUTER_USE_APPROVAL_REQUIRED',
          redaction_report: {
            raw_screenshot_persisted_count: 0,
          },
          steps: [
            {
              step_index: 0,
              execution_status: 'approval_required',
              before_hash: 'a'.repeat(64),
              action: {
                action_id: 'click_submit_button',
                action_type: 'click',
                target_element_id: 'submit_button',
                rationale: 'The fixture submit button is visible.',
                expected_effect: 'The fixture status changes to submitted.',
                risk_class: 'medium',
                requires_approval: true,
                confidence: 0.93,
                raw_screenshot_path: '/tmp/private-screen.png',
              },
              policy_decision: {
                reason_code: 'COMPUTER_USE_APPROVAL_REQUIRED',
              },
              approval_snapshot: {
                status: 'pending',
                raw_screenshot_path: '/tmp/private-approval.png',
              },
              verification: {
                status: 'satisfied',
                reason_code: 'VISION_VERIFICATION_SATISFIED',
              },
            },
          ],
        },
      },
      events: [],
      pendingApprovals: [],
      linkedApprovals: [],
      artifactsByName: {},
    });

    expect(snapshot.visionRuntime).toMatchObject({
      currentStepStatus: 'approval_required',
      actionType: 'click',
      actionId: 'click_submit_button',
      targetElementId: 'submit_button',
      riskClass: 'medium',
      requiresApproval: true,
      approvalState: 'pending',
      policyDecision: 'COMPUTER_USE_APPROVAL_REQUIRED',
      verificationStatus: 'satisfied',
      verificationReason: 'VISION_VERIFICATION_SATISFIED',
      stopReason: 'COMPUTER_USE_APPROVAL_REQUIRED',
      rawScreenshotPathIgnored: true,
    });
    expect(JSON.stringify(snapshot.visionRuntime)).not.toContain('/tmp/private-screen.png');
  });
});
