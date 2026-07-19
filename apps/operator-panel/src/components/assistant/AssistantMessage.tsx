import { useState, type ReactNode } from 'react';

import type { AssistantArtifactProposalPart, AssistantArtifactRef, AssistantTurn } from '../../assistant/assistantTypes';
import { assistantUiText, translateAssistantText, type UiLocale } from '../../i18n';
import { Card } from '../primitives/Card';
import { Button } from '../primitives/Button';
import { Icon } from '../primitives/Icon';
import { AssistantActionPreview } from './AssistantActionPreview';
import { AssistantApprovalCard } from './AssistantApprovalCard';
import { ArtifactProposalCard } from './ArtifactProposalCard';
import { AssistantRunReferences } from './AssistantRunReferences';
import { AssistantRunningState } from './AssistantRunningState';

type MarkdownBlock =
  | { type: 'code'; code: string; language: string }
  | { type: 'heading'; depth: 2 | 3 | 4; text: string }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'table'; rows: string[][] }
  | { type: 'paragraph'; text: string };

const COLLAPSED_USER_MESSAGE_CHARS = 560;
const COLLAPSED_USER_MESSAGE_LINES = 8;

function formatClock(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function isTableDivider(line: string): boolean {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function parseTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
}

function parseMarkdownBlocks(source: string): MarkdownBlock[] {
  const lines = source.replace(/\r\n/g, '\n').split('\n');
  const blocks: MarkdownBlock[] = [];
  let paragraph: string[] = [];
  let index = 0;

  const flushParagraph = () => {
    const text = paragraph.join(' ').trim();
    if (text) {
      blocks.push({ type: 'paragraph', text });
    }
    paragraph = [];
  };

  while (index < lines.length) {
    const line = lines[index] ?? '';
    const trimmed = line.trim();

    if (!trimmed) {
      flushParagraph();
      index += 1;
      continue;
    }

    const fence = trimmed.match(/^```([\w.+-]*)\s*$/);
    if (fence) {
      flushParagraph();
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        code.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) {
        index += 1;
      }
      blocks.push({ type: 'code', code: code.join('\n'), language: fence[1] ?? '' });
      continue;
    }

    const heading = trimmed.match(/^(#{2,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      blocks.push({
        type: 'heading',
        depth: Math.min(heading[1].length, 4) as 2 | 3 | 4,
        text: heading[2],
      });
      index += 1;
      continue;
    }

    if (trimmed.includes('|') && index + 1 < lines.length && isTableDivider(lines[index + 1])) {
      flushParagraph();
      const rows = [parseTableRow(trimmed)];
      index += 2;
      while (index < lines.length && lines[index].trim().includes('|')) {
        rows.push(parseTableRow(lines[index]));
        index += 1;
      }
      blocks.push({ type: 'table', rows });
      continue;
    }

    const listMatch = trimmed.match(/^([-*]|\d+[.)])\s+(.+)$/);
    if (listMatch) {
      flushParagraph();
      const ordered = /^\d+[.)]$/.test(listMatch[1]);
      const items = [listMatch[2]];
      index += 1;
      while (index < lines.length) {
        const next = lines[index].trim();
        const nextMatch = next.match(/^([-*]|\d+[.)])\s+(.+)$/);
        if (!nextMatch || /^\d+[.)]$/.test(nextMatch[1]) !== ordered) {
          break;
        }
        items.push(nextMatch[2]);
        index += 1;
      }
      blocks.push({ type: 'list', ordered, items });
      continue;
    }

    paragraph.push(trimmed);
    index += 1;
  }

  flushParagraph();
  return blocks;
}

function isSafeHref(value: string): boolean {
  return /^(https?:|mailto:)/i.test(value);
}

function renderInlineMarkdown(source: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(source)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(source.slice(lastIndex, match.index));
    }
    const token = match[0];
    const key = `${keyPrefix}-${match.index}`;
    if (token.startsWith('`')) {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith('**')) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else {
      const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      const href = link?.[2]?.trim() ?? '';
      nodes.push(
        isSafeHref(href) ? (
          <a key={key} href={href} target="_blank" rel="noreferrer">
            {link?.[1] ?? href}
          </a>
        ) : (
          <span key={key}>{link?.[1] ?? token}</span>
        ),
      );
    }
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < source.length) {
    nodes.push(source.slice(lastIndex));
  }
  return nodes;
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  const copyCode = () => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      void navigator.clipboard.writeText(code);
    }
  };

  return (
    <div className="assistant-code-block">
      <div>
        <span>{language || 'text'}</span>
        <button type="button" onClick={copyCode}>
          Copy
        </button>
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}

function MarkdownAnswer({ text }: { text: string }) {
  const blocks = parseMarkdownBlocks(text);
  return (
    <div className="assistant-answer assistant-markdown">
      {blocks.map((block, index) => {
        const key = `${block.type}-${index}`;
        if (block.type === 'code') {
          return <CodeBlock key={key} code={block.code} language={block.language} />;
        }
        if (block.type === 'heading') {
          const Heading = `h${block.depth}` as 'h2' | 'h3' | 'h4';
          return <Heading key={key}>{renderInlineMarkdown(block.text, key)}</Heading>;
        }
        if (block.type === 'list') {
          const List = block.ordered ? 'ol' : 'ul';
          return (
            <List key={key}>
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>{renderInlineMarkdown(item, `${key}-${itemIndex}`)}</li>
              ))}
            </List>
          );
        }
        if (block.type === 'table') {
          const [head = [], ...body] = block.rows;
          return (
            <div className="assistant-table-scroll" key={key}>
              <table>
                <thead>
                  <tr>
                    {head.map((cell, cellIndex) => (
                      <th key={`${key}-h-${cellIndex}`}>{renderInlineMarkdown(cell, `${key}-h-${cellIndex}`)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {body.map((row, rowIndex) => (
                    <tr key={`${key}-r-${rowIndex}`}>
                      {row.map((cell, cellIndex) => (
                        <td key={`${key}-r-${rowIndex}-${cellIndex}`}>
                          {renderInlineMarkdown(cell, `${key}-r-${rowIndex}-${cellIndex}`)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        return <p key={key}>{renderInlineMarkdown(block.text, key)}</p>;
      })}
    </div>
  );
}

function UserMessageText({ text, locale }: { text: string; locale: UiLocale }) {
  const [expanded, setExpanded] = useState(false);
  const lines = text.split('\n');
  const shouldCollapse = text.length > COLLAPSED_USER_MESSAGE_CHARS || lines.length > COLLAPSED_USER_MESSAGE_LINES;
  const visibleText =
    shouldCollapse && !expanded
      ? `${lines.slice(0, COLLAPSED_USER_MESSAGE_LINES).join('\n').slice(0, COLLAPSED_USER_MESSAGE_CHARS).trimEnd()}...`
      : text;

  return (
    <div className={shouldCollapse && !expanded ? 'assistant-user-text assistant-user-text-collapsed' : 'assistant-user-text'}>
      <p>{visibleText}</p>
      {shouldCollapse ? (
        <button type="button" onClick={() => setExpanded((value) => !value)}>
          {expanded ? (locale === 'tr' ? 'Kısalt' : 'Collapse') : locale === 'tr' ? 'Devamını göster' : 'Show more'}
        </button>
      ) : null}
    </div>
  );
}

export function AssistantMessage({
  turn,
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
}: {
  turn: AssistantTurn;
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
}) {
  const text = assistantUiText[locale];
  const message = turn.assistantMessage;
  const primaryRun = message.referencedRuns[0];
  const hasDetailedFinding = Boolean(primaryRun) && !message.proposedAction;
  const hasAssistantOutput = Boolean(
    message.text ||
      message.warning ||
      message.error ||
      message.proposedAction ||
      message.approval ||
      message.referencedRuns.length > 0 ||
      message.referencedArtifacts.length > 0 ||
      message.parts.length > 0,
  );
  const copyAssistantText = () => {
    if (message.text && typeof navigator !== 'undefined' && navigator.clipboard) {
      void navigator.clipboard.writeText(message.text);
    }
  };

  return (
    <div className="assistant-turn">
      <Card className="assistant-user-message">
        <div>
          <time className="assistant-user-time">{formatClock(turn.userMessage.createdAtUtc)}</time>
          <UserMessageText text={turn.userMessage.text} locale={locale} />
        </div>
      </Card>
      <Card className="assistant-assistant-message">
        <div className="assistant-message-body">
          <span className="assistant-message-meta">
            <time>{formatClock(turn.startedAtUtc)}</time>
          </span>
        <AssistantRunningState
          status={turn.status}
          startedAtUtc={turn.startedAtUtc}
          completedAtUtc={turn.completedAtUtc}
        />
        {message.text ? <MarkdownAnswer text={translateAssistantText(message.text, locale)} /> : null}
        {message.warning ? <p className="assistant-warning-text">{translateAssistantText(message.warning, locale)}</p> : null}
        {message.error ? (
          <div className="assistant-error-card">
            <strong>{message.error.code}</strong>
            <p>{translateAssistantText(message.error.message, locale)}</p>
            {debugRawEnabled && message.error.stderrPreview ? <code>{message.error.stderrPreview}</code> : null}
          </div>
        ) : null}
        {hasDetailedFinding ? (
          <div className="assistant-findings-panel">
            <h3>{text.whatIFound}</h3>
            <dl>
              <div>
                <dt>{text.runId}</dt>
                <dd>{primaryRun?.id}</dd>
              </div>
              <div>
                <dt>{text.status}</dt>
                <dd>{translateAssistantText(primaryRun?.status ?? turn.status, locale)}</dd>
              </div>
              <div>
                <dt>{text.failedStep}</dt>
                <dd>{locale === 'tr' ? 'Operatör kuyruğu sağlığını incele' : 'Inspect operator queue health'}</dd>
              </div>
              <div>
                <dt>{text.rootCause}</dt>
                <dd>{primaryRun?.summary ? translateAssistantText(primaryRun.summary, locale) : text.noRootCause}</dd>
              </div>
              <div>
                <dt>{text.impact}</dt>
                <dd>{text.noChanges}</dd>
              </div>
              <div>
                <dt>{text.duration}</dt>
                <dd>00:03:18</dd>
              </div>
            </dl>
          </div>
        ) : null}
        {message.proposedAction ? <AssistantActionPreview action={message.proposedAction} locale={locale} /> : null}
        {message.approval ? (
          <AssistantApprovalCard
            approval={message.approval}
            disabled={approvalDisabled || !message.approval.detailLoaded}
            disabledReason={
              !message.approval.detailLoaded
                ? translateAssistantText('Approval detail must load before decision.', locale)
                : translateAssistantText(approvalDisabledReason, locale)
            }
            locale={locale}
            onReview={onReviewApproval}
            onApprove={onApprove}
            onReject={onReject}
            onExecute={onExecute}
          />
        ) : null}
        {message.parts.filter((part) => part.type === 'artifact-proposal').map((proposal) => (
          <ArtifactProposalCard
            key={proposal.proposalId}
            proposal={proposal}
            disabled={approvalDisabled}
            disabledReason={approvalDisabledReason}
            onReview={onReviewApproval}
            onApprove={onApprove}
            onReject={onReject}
            onApply={onApplyProposal ?? (() => undefined)}
            risk={message.approval?.approvalId === proposal.approvalId ? message.approval.risk : undefined}
          />
        ))}
        {message.parts.filter((part) => part.type === 'artifact').map((artifact) => (
          <section className="assistant-inline-artifact" key={`${artifact.artifactId}-${artifact.revisionId ?? 'draft'}`}>
            <div>
              <strong>{artifact.title}</strong>
              <p>{artifact.summary}</p>
            </div>
            {artifact.openable && onOpenArtifact ? (
              <Button variant="ghost" onClick={() => onOpenArtifact(artifact.artifactId)}>Open artifact</Button>
            ) : null}
          </section>
        ))}
        {renderInlineArtifact ? message.referencedArtifacts
          .filter((artifact) => artifact.kind === 'form' && artifact.artifactId)
          .map((artifact) => (
            <div key={`inline-${artifact.artifactId}-${artifact.revisionId ?? ''}`}>
              {renderInlineArtifact(artifact)}
            </div>
          )) : null}
        <AssistantRunReferences
          runs={message.referencedRuns}
          artifacts={message.referencedArtifacts}
          emptyRunLabel={emptyRunLabel}
          locale={locale}
          onOpenArtifact={onOpenArtifact}
        />
        {hasAssistantOutput ? (
          <div className="assistant-message-actions" aria-label="Assistant message actions">
            <button type="button" aria-label={text.copyAnswer} title={text.copyAnswer} onClick={copyAssistantText}>
              <Icon name="copy" />
            </button>
            <button type="button" aria-label={text.regenerateAnswer} title={text.regenerateAnswer} onClick={() => onRegenerate(turn.id)}>
              <Icon name="refresh" />
            </button>
          </div>
        ) : null}
        </div>
      </Card>
    </div>
  );
}
