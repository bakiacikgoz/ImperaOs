import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { getAssistantFixture } from '../../assistant/assistantFixtures';
import { DEFAULT_ASSISTANT_RUNTIME_SETTINGS } from '../../settings';
import { AssistantView, type AssistantViewCopy } from './AssistantView';

const copy: AssistantViewCopy = {
  title: 'ImperaOS Assistant',
  subtitle: 'Ask about systems, runs, logs, policies, approvals, and artifacts.',
  welcomeTitle: 'Welcome to ImperaOS Assistant',
  badgeLabel: 'Governed assistant',
  newChat: 'New Chat',
  messageLabel: 'Message',
  sendLabel: 'Send',
  composerPlaceholder: 'Ask about systems, runs, policies, or logs...',
  readOnlyByDefault: 'Read-only by default',
  sensitiveDataNotice: 'Sensitive data stays in your environment',
  dryRunSafe: 'Dry-run preview before execution',
  referencedRuns: 'Referenced runs',
  systemHealth: 'System health',
  suggestedPromptsLabel: 'Suggested prompts',
  suggestedPrompts: [
    'Summarize recent errors',
    'Draft a remediation plan',
    'Review policy changes',
    'Analyze a run',
  ],
  awaitingContextTitle: 'Awaiting context',
  awaitingContextBody: 'Runtime health and contract state will stay visible before assistant actions are proposed.',
  noReferencedRunTitle: 'No referenced run',
  noReferencedRunBody: 'Run and artifact references will remain read-only until later integration phases.',
  approvalLifecycle: 'Approval lifecycle',
  approvalGated: 'Approval-gated',
  approvalLifecycleBody: 'Proposed actions will reuse the existing pending, approved, executed, and consumed flow.',
};

const requiredActionProps = {
  runtimeSettings: DEFAULT_ASSISTANT_RUNTIME_SETTINGS,
  onRuntimeSettingsChange: () => undefined,
  onSend: () => undefined,
  onNewChat: () => undefined,
  onReviewApproval: () => undefined,
  onApprove: () => undefined,
  onReject: () => undefined,
  onExecute: () => undefined,
  onRegenerate: () => undefined,
  onCancel: () => undefined,
};

describe('AssistantView', () => {
  it('renders the welcome state with safety context', () => {
    const html = renderToStaticMarkup(
      <AssistantView copy={copy} state={getAssistantFixture('welcome')} {...requiredActionProps} />,
    );

    expect(html).toContain('Welcome to ImperaOS Assistant');
    expect(html).toContain('Read-only by default');
    expect(html).toContain('Referenced runs');
    expect(html).not.toContain('Summarize recent errors');
  });

  it('renders the running state with transcript and referenced run context', () => {
    const html = renderToStaticMarkup(
      <AssistantView copy={copy} state={getAssistantFixture('running')} {...requiredActionProps} />,
    );

    expect(html).toContain('Son run hatasını özetle');
    expect(html).toContain('The selected run is blocked by an approval gate.');
    expect(html).toContain('job-ui-preview-cu-1');
  });

  it('exposes committed workspace artifacts as open actions', () => {
    const state = getAssistantFixture('running');
    const html = renderToStaticMarkup(
      <AssistantView
        copy={copy}
        state={{
          ...state,
          turns: state.turns.map((turn, index) =>
            index === state.turns.length - 1
              ? {
                  ...turn,
                  assistantMessage: {
                    ...turn.assistantMessage,
                    referencedArtifacts: [
                      {
                        name: 'Project brief',
                        artifactId: 'artifact-project-brief',
                        kind: 'document',
                        openable: true,
                        summary: 'Committed document artifact',
                      },
                    ],
                  },
                }
              : turn,
          ),
        }}
        onOpenArtifact={() => undefined}
        {...requiredActionProps}
      />,
    );

    expect(html).toContain('aria-label="Open Project brief"');
  });

  it('renders the approval-required state with guarded approval actions', () => {
    const html = renderToStaticMarkup(
      <AssistantView
        copy={copy}
        state={getAssistantFixture('approval_required')}
        approvalDisabled
        approvalDisabledReason="Set operator id to continue"
        {...requiredActionProps}
      />,
    );

    expect(html).toContain('Approval required');
    expect(html).toContain('apr_20260308_device_action');
    expect(html).toContain('Set operator id to continue');
    expect(html).toContain('disabled=""');
  });
});
