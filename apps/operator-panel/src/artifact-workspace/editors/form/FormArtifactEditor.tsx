// Import the form component directly. The package barrel also imports its test
// registry, which eagerly initializes AJV and violates the production CSP.
import Form from '@rjsf/core/lib/components/Form.js';
import type { RJSFSchema, UiSchema } from '@rjsf/utils';
import { useId, useRef, useSyncExternalStore } from 'react';

import type {
  ArtifactDescriptor,
  ArtifactFormSubmissionResult,
  ArtifactRevision,
} from '../../artifactContracts';
import { deriveFormFieldId, validateSafeFormContent, type SafeFormContent } from './formAdapter';
import { formSessionKey, FormSessionRuntime } from './formSessionRuntime';
import { safeRjsfValidator } from './safeRjsfValidator';

interface FormArtifactEditorProps {
  artifact: ArtifactDescriptor;
  revision: ArtifactRevision;
  content: unknown;
  mode: 'edit' | 'readonly';
  runtime: FormSessionRuntime;
  locale?: 'en' | 'tr';
  onSubmit?: (
    response: Record<string, unknown>,
    idempotencyKey: string,
  ) => Promise<ArtifactFormSubmissionResult | Pick<ArtifactFormSubmissionResult, 'status' | 'disposition'>>;
}

function buildUiSchema(
  source: Record<string, unknown> | undefined,
  sensitivePaths: string[] | undefined,
): UiSchema<Record<string, unknown>> {
  const uiSchema: Record<string, unknown> = source ? { ...source } : {};
  for (const path of sensitivePaths ?? []) {
    const parts = path.slice(1).split('/').map((part) => part.replaceAll('~1', '/').replaceAll('~0', '~'));
    let current = uiSchema;
    for (const [index, key] of parts.entries()) {
      const existing = typeof current[key] === 'object' && current[key] !== null
        ? current[key] as Record<string, unknown>
        : {};
      const next = { ...existing };
      current[key] = next;
      if (index === parts.length - 1) next['ui:widget'] = 'password';
      current = next;
    }
  }
  return uiSchema as UiSchema<Record<string, unknown>>;
}

function errorPropertyPath(property: string | undefined): string[] {
  if (!property) return [];
  const parts: string[] = [];
  const pattern = /\.([A-Za-z_$][\w$]*)|\["((?:[^"\\]|\\.)*)"\]/g;
  for (const match of property.matchAll(pattern)) {
    if (match[1]) parts.push(match[1]);
    else if (match[2]) {
      try { parts.push(JSON.parse(`"${match[2]}"`) as string); } catch { return []; }
    }
  }
  return parts;
}

function ValidatedFormArtifactEditor({
  artifact,
  revision,
  mode,
  runtime,
  onSubmit,
  safeContent,
  locale = 'en',
}: Omit<FormArtifactEditorProps, 'content'> & { safeContent: SafeFormContent }) {
  const instanceId = useId().replace(/[^A-Za-z0-9_-]/g, '_');
  const errorSummaryRef = useRef<HTMLDivElement | null>(null);
  const sessionKey = formSessionKey(artifact.artifactId, revision.revisionId);
  runtime.prepare(sessionKey);
  const snapshot = useSyncExternalStore(
    runtime.subscribe,
    () => runtime.getSnapshot(sessionKey),
    () => runtime.getSnapshot(sessionKey),
  );
  const schema = safeContent.schema as RJSFSchema;
  const uiSchema = buildUiSchema(safeContent.uiSchema, safeContent.sensitivePaths);
  const disabled = mode === 'readonly';
  const idPrefix = `${deriveFormFieldId(artifact.artifactId, [])}__${instanceId}`;
  const submissionState = snapshot.submissionState;
  const text = locale === 'tr' ? {
    invalid: 'Formda geçersiz alanlar var.',
    retry: 'Form gönderimini yeniden dene',
    submitting: 'Form gönderiliyor…',
    submit: 'Formu gönder',
    failed: 'Form gönderilemedi. Aynı gönderimi yeniden deneyin.',
    submitted: 'Form gönderildi.',
    pending: 'Form gönderildi ve onay bekliyor.',
  } : {
    invalid: 'Form contains invalid fields.',
    retry: 'Retry form submission',
    submitting: 'Submitting form…',
    submit: 'Submit form',
    failed: 'The form could not be submitted. Retry the same submission.',
    submitted: 'Form submitted.',
    pending: 'Form submitted and awaiting approval.',
  };

  const update = (formData: Record<string, unknown> | undefined) => {
    const nextData = formData ?? {};
    const validation = safeRjsfValidator.validateFormData(nextData, schema);
    runtime.update(sessionKey, nextData, validation.errors);
  };

  const submit = async () => {
    const validation = safeRjsfValidator.validateFormData(snapshot.formData, schema);
    runtime.update(sessionKey, snapshot.formData, validation.errors);
    if (validation.errors.length > 0) {
      queueMicrotask(() => errorSummaryRef.current?.focus());
      return;
    }
    if (!onSubmit) return;
    const submissionKey = runtime.beginSubmission(
      sessionKey,
      () => `form-submit-${globalThis.crypto.randomUUID()}`,
    );
    if (!submissionKey) return;
    try {
      const result = await onSubmit(snapshot.formData, submissionKey);
      runtime.completeSubmission(
        sessionKey,
        result.status === 'pending_continuation' ? 'pending' : 'submitted',
      );
    } catch {
      runtime.failSubmission(sessionKey);
    }
  };

  return (
    <section aria-label={artifact.title}>
      {snapshot.errors.length > 0 ? (
        <div ref={errorSummaryRef} role="alert" aria-live="polite" tabIndex={-1}>
          <p>{text.invalid}</p>
          <ul>
            {snapshot.errors.slice(0, 20).map((error, index) => {
              const targetPath = errorPropertyPath(error.property);
              const targetId = targetPath.length > 0 ? [idPrefix, ...targetPath].join('__') : null;
              const label = (error.stack || 'Field is invalid.').slice(0, 256);
              return (
                <li key={`${error.property ?? 'form'}-${error.name ?? 'invalid'}-${index}`}>
                  {targetId ? <a href={`#${targetId}`}>{label}</a> : label}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
      <Form<Record<string, unknown>>
        schema={schema}
        uiSchema={uiSchema}
        validator={safeRjsfValidator}
        formData={snapshot.formData}
        disabled={disabled}
        readonly={disabled}
        idPrefix={idPrefix}
        idSeparator="__"
        noHtml5Validate
        onChange={(event) => update(event.formData)}
        onBlur={() => update(snapshot.formData)}
      >
        <></>
      </Form>
      {onSubmit && !disabled ? (
        <button
          type="button"
          disabled={submissionState === 'submitting' || submissionState === 'submitted' || submissionState === 'pending'}
          onClick={() => void submit()}
        >
          {submissionState === 'failed' ? text.retry : submissionState === 'submitting' ? text.submitting : text.submit}
        </button>
      ) : null}
      {submissionState === 'failed' ? (
        <p role="alert">{text.failed}</p>
      ) : null}
      {submissionState === 'submitted' ? <p role="status">{text.submitted}</p> : null}
      {submissionState === 'pending' ? <p role="status">{text.pending}</p> : null}
    </section>
  );
}

export function FormArtifactEditor(props: FormArtifactEditorProps) {
  let safeContent: SafeFormContent | null = null;
  try {
    safeContent = validateSafeFormContent(props.content);
  } catch {
    safeContent = null;
  }
  if (!safeContent) {
    return <div role="alert">{props.locale === 'tr' ? 'Form içeriği güvenli olmadığı için kullanılamıyor.' : 'Form content is unavailable because its schema is unsafe.'}</div>;
  }
  return <ValidatedFormArtifactEditor {...props} safeContent={safeContent} />;
}
