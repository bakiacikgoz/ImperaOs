import { useEffect, useRef } from 'react';

import type { ArtifactFormSubmissionRequest, ArtifactFormSubmissionResult } from './artifactContracts';
import { ArtifactEditorHost } from './editors/ArtifactEditorHost';
import type { FormSessionRuntime } from './editors/form/formSessionRuntime';
import type { ArtifactWorkspaceTab } from './workspaceController';

export function AssistantInlineFormPart({
  artifactId,
  tab,
  loading,
  locale,
  formRuntime,
  onLoad,
  onExpand,
  onSubmit,
  workspaceEnabled = false,
  formEnabled = false,
}: {
  artifactId: string;
  tab: ArtifactWorkspaceTab | null;
  loading: boolean;
  locale: 'en' | 'tr';
  formRuntime: FormSessionRuntime;
  onLoad: (artifactId: string) => void;
  onExpand: (artifactId: string) => void;
  onSubmit: (request: ArtifactFormSubmissionRequest) => Promise<ArtifactFormSubmissionResult>;
  workspaceEnabled?: boolean;
  formEnabled?: boolean;
}) {
  const requestedArtifactId = useRef<string | null>(null);
  useEffect(() => {
    if (!tab && !loading && requestedArtifactId.current !== artifactId) {
      requestedArtifactId.current = artifactId;
      onLoad(artifactId);
    }
  }, [artifactId, loading, onLoad, tab]);

  if (!tab) {
    return (
      <div className="assistant-inline-form" role="status">
        {locale === 'tr' ? 'GÃ¼venli form yÃ¼kleniyorâ€¦' : 'Loading governed formâ€¦'}
        {!loading ? (
          <button type="button" onClick={() => onLoad(artifactId)}>
            {locale === 'tr' ? 'Formu yeniden dene' : 'Retry form'}
          </button>
        ) : null}
      </div>
    );
  }
  if (tab.artifact.kind !== 'form') {
    return <div className="assistant-inline-form" role="alert">The referenced artifact is not a form.</div>;
  }
  return (
    <section className="assistant-inline-form" aria-label={`Inline form: ${tab.artifact.title}`}>
      <header className="assistant-inline-form-heading">
        <strong>{locale === 'tr' ? 'Doğrulanmış form' : 'Validated form'}</strong>
        <p>{locale === 'tr'
          ? 'Yanıtlarınız gönderilmeden önce kontrol edilir. Aynı gönderim güvenle yeniden denenebilir.'
          : 'Your answers are checked before submission. The same submission can be retried safely.'}</p>
      </header>
      <ArtifactEditorHost
        artifact={tab.artifact}
        revision={tab.revision}
        content={tab.draftContent}
        mode={tab.artifact.status === 'archived' ? 'view' : 'edit'}
        saveState={tab.saveState}
        onChange={() => undefined}
        onSelectionChange={() => undefined}
        onRequestExport={() => undefined}
        formRuntime={formRuntime}
        onSubmitForm={onSubmit}
        workspaceEnabled={workspaceEnabled}
        formEnabled={formEnabled}
        locale={locale}
      />
      <button type="button" onClick={() => onExpand(artifactId)}>
        {locale === 'tr' ? 'Çalışma alanında genişlet' : 'Expand in Workbench'}
      </button>
    </section>
  );
}
