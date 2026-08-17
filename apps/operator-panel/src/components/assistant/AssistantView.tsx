import { useMemo, useState, type ReactNode } from 'react';
import { AssistantRuntimeProvider } from '@assistant-ui/react';

import type { AssistantArtifactProposalPart, AssistantArtifactRef, AssistantSessionState } from '../../assistant/assistantTypes';
import type { AssistantComposerControls } from '../../assistant/assistantTypes';
import { useImperaAssistantUiRuntime } from '../../assistant/assistantUiRuntime';
import type { AssistantModelDiscoveryState } from '../../assistant/useAssistantModels';
import type { AssistantRuntimeSettings } from '../../settings';
import type { ArtifactKind } from '../../artifact-workspace/artifactContracts';
import { assistantUiText, type UiLocale } from '../../i18n';
import { ArtifactWorkbenchShell } from '../../artifact-workspace/ui/ArtifactWorkbenchShell';
import { Card } from '../primitives/Card';
import { Icon } from '../primitives/Icon';
import { AssistantComposer } from './AssistantComposer';
import { AssistantTranscript } from './AssistantTranscript';
import { AssistantWelcome } from './AssistantWelcome';

export type AssistantViewCopy = {
  title: string;
  subtitle: string;
  welcomeTitle: string;
  badgeLabel: string;
  newChat: string;
  messageLabel: string;
  sendLabel: string;
  composerPlaceholder: string;
  readOnlyByDefault: string;
  sensitiveDataNotice: string;
  dryRunSafe: string;
  referencedRuns: string;
  systemHealth: string;
  suggestedPromptsLabel: string;
  suggestedPrompts: string[];
  awaitingContextTitle: string;
  awaitingContextBody: string;
  noReferencedRunTitle: string;
  noReferencedRunBody: string;
  approvalLifecycle: string;
  approvalGated: string;
  approvalLifecycleBody: string;
};

export function AssistantView({
  copy,
  state,
  rightRail = null,
  workbench = null,
  workbenchAvailable = false,
  workbenchOpen = false,
  approvalDisabled = true,
  approvalDisabledReason = '',
  debugRawEnabled = false,
  runtimeSettings,
  modelDiscovery,
  locale = 'en',
  onRuntimeSettingsChange,
  onSend,
  onNewChat,
  onToggleWorkbench,
  onReviewApproval,
  onApprove,
  onReject,
  onExecute,
  onApplyProposal,
  onRegenerate,
  onOpenArtifact,
  renderInlineArtifact,
  assistantUiRuntimeEnabled = true,
  activeArtifactKind,
  onCancel,
  onOpenTerminal,
}: {
  copy: AssistantViewCopy;
  state: AssistantSessionState;
  rightRail?: ReactNode;
  workbench?: ReactNode;
  workbenchAvailable?: boolean;
  workbenchOpen?: boolean;
  approvalDisabled?: boolean;
  approvalDisabledReason?: string;
  debugRawEnabled?: boolean;
  runtimeSettings: AssistantRuntimeSettings;
  modelDiscovery?: AssistantModelDiscoveryState | null;
  locale?: UiLocale;
  onRuntimeSettingsChange: (next: Partial<AssistantRuntimeSettings>) => void;
  onSend: (
    message: string,
    runtimeSettings: AssistantRuntimeSettings,
    controls: AssistantComposerControls,
  ) => void;
  onNewChat: () => void;
  onToggleWorkbench?: () => void;
  onReviewApproval: (approvalId: string) => void;
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string) => void;
  onExecute: (approvalId: string) => void;
  onApplyProposal?: (proposal: AssistantArtifactProposalPart) => void;
  onRegenerate: (turnId: string) => void;
  onOpenArtifact?: (artifactId: string) => void;
  renderInlineArtifact?: (artifact: AssistantArtifactRef) => ReactNode;
  assistantUiRuntimeEnabled?: boolean;
  activeArtifactKind?: ArtifactKind;
  onCancel: () => void;
  onOpenTerminal?: () => void;
}) {
  const [contextRailOpen, setContextRailOpen] = useState(false);
  const [assistantSearchQuery, setAssistantSearchQuery] = useState('');
  const [assistantNotificationsOpen, setAssistantNotificationsOpen] = useState(false);
  const text = assistantUiText[locale];
  const currentTurnRunning = state.status === 'starting' || state.status === 'streaming';
  const surfaceState =
    state.status === 'awaiting_approval' ? 'approval' : state.turns.length > 0 ? 'transcript' : 'welcome';
  const normalizedSearchQuery = assistantSearchQuery.trim().toLowerCase();
  const searchResults = useMemo(() => {
    if (!normalizedSearchQuery) {
      return [];
    }
    return state.turns
      .flatMap((turn) => [
        {
          id: `${turn.id}-user`,
          label: locale === 'tr' ? 'Kullanıcı mesajı' : 'User message',
          text: turn.userMessage.text,
        },
        {
          id: `${turn.id}-assistant`,
          label: locale === 'tr' ? 'Asistan yanıtı' : 'Assistant response',
          text: turn.assistantMessage.text,
        },
      ])
      .filter((item) => item.text.toLowerCase().includes(normalizedSearchQuery))
      .slice(0, 5);
  }, [locale, normalizedSearchQuery, state.turns]);
  const assistantNotifications = useMemo(() => {
    const latestTurn = state.turns.at(-1);
    return [
      {
        id: 'assistant-status',
        title: locale === 'tr' ? 'Asistan durumu' : 'Assistant status',
        body: state.status,
      },
      latestTurn
        ? {
            id: 'assistant-latest-turn',
            title: locale === 'tr' ? 'Son yanıt' : 'Latest response',
            body: latestTurn.status,
          }
        : null,
      state.pendingApprovalId
        ? {
            id: 'assistant-approval',
            title: locale === 'tr' ? 'Onay bekliyor' : 'Approval pending',
            body: state.pendingApprovalId,
          }
        : null,
      state.selectedRunIds.length > 0
        ? {
            id: 'assistant-run-context',
            title: locale === 'tr' ? 'Run bağlamı' : 'Run context',
            body: state.selectedRunIds[0],
          }
        : null,
    ].filter((item): item is { id: string; title: string; body: string } => Boolean(item));
  }, [locale, state.pendingApprovalId, state.selectedRunIds, state.status, state.turns]);
  const assistantRuntime = useImperaAssistantUiRuntime({
    state,
    onNew: (message) =>
      onSend(message, runtimeSettings, { contextAttachmentKinds: [], toolIntents: [] }),
    onCancel,
    onRegenerate,
  });

  const surface = (
    <section
        className={`assistant-surface assistant-surface-${surfaceState}`}
        aria-labelledby="assistant-title"
        data-testid="page-primary-region"
      >
      <header className="assistant-top-chrome">
        <div className="assistant-context-switcher" aria-label="Assistant workspace context">
          <div className="assistant-top-select assistant-top-select-wide">
            <span>{text.workspace}</span>
            <strong>
              Production Control Plane <Icon name="chevron" />
            </strong>
          </div>
          <div className="assistant-top-select">
            <span>{text.policyMode}</span>
            <strong className="assistant-warning-value">
              <Icon name="shield" /> {text.guarded} <Icon name="chevron" />
            </strong>
          </div>
          <div className="assistant-top-select">
            <span>{text.runtimeStatus}</span>
            <strong className="assistant-success-value">{text.healthy}</strong>
          </div>
        </div>
        <div className="assistant-top-actions">
          <div className="assistant-search-wrap">
            <label className="assistant-search">
              <Icon name="logs" />
              <input
                aria-label={text.search}
                placeholder={text.search}
                value={assistantSearchQuery}
                onChange={(event) => setAssistantSearchQuery(event.target.value)}
              />
              <kbd>{normalizedSearchQuery ? searchResults.length : '⌘K'}</kbd>
            </label>
            {normalizedSearchQuery ? (
              <div className="assistant-search-results" role="status" aria-label={text.search}>
                {searchResults.length > 0 ? (
                  searchResults.map((result) => (
                    <article key={result.id}>
                      <span>{result.label}</span>
                      <p>{result.text}</p>
                    </article>
                  ))
                ) : (
                  <p>{locale === 'tr' ? 'Eşleşme yok' : 'No matches'}</p>
                )}
              </div>
            ) : null}
          </div>
          {workbenchAvailable && onToggleWorkbench ? (
            <button
              type="button"
              aria-label={
                workbenchOpen
                  ? locale === 'tr'
                    ? 'Çalışma alanını kapat'
                    : 'Close workbench'
                  : locale === 'tr'
                    ? 'Çalışma alanını aç'
                    : 'Open workbench'
              }
              aria-expanded={workbenchOpen}
              className={workbenchOpen ? 'assistant-context-toggle assistant-toggle-active' : 'assistant-context-toggle'}
              title={locale === 'tr' ? 'Çalışma alanı' : 'Workbench'}
              onClick={onToggleWorkbench}
            >
              <Icon name="grid" />
            </button>
          ) : null}
          {onOpenTerminal ? (
            <button type="button" aria-label={text.terminal} title={text.terminal} onClick={onOpenTerminal}>
              <Icon name="terminal" />
            </button>
          ) : null}
          <div className="assistant-action-popover">
            <button
              type="button"
              aria-label={text.notifications}
              aria-expanded={assistantNotificationsOpen}
              className="assistant-notification-button"
              title={text.notifications}
              onClick={() => setAssistantNotificationsOpen((value) => !value)}
            >
              <Icon name="bell" />
              <span aria-hidden="true" />
            </button>
            {assistantNotificationsOpen ? (
              <div className="assistant-notification-popover" role="status" aria-label={text.notifications}>
                {assistantNotifications.map((item) => (
                  <article key={item.id}>
                    <span>{item.title}</span>
                    <p>{item.body}</p>
                  </article>
                ))}
              </div>
            ) : null}
          </div>
          {rightRail ? (
            <button
              type="button"
              aria-label={contextRailOpen ? text.closeAssistantContext : text.openAssistantContext}
              aria-expanded={contextRailOpen}
              className="assistant-context-toggle"
              title={text.assistantContext}
              onClick={() => setContextRailOpen((value) => !value)}
            >
              <Icon name="menu" />
            </button>
          ) : null}
        </div>
      </header>

      <div className="assistant-surface-grid">
        <ArtifactWorkbenchShell
          workbench={workbench}
          activeArtifactKind={activeArtifactKind}
          onCloseWorkbench={() => onToggleWorkbench?.()}
        >
        <div className="assistant-main-stage">
          {state.turns.length > 0 ? (
            <header className="assistant-session-header">
              <span id="assistant-title" className="sr-only">
                {copy.title}
              </span>
              <div className="assistant-session-actions">
                <button type="button" className="assistant-session-icon-button" aria-label={copy.newChat} title={copy.newChat} onClick={onNewChat}>
                  <Icon name="edit" />
                </button>
                <button
                  type="button"
                  className="assistant-session-icon-button"
                  aria-label={text.moreActions}
                  disabled
                  title={text.moreActionsUnavailable}
                >
                  ···
                </button>
              </div>
            </header>
          ) : (
            <span id="assistant-title" className="sr-only">
              {copy.title}
            </span>
          )}

          {state.turns.length === 0 ? (
            <AssistantWelcome
              title={copy.welcomeTitle}
              subtitle={copy.subtitle}
              badgeLabel={copy.badgeLabel}
              readOnlyByDefault={copy.readOnlyByDefault}
            />
          ) : (
            <AssistantTranscript
              turns={state.turns}
              approvalDisabled={approvalDisabled}
              approvalDisabledReason={approvalDisabledReason}
              emptyRunLabel={copy.noReferencedRunTitle}
              debugRawEnabled={debugRawEnabled}
              locale={locale}
              onReviewApproval={onReviewApproval}
              onApprove={onApprove}
              onReject={onReject}
              onExecute={onExecute}
              onApplyProposal={onApplyProposal}
              onRegenerate={onRegenerate}
              onOpenArtifact={onOpenArtifact}
              renderInlineArtifact={renderInlineArtifact}
              assistantUiRuntimeEnabled={assistantUiRuntimeEnabled}
            />
          )}

          {state.turns.length === 0 ? (
            <div className="assistant-context-grid" aria-label={text.assistantContext}>
              <Card className="assistant-context-card">
                <span className="assistant-card-label">{copy.systemHealth}</span>
                <strong>{copy.awaitingContextTitle}</strong>
                <p>{copy.awaitingContextBody}</p>
              </Card>
              <Card className="assistant-context-card">
                <span className="assistant-card-label">{copy.referencedRuns}</span>
                <strong>{copy.noReferencedRunTitle}</strong>
                <p>{copy.noReferencedRunBody}</p>
              </Card>
              <Card className="assistant-context-card">
                <span className="assistant-card-label">{copy.approvalLifecycle}</span>
                <strong>{copy.approvalGated}</strong>
                <p>{copy.approvalLifecycleBody}</p>
              </Card>
            </div>
          ) : null}

          <AssistantComposer
            label={copy.messageLabel}
            placeholder={copy.composerPlaceholder}
            sendLabel={copy.sendLabel}
            disabled={currentTurnRunning}
            runtimeSettings={runtimeSettings}
            modelDiscovery={modelDiscovery}
            locale={locale}
            onRuntimeSettingsChange={onRuntimeSettingsChange}
            onSend={onSend}
            onCancel={currentTurnRunning ? onCancel : undefined}
          />
        </div>
        </ArtifactWorkbenchShell>

        {rightRail ? (
          <>
            <div
              className={contextRailOpen ? 'assistant-context-drawer assistant-context-drawer-open' : 'assistant-context-drawer'}
              aria-hidden={!contextRailOpen}
            >
              <button
                type="button"
                className="assistant-context-backdrop"
                aria-label={text.closeAssistantContext}
                onClick={() => setContextRailOpen(false)}
              />
              <div className="assistant-context-panel" role="complementary" aria-label={text.assistantContextPanel}>
                <div className="assistant-context-panel-head">
                  <span>{text.assistantContext}</span>
                  <button type="button" aria-label={text.closeAssistantContext} onClick={() => setContextRailOpen(false)}>
                    <Icon name="close" />
                  </button>
                </div>
                {rightRail}
              </div>
            </div>
            <div className="assistant-context-rail-desktop">{rightRail}</div>
          </>
        ) : null}
      </div>
    </section>
  );
  return assistantUiRuntimeEnabled ? (
    <AssistantRuntimeProvider runtime={assistantRuntime}>{surface}</AssistantRuntimeProvider>
  ) : surface;
}
