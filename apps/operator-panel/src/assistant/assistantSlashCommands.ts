import type { AssistantContextAttachmentKind, AssistantSafeToolIntent } from './assistantTypes';

export type AssistantSlashCommand = {
  command: string;
  description: string;
  contextAttachmentKinds: AssistantContextAttachmentKind[];
  toolIntents: AssistantSafeToolIntent[];
};

export type ResolvedAssistantSlashCommand = Pick<
  AssistantSlashCommand,
  'command' | 'contextAttachmentKinds' | 'toolIntents'
> & { message: string };

/**
 * This is a UI registry, not a policy registry. Every command narrows to an
 * existing safe prompt intent and never grants tool, terminal, browser, or
 * approval authority.
 */
export const assistantSlashCommands: readonly AssistantSlashCommand[] = [
  { command: '/inspect-run', description: 'Attach and inspect the active run.', contextAttachmentKinds: ['active_run'], toolIntents: ['inspect_run'] },
  { command: '/summarize-events', description: 'Attach recent governed events.', contextAttachmentKinds: ['event_tail'], toolIntents: ['summarize_events'] },
  { command: '/explain-policy', description: 'Attach the pending approval summary.', contextAttachmentKinds: ['approval_summary'], toolIntents: ['explain_policy_blocker'] },
  { command: '/draft-remediation', description: 'Attach the system-health summary.', contextAttachmentKinds: ['system_health'], toolIntents: ['draft_remediation_plan'] },
  { command: '/review-approval', description: 'Prepare a governed approval review.', contextAttachmentKinds: ['approval_summary'], toolIntents: ['prepare_approval_review'] },
];

export function hasAssistantSlashPrefix(value: string): boolean {
  return /^\s*\/[^\s]+/.test(value);
}

export function resolveAssistantSlashCommand(value: string): ResolvedAssistantSlashCommand | null {
  const match = value.trim().match(/^(\/[^\s]+)(?:\s+([\s\S]*))?$/);
  if (!match) return null;
  const command = assistantSlashCommands.find((candidate) => candidate.command === match[1].toLowerCase());
  if (!command) return null;
  return {
    command: command.command,
    message: match[2]?.trim() ?? '',
    contextAttachmentKinds: [...command.contextAttachmentKinds],
    toolIntents: [...command.toolIntents],
  };
}
