import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { ThreadPrimitive, useAuiState } from '@assistant-ui/react';

import type { AssistantArtifactProposalPart, AssistantArtifactRef, AssistantTurn } from '../../assistant/assistantTypes';
import type { UiLocale } from '../../i18n';
import { AssistantMessage } from './AssistantMessage';

const LATEST_THRESHOLD_PX = 96;

interface RuntimeTranscriptContextValue {
  turns: AssistantTurn[];
  approvalDisabled: boolean;
  approvalDisabledReason: string;
  emptyRunLabel: string;
  debugRawEnabled: boolean;
  locale: UiLocale;
  onReviewApproval: (approvalId: string) => void;
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string) => void;
  onExecute: (approvalId: string) => void;
  onApplyProposal?: (proposal: AssistantArtifactProposalPart) => void;
  onRegenerate: (turnId: string) => void;
  onOpenArtifact?: (artifactId: string) => void;
  renderInlineArtifact?: (artifact: AssistantArtifactRef) => ReactNode;
}

const RuntimeTranscriptContext = createContext<RuntimeTranscriptContextValue | null>(null);

function RuntimeTurnMessage() {
  const context = useContext(RuntimeTranscriptContext);
  const messageId = useAuiState((state) => state.message.id);
  if (!context || !messageId.endsWith('-assistant')) return null;
  const turn = context.turns.find((candidate) => candidate.assistantMessage.id === messageId);
  if (!turn) return null;
  return (
    <div data-assistant-turn="true">
      <AssistantMessage
        turn={turn}
        approvalDisabled={context.approvalDisabled}
        approvalDisabledReason={context.approvalDisabledReason}
        emptyRunLabel={context.emptyRunLabel}
        debugRawEnabled={context.debugRawEnabled}
        locale={context.locale}
        onReviewApproval={context.onReviewApproval}
        onApprove={context.onApprove}
        onReject={context.onReject}
        onExecute={context.onExecute}
        onApplyProposal={context.onApplyProposal}
        onRegenerate={context.onRegenerate}
        onOpenArtifact={context.onOpenArtifact}
        renderInlineArtifact={context.renderInlineArtifact}
      />
    </div>
  );
}

function bottomGap(element: HTMLElement): number {
  return element.scrollHeight - element.clientHeight - element.scrollTop;
}

export function AssistantTranscript({
  turns,
  approvalDisabled,
  approvalDisabledReason,
  emptyRunLabel,
  debugRawEnabled,
  locale = 'en',
  onReviewApproval,
  onApprove,
  onReject,
  onExecute,
  onApplyProposal,
  onRegenerate,
  onOpenArtifact,
  renderInlineArtifact,
  assistantUiRuntimeEnabled = true,
}: {
  turns: AssistantTurn[];
  approvalDisabled: boolean;
  approvalDisabledReason: string;
  emptyRunLabel: string;
  debugRawEnabled: boolean;
  locale?: UiLocale;
  onReviewApproval: (approvalId: string) => void;
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string) => void;
  onExecute: (approvalId: string) => void;
  onApplyProposal?: (proposal: AssistantArtifactProposalPart) => void;
  onRegenerate: (turnId: string) => void;
  onOpenArtifact?: (artifactId: string) => void;
  renderInlineArtifact?: (artifact: AssistantArtifactRef) => ReactNode;
  assistantUiRuntimeEnabled?: boolean;
}) {
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const isAtLatestRef = useRef(true);
  const previousLastTurnIdRef = useRef('');
  const userNavigatedTranscriptRef = useRef(false);
  const [isAtLatest, setIsAtLatest] = useState(true);
  const runtimeContext: RuntimeTranscriptContextValue = {
    turns,
    approvalDisabled,
    approvalDisabledReason,
    emptyRunLabel,
    debugRawEnabled,
    locale,
    onReviewApproval,
    onApprove,
    onReject,
    onExecute,
    onApplyProposal,
    onRegenerate,
    onOpenArtifact,
    renderInlineArtifact,
  };
  const lastTurnId = turns.at(-1)?.id ?? '';
  const transcriptContentKey = useMemo(
    () =>
      turns
        .map((turn) =>
          [
            turn.id,
            turn.status,
            turn.userMessage.text.length,
            turn.assistantMessage.text.length,
            turn.assistantMessage.referencedRuns.length,
            turn.assistantMessage.referencedArtifacts.length,
            turn.assistantMessage.warning ?? '',
            turn.assistantMessage.error?.code ?? '',
            turn.assistantMessage.approval?.approvalId ?? '',
            turn.assistantMessage.proposedAction?.id ?? '',
          ].join(':'),
        )
        .join('|'),
    [turns],
  );

  const updateLatestState = useCallback(() => {
    const transcript = transcriptRef.current;
    if (!transcript) {
      return;
    }
    const next = bottomGap(transcript) <= LATEST_THRESHOLD_PX;
    if (!next && !userNavigatedTranscriptRef.current) {
      isAtLatestRef.current = true;
      setIsAtLatest(true);
      return;
    }
    if (next) {
      userNavigatedTranscriptRef.current = false;
    }
    isAtLatestRef.current = next;
    setIsAtLatest(next);
  }, []);

  const scrollToLatest = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const transcript = transcriptRef.current;
    if (!transcript) {
      return;
    }
    transcript.scrollTo({ top: transcript.scrollHeight, behavior });
    userNavigatedTranscriptRef.current = false;
    isAtLatestRef.current = true;
    setIsAtLatest(true);
  }, []);

  useEffect(() => {
    const transcript = transcriptRef.current;
    if (!transcript) {
      return undefined;
    }
    const markUserNavigation = () => {
      userNavigatedTranscriptRef.current = true;
    };
    transcript.addEventListener('scroll', updateLatestState, { passive: true });
    transcript.addEventListener('wheel', markUserNavigation, { passive: true });
    transcript.addEventListener('touchstart', markUserNavigation, { passive: true });
    transcript.addEventListener('pointerdown', markUserNavigation, { passive: true });
    transcript.addEventListener('keydown', markUserNavigation);
    updateLatestState();
    return () => {
      transcript.removeEventListener('scroll', updateLatestState);
      transcript.removeEventListener('wheel', markUserNavigation);
      transcript.removeEventListener('touchstart', markUserNavigation);
      transcript.removeEventListener('pointerdown', markUserNavigation);
      transcript.removeEventListener('keydown', markUserNavigation);
    };
  }, [updateLatestState]);

  useLayoutEffect(() => {
    const lastTurnChanged = previousLastTurnIdRef.current !== lastTurnId;
    previousLastTurnIdRef.current = lastTurnId;
    if (!lastTurnId) {
      return;
    }
    if (lastTurnChanged) {
      if (userNavigatedTranscriptRef.current && !isAtLatestRef.current) {
        updateLatestState();
        return;
      }
      scrollToLatest('auto');
      return;
    }
    if (isAtLatestRef.current) {
      scrollToLatest('auto');
      return;
    }
    updateLatestState();
  }, [lastTurnId, scrollToLatest, transcriptContentKey, updateLatestState]);

  useEffect(() => {
    const transcript = transcriptRef.current;
    if (!transcript || typeof ResizeObserver === 'undefined') {
      return undefined;
    }
    const observer = new ResizeObserver(() => {
      if (isAtLatestRef.current) {
        scrollToLatest('auto');
      } else {
        updateLatestState();
      }
    });
    observer.observe(transcript);
    const lastTurn = transcript.querySelector<HTMLElement>('[data-assistant-turn="true"]:last-child');
    if (lastTurn) {
      observer.observe(lastTurn);
    }
    return () => observer.disconnect();
  }, [lastTurnId, scrollToLatest, updateLatestState]);

  return (
    <div className="assistant-transcript-shell">
      <div className="assistant-transcript" role="log" aria-live="polite" ref={transcriptRef}>
        {assistantUiRuntimeEnabled ? (
          <RuntimeTranscriptContext.Provider value={runtimeContext}>
            <ThreadPrimitive.Messages components={{ Message: RuntimeTurnMessage }} />
          </RuntimeTranscriptContext.Provider>
        ) : turns.map((turn) => (
          <div key={turn.id} data-assistant-turn="true">
            <AssistantMessage
              turn={turn}
              approvalDisabled={approvalDisabled}
              approvalDisabledReason={approvalDisabledReason}
              emptyRunLabel={emptyRunLabel}
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
            />
          </div>
        ))}
      </div>
      {!isAtLatest ? (
        <button type="button" className="assistant-jump-latest" onClick={() => scrollToLatest()}>
          {locale === 'tr' ? 'En yeniye git' : 'Jump to latest'}
        </button>
      ) : null}
    </div>
  );
}
