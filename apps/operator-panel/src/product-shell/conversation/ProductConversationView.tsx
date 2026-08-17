import {
  Copy,
  ExternalLink,
  FileText,
  RefreshCw,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';
import { useEffect, useState } from 'react';

import type { AssistantSessionState } from '../../assistant/assistantTypes';
import { productWorkspaceClient, type ProductTaskLink } from '../adapters/productWorkspaceClient';
import { transientConversationTurns, type StoredMessage } from './conversationState';

type ProductConversationViewProps = {
  state: AssistantSessionState;
  taskId: string;
  refreshToken?: number;
  onOpenArtifacts?: (artifactId?: string) => void;
  onOpenApproval?: (approvalId: string) => void;
  onRegenerate?: (turnId: string) => void;
};

function copyMessage(body: string) {
  void globalThis.navigator?.clipboard?.writeText(body);
}

function MessageFeedback({
  body,
  onRegenerate,
}: {
  body: string;
  onRegenerate?: () => void;
}) {
  return (
    <div className="message-feedback">
      <button type="button" title="Copy" onClick={() => copyMessage(body)}><Copy size={15} /></button>
      {onRegenerate ? <button type="button" title="Regenerate" onClick={onRegenerate}><RefreshCw size={15} /></button> : null}
      <button type="button" title="Like" disabled data-disabled-reason="ASSISTANT_FEEDBACK_CAPABILITY_UNAVAILABLE"><ThumbsUp size={15} /></button>
      <button type="button" title="Dislike" disabled data-disabled-reason="ASSISTANT_FEEDBACK_CAPABILITY_UNAVAILABLE"><ThumbsDown size={15} /></button>
    </div>
  );
}

export function ProductConversationView({
  state,
  taskId,
  refreshToken = 0,
  onOpenArtifacts,
  onOpenApproval,
  onRegenerate,
}: ProductConversationViewProps) {
  const [stored, setStored] = useState<StoredMessage[]>([]);
  const [links, setLinks] = useState<ProductTaskLink[]>([]);
  const [loadError, setLoadError] = useState('');
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    setLoadError('');
    void Promise.all([productWorkspaceClient.listMessages(taskId), productWorkspaceClient.listLinks(taskId)])
      .then(([{ messages }, { links: nextLinks }]) => {
        setStored(messages);
        setLinks(nextLinks);
      })
      .catch((cause) => {
        setLoadError(cause instanceof Error ? cause.message : 'Could not load the durable conversation.');
      });
  }, [refreshToken, retryToken, taskId]);

  const transient = transientConversationTurns(state, stored);
  const empty = !loadError && !state.turns.length && !stored.length;

  return (
    <section className="conversation-view" aria-label="Assistant conversation">
      <div className="conversation-inner">
        {loadError ? (
          <section className="conversation-empty" role="alert">
            <h2>Conversation unavailable</h2>
            <p>{loadError}</p>
            <button type="button" onClick={() => setRetryToken((current) => current + 1)}>Retry durable conversation</button>
          </section>
        ) : null}
        {empty ? (
          <section className="conversation-empty ps-empty">
            <h2>Start governed work</h2>
            <p>ImperaOS will plan, enforce policy, and keep a trace of the run.</p>
          </section>
        ) : null}

        {stored.map((message) => (
          message.role === 'user' ? (
            <article className="user-message" key={message.messageId}>
              <p>{message.body}</p>
            </article>
          ) : (
            <div className="assistant-message-block" key={message.messageId}>
              <article className="completion-message">
                <p>{message.body}</p>
              </article>
              <MessageFeedback body={message.body} />
            </div>
          )
        ))}

        {transient.map((turn) => {
          const sourceTurn = state.turns.find((candidate) => candidate.id === turn.id);
          const approval = sourceTurn?.assistantMessage.approval;
          const isWorking = sourceTurn?.status === 'streaming' || sourceTurn?.status === 'starting';
          return (
            <div className="assistant-turn" key={turn.id}>
              {turn.user ? <article className="user-message"><p>{turn.user}</p></article> : null}
              {turn.status ? (
                <div className="conversation-session-divider">
                  <span>{turn.status}</span>
                </div>
              ) : null}
              {isWorking ? (
                <section className="assistant-working" aria-live="polite" aria-label="Assistant is working">
                  <div className="assistant-working-header">
                    <span className="assistant-working-orb" aria-hidden="true" />
                    <span>{turn.status || 'Working'}</span>
                  </div>
                  <div className="assistant-working-divider" aria-hidden="true" />
                  {turn.assistant ? <p className="assistant-working-copy">{turn.assistant}</p> : null}
                </section>
              ) : turn.assistant ? (
                <article className="completion-message"><p>{turn.assistant}</p></article>
              ) : null}
              {(turn.assistant || turn.user) ? (
                <>
                  <div className="conversation-actions">
                    {approval && onOpenApproval ? (
                      <button type="button" onClick={() => onOpenApproval(approval.approvalId)}>
                        Open approval
                      </button>
                    ) : null}
                    {turn.assistant ? (
                      <button
                        type="button"
                        disabled
                        title="No governed feedback sink is registered for assistant turns."
                        data-disabled-reason="ASSISTANT_FEEDBACK_CAPABILITY_UNAVAILABLE"
                      >
                        Feedback unavailable
                      </button>
                    ) : null}
                  </div>
                  <MessageFeedback
                    body={turn.assistant ?? turn.user ?? ''}
                    onRegenerate={turn.assistant && onRegenerate ? () => onRegenerate(turn.id) : undefined}
                  />
                </>
              ) : null}
            </div>
          );
        })}

        {state.referencedArtifacts.filter((artifact) => artifact.openable && artifact.artifactId).length ? (
          <section className="reference-documents" aria-label="Referenced artifacts">
            {state.referencedArtifacts
              .filter((artifact) => artifact.openable && artifact.artifactId)
              .map((artifact) => (
                <button
                  type="button"
                  className="reference-document-card"
                  aria-label="Open in workspace"
                  key={`${artifact.artifactId}:${artifact.revisionId ?? ''}`}
                  onClick={() => onOpenArtifacts?.(artifact.artifactId)}
                >
                  <span className="reference-document-icon"><FileText size={22} /></span>
                  <span>
                    <strong>{artifact.name}</strong>
                    <small>{artifact.kind ?? 'artifact'} · {artifact.summary ?? 'Governed artifact available'}</small>
                  </span>
                  <span className="reference-document-open">Open in workspace <ExternalLink size={15} /></span>
                </button>
              ))}
          </section>
        ) : null}

        {links.length ? (
          <section className="change-summary-card durable-task-links" aria-label="Durable task links">
            <header>
              <span className="change-summary-icon"><FileText size={19} /></span>
              <span><strong>Durable task links</strong><small>{links.length} governed reference{links.length === 1 ? '' : 's'}</small></span>
            </header>
            {links.map((link) => (
              <div className="changed-file-row" key={link.linkId}>
                <code>{link.targetType}</code>
                <span>{link.targetId}</span>
                {link.targetType === 'artifact' ? (
                  <button type="button" onClick={() => onOpenArtifacts?.(link.targetId)}>
                    Open artifact {link.targetId}
                  </button>
                ) : null}
                {link.targetType === 'approval' ? (
                  <button type="button" onClick={() => onOpenApproval?.(link.targetId)}>
                    Open approval {link.targetId}
                  </button>
                ) : null}
                {link.targetType === 'run' ? <span className="ps-muted">Governed run reference</span> : null}
                {link.targetType === 'team_job' ? <span className="ps-muted">Governed team job reference</span> : null}
              </div>
            ))}
          </section>
        ) : null}
      </div>
    </section>
  );
}
