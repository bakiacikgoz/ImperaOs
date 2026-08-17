import {
  ArrowUp,
  ChevronDown,
  Folder,
  GitBranch,
  Laptop,
  Mic,
  Plus,
  ShieldAlert,
  Square,
} from 'lucide-react';
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';

import {
  validateAssistantRuntimeSettings,
  type AssistantRuntimeSettings,
} from '../../settings';
import type { AssistantModelDiscoveryState } from '../../assistant/useAssistantModels';
import type {
  AssistantComposerControls,
  AssistantContextAttachmentKind,
  AssistantSafeToolIntent,
} from '../../assistant/assistantTypes';
import {
  assistantSlashCommands,
  hasAssistantSlashPrefix,
  resolveAssistantSlashCommand,
} from '../../assistant/assistantSlashCommands';
import { assistantUiText, translateAssistantText, type UiLocale } from '../../i18n';
import { Button } from '../primitives/Button';
import { Icon } from '../primitives/Icon';
import { AssistantModelPicker } from './AssistantModelPicker';

function runtimeDisplayLabel(settings: AssistantRuntimeSettings, locale: UiLocale): string {
  const defaultLabel = locale === 'tr' ? 'profil varsayılanı' : 'profile default';
  const provider = settings.assistantProvider.trim() || defaultLabel;
  const model = settings.assistantModel.trim() || settings.assistantHfModelId.trim() || defaultLabel;
  return `${provider} / ${model}`;
}

export function AssistantComposer({
  label,
  placeholder,
  sendLabel,
  disabled,
  initialValue = '',
  statusLabel = '',
  runtimeSettings,
  modelDiscovery,
  locale = 'en',
  variant = 'operator',
  projectControl,
  onRuntimeSettingsChange,
  onSend,
  onCancel,
}: {
  label: string;
  placeholder: string;
  sendLabel: string;
  disabled: boolean;
  initialValue?: string;
  statusLabel?: string;
  runtimeSettings: AssistantRuntimeSettings;
  modelDiscovery?: AssistantModelDiscoveryState | null;
  locale?: UiLocale;
  variant?: 'operator' | 'product';
  projectControl?: ReactNode;
  onRuntimeSettingsChange: (next: Partial<AssistantRuntimeSettings>) => void;
  onSend: (
    message: string,
    runtimeSettings: AssistantRuntimeSettings,
    controls: AssistantComposerControls,
  ) => void;
  onCancel?: () => void;
}) {
  const text = assistantUiText[locale];
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const contextOptions: Array<{ kind: AssistantContextAttachmentKind; label: string }> = [
    { kind: 'active_run', label: text.activeRun },
    { kind: 'event_tail', label: text.recentEvents },
    { kind: 'approval_summary', label: text.approval },
    { kind: 'artifact_summary', label: text.artifacts },
    { kind: 'system_health', label: text.systemHealthAttachment },
  ];
  const toolOptions: Array<{ intent: AssistantSafeToolIntent; label: string }> = [
    { intent: 'inspect_run', label: text.inspectRun },
    { intent: 'summarize_events', label: text.summarizeEvents },
    { intent: 'explain_policy_blocker', label: text.explainBlocker },
    { intent: 'draft_remediation_plan', label: text.draftPlan },
    { intent: 'prepare_approval_review', label: text.prepareApprovalReview },
  ];
  const [draft, setDraft] = useState(initialValue);
  const [contextAttachmentKinds, setContextAttachmentKinds] = useState<AssistantContextAttachmentKind[]>(
    contextOptions.map((option) => option.kind),
  );
  const [toolIntents, setToolIntents] = useState<AssistantSafeToolIntent[]>(['inspect_run']);

  useEffect(() => {
    setDraft(initialValue);
  }, [initialValue]);

  const resizeDraft = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 150)}px`;
  }, []);

  useLayoutEffect(() => {
    resizeDraft();
  }, [draft, resizeDraft]);

  const validationMessage = validateAssistantRuntimeSettings(runtimeSettings);
  const slashCommand = resolveAssistantSlashCommand(draft);
  const unsupportedSlashCommand = hasAssistantSlashPrefix(draft) && !slashCommand;
  const slashValidationMessage = unsupportedSlashCommand
    ? 'This slash command is not available in the governed assistant.'
    : slashCommand && !slashCommand.message
      ? 'Add a request after the slash command.'
      : undefined;
  const messageToSend = slashCommand ? slashCommand.message : draft;
  const mergedContextAttachmentKinds = Array.from(new Set([
    ...contextAttachmentKinds,
    ...(slashCommand?.contextAttachmentKinds ?? []),
  ]));
  const mergedToolIntents = Array.from(new Set([
    ...toolIntents,
    ...(slashCommand?.toolIntents ?? []),
  ]));
  const canSend = messageToSend.trim().length > 0 && !disabled && !validationMessage && !slashValidationMessage;
  const canCancel = disabled && Boolean(onCancel);
  const cancelLabel = locale === 'tr' ? 'Durdur' : 'Stop';
  const visibleStatusLabel = statusLabel && statusLabel !== 'idle' ? statusLabel : '';
  const selectedRuntimeLabel = runtimeDisplayLabel(runtimeSettings, locale);
  const approvalLabel = runtimeSettings.approvalProfile === 'always_ask'
    ? (locale === 'tr' ? 'Onay iste' : 'Ask for approval')
    : runtimeSettings.approvalProfile === 'policy_automatic'
      ? (locale === 'tr' ? 'Politika içinde otomatik' : 'Automatic within policy')
      : (locale === 'tr' ? 'Riske göre onay iste' : 'Risk-based approval');
  const controls: AssistantComposerControls = {
    contextAttachmentKinds: mergedContextAttachmentKinds,
    toolIntents: mergedToolIntents,
  };
  const sendDisabledReason =
    translateAssistantText(validationMessage, locale) ||
    slashValidationMessage ||
    (disabled
      ? translateAssistantText('Assistant is currently processing a turn.', locale)
        : messageToSend.trim().length === 0
        ? translateAssistantText('Enter a message to send.', locale)
        : undefined);
  const composerDisabledReason = disabled
    ? translateAssistantText('Assistant is currently processing a turn.', locale)
    : undefined;
  const isProductComposer = variant === 'product';

  const toggleContext = (kind: AssistantContextAttachmentKind) => {
    setContextAttachmentKinds((previous) =>
      previous.includes(kind) ? previous.filter((item) => item !== kind) : [...previous, kind],
    );
  };
  const toggleTool = (intent: AssistantSafeToolIntent) => {
    setToolIntents((previous) =>
      previous.includes(intent) ? previous.filter((item) => item !== intent) : [...previous, intent],
    );
  };
  const submitDraft = () => {
    if (!canSend) {
      return;
    }
    onSend(messageToSend, runtimeSettings, controls);
    setDraft('');
  };

  const messageInput = (
    <>
      <label className={`assistant-composer-label${isProductComposer ? ' sr-only' : ''}`} htmlFor="assistant-message">
        {label}
      </label>
      <textarea
        ref={textareaRef}
        id="assistant-message"
        placeholder={placeholder}
        rows={isProductComposer ? 1 : 3}
        value={draft}
        disabled={disabled}
        title={composerDisabledReason}
        data-disabled-reason={composerDisabledReason}
        onChange={(event) => {
          setDraft(event.target.value);
          if (typeof window !== 'undefined') {
            window.requestAnimationFrame(resizeDraft);
          }
        }}
        onKeyDown={(event) => {
          if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) {
            return;
          }
          event.preventDefault();
          submitDraft();
        }}
      />
    </>
  );
  const runtimeProfiles = (
    <div className="assistant-runtime-profiles" aria-label="Assistant runtime profiles">
      <label>Reasoning effort<select aria-label="Reasoning effort" value={runtimeSettings.reasoningEffort ?? 'medium'} onChange={(event) => onRuntimeSettingsChange({ reasoningEffort: event.target.value as NonNullable<AssistantRuntimeSettings['reasoningEffort']> })}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="very_high">Very high</option></select></label>
      <label>Speed<select aria-label="Speed profile" value={runtimeSettings.speedProfile ?? 'standard'} onChange={(event) => onRuntimeSettingsChange({ speedProfile: event.target.value as NonNullable<AssistantRuntimeSettings['speedProfile']> })}><option value="standard">Standard</option><option value="fast">Fast</option></select></label>
      <label>Approval<select aria-label="Approval profile" value={runtimeSettings.approvalProfile ?? 'risk_based'} onChange={(event) => onRuntimeSettingsChange({ approvalProfile: event.target.value as NonNullable<AssistantRuntimeSettings['approvalProfile']> })}><option value="always_ask">Always ask</option><option value="risk_based">Risk based</option><option value="policy_automatic">Within policy boundaries</option></select></label>
    </div>
  );
  const runtimeControls = (
    <>
      <AssistantModelPicker
        runtimeSettings={runtimeSettings}
        modelDiscovery={modelDiscovery}
        locale={locale}
        onRuntimeSettingsChange={onRuntimeSettingsChange}
      />
      {runtimeProfiles}
    </>
  );
  const validation = validationMessage ? (
    <p className="assistant-runtime-validation" role="alert">
      {translateAssistantText(validationMessage, locale)}
    </p>
  ) : null;
  const composerActions = (
    <div className={`assistant-composer-actions${isProductComposer ? ' composer-actions' : ''}`}>
      <div className={`assistant-composer-tools${isProductComposer ? ' composer-actions-left' : ''}`}>
        <details className={`assistant-composer-menu${isProductComposer ? ' composer-add-picker' : ''}`}>
          <summary className={isProductComposer ? 'icon-button' : undefined} aria-label={text.attachContext}>
            {isProductComposer ? <Plus size={18} strokeWidth={1.75} /> : <Icon name="paperclip" />}
            <span className="sr-only">{text.attachContext}</span>
          </summary>
          <div className="assistant-composer-menu-panel" role="group" aria-label={text.contextAttachments}>
            {contextOptions.map((option) => (
              <label key={option.kind}>
                <input
                  type="checkbox"
                  checked={contextAttachmentKinds.includes(option.kind)}
                  onChange={() => toggleContext(option.kind)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </details>
        <details className={`assistant-composer-menu${isProductComposer ? ' product-slash-menu' : ''}`}>
          <summary>Slash commands</summary>
          <div className="assistant-composer-menu-panel" role="group" aria-label="Governed slash commands">
            {assistantSlashCommands.map((command) => (
              <button key={command.command} type="button" onClick={() => setDraft(`${command.command} `)} title={command.description}>
                <code>{command.command}</code><span>{command.description}</span>
              </button>
            ))}
          </div>
        </details>
        <details className={`assistant-composer-menu${isProductComposer ? ' composer-access-picker' : ''}`}>
          <summary className={isProductComposer ? 'composer-access' : undefined}>
            {isProductComposer
              ? <ShieldAlert size={14} strokeWidth={1.75} />
              : <Icon name="command" />}
            <span>{isProductComposer ? approvalLabel : text.tools}</span>
            {!isProductComposer ? <Icon name="chevron" /> : null}
          </summary>
          <div className="assistant-composer-menu-panel" role="group" aria-label={text.safeToolIntents}>
            {toolOptions.map((option) => (
              <label key={option.intent}>
                <input
                  type="checkbox"
                  checked={toolIntents.includes(option.intent)}
                  onChange={() => toggleTool(option.intent)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </details>
        {visibleStatusLabel ? <em>{visibleStatusLabel}</em> : null}
      </div>
      <div className={`assistant-composer-submit${isProductComposer ? ' composer-actions-right' : ''}`}>
        {isProductComposer ? (
          <details className="model-picker">
            <summary className="composer-model">
              <span>{selectedRuntimeLabel}</span>
              <ChevronDown size={14} strokeWidth={1.75} />
            </summary>
            <div className="model-menu product-model-menu" role="dialog" aria-label="Model settings">
              {runtimeControls}
            </div>
          </details>
        ) : (
          <span className="assistant-model-summary" aria-label={text.selectedAssistantModel}>
            <span>{text.model}</span>
            <strong>{selectedRuntimeLabel}</strong>
          </span>
        )}
        {isProductComposer ? (
          <button
            type="button"
            className="icon-button"
            disabled
            title={locale === 'tr' ? 'Sesli giriş bu runtime tarafından sağlanmıyor.' : 'Voice input is not provided by this runtime.'}
            data-disabled-reason="VOICE_INPUT_CAPABILITY_UNAVAILABLE"
            aria-label={locale === 'tr' ? 'Sesli giriş kullanılamıyor' : 'Voice input unavailable'}
          >
            <Mic size={17} strokeWidth={1.75} />
          </button>
        ) : null}
        {isProductComposer ? (
          <button
            type={canCancel ? 'button' : 'submit'}
            className={`send-button${canSend ? ' is-ready' : ''}`}
            aria-label={canCancel ? cancelLabel : sendLabel}
            disabled={canCancel ? false : !canSend}
            title={canCancel ? cancelLabel : sendDisabledReason}
            data-disabled-reason={canCancel ? undefined : sendDisabledReason}
            onClick={canCancel ? onCancel : undefined}
          >
            {canCancel
              ? <Square size={15} strokeWidth={2.1} />
              : <ArrowUp size={16} strokeWidth={2.25} />}
          </button>
        ) : (
          <Button
            type={canCancel ? 'button' : 'submit'}
            icon={<Icon name={canCancel ? 'close' : 'arrow-up'} />}
            variant="primary"
            disabled={canCancel ? false : !canSend}
            title={canCancel ? cancelLabel : sendDisabledReason}
            data-disabled-reason={canCancel ? undefined : sendDisabledReason}
            onClick={canCancel ? onCancel : undefined}
          >
            <span className="assistant-send-label">{canCancel ? cancelLabel : sendLabel}</span>
          </Button>
        )}
      </div>
    </div>
  );
  const form = (
    <form
      className={`assistant-composer${isProductComposer ? ' composer codex-composer is-home' : ''}`}
      aria-label="Assistant composer"
      onSubmit={(event) => {
        event.preventDefault();
        submitDraft();
      }}
    >
      {isProductComposer ? (
        <div className="composer-entry">
          {messageInput}
          {validation}
          {composerActions}
        </div>
      ) : (
        <>
          {messageInput}
          {runtimeControls}
          {validation}
          {composerActions}
        </>
      )}
    </form>
  );

  if (isProductComposer) {
    return (
      <div className="composer-stack is-home">
        <div className="composer-context-bar">
          {projectControl ?? (
            <span className="composer-chip">
              <Folder size={14} strokeWidth={1.6} />
              <span>ImperaOS</span>
            </span>
          )}
          <span className="composer-chip" title={locale === 'tr' ? 'Yerel masaüstü runtime' : 'Local desktop runtime'}>
            <Laptop size={14} strokeWidth={1.6} />
            <span>{locale === 'tr' ? 'Yerel' : 'Local'}</span>
          </span>
          <span
            className="composer-chip"
            title={locale === 'tr' ? 'Doğrulanmış Git branch bağlamı kullanılamıyor.' : 'Verified Git branch context is unavailable.'}
            data-disabled-reason="GIT_BRANCH_CONTEXT_UNAVAILABLE"
          >
            <GitBranch size={14} strokeWidth={1.6} />
            <span>{locale === 'tr' ? 'Branch yok' : 'No branch'}</span>
          </span>
        </div>
        {form}
      </div>
    );
  }

  return form;
}
