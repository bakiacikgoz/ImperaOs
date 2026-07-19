import { useEffect, useMemo, useRef, useState } from 'react';

import type { AssistantSessionState } from '../../assistant/assistantTypes';
import { SpreadsheetArtifactContentSchema, type ArtifactAssetDescriptor, type ArtifactAssetReadResult, type ArtifactDescriptor, type ArtifactRevision } from '../../artifact-workspace/artifactContracts';
import type { ArtifactFormSubmissionRequest, ArtifactFormSubmissionResult } from '../../artifact-workspace/artifactContracts';
import type { FormSessionRuntime } from '../../artifact-workspace/editors/form/formSessionRuntime';
import type { ArtifactWorkspaceState } from '../../artifact-workspace/workspaceController';
import type {
  ArtifactRevisionComparison,
  ArtifactWorkspaceUiError,
} from '../../artifact-workspace/useAssistantArtifactWorkspaceController';
import { ArtifactEditorHost, type ArtifactSelection } from '../../artifact-workspace/editors/ArtifactEditorHost';
import type { ArtifactFeatureFlagState } from '../../artifact-workspace/artifactFeatureFlags';
import { ArtifactDiffView } from '../../artifact-workspace/ui/ArtifactDiffView';
import { ArtifactConflictPanel } from '../../artifact-workspace/ui/ArtifactConflictPanel';
import { ArtifactExportDialog } from '../../artifact-workspace/ui/ArtifactExportDialog';
import { ArtifactEditorErrorBoundary } from '../../artifact-workspace/ui/ArtifactWorkbenchShell';
import { ArtifactReadOnlyContent } from '../../artifact-workspace/ui/ArtifactLicenseBlocked';
import {
  ARTIFACT_EXPORT_FORMATS,
  suggestedArtifactExportFilename,
  type ArtifactExportFormat,
} from '../../artifact-workspace/artifactExportFormats';
import { translateAssistantText, type UiLocale } from '../../i18n';
import { Badge } from '../primitives/Badge';
import { Button } from '../primitives/Button';
import { Icon } from '../primitives/Icon';

export type AssistantWorkbenchArtifact = {
  name: string;
  summary?: string;
  value?: unknown;
};

type WorkspaceProps = {
  artifactFeatureFlags?: ArtifactFeatureFlagState;
  workspaceState?: ArtifactWorkspaceState;
  catalog?: ArtifactDescriptor[];
  catalogNextCursor?: string | null;
  catalogLoading?: boolean;
  history?: ArtifactRevision[];
  historyNextCursor?: string | null;
  historyLoading?: boolean;
  comparison?: ArtifactRevisionComparison | null;
  conflictResolving?: { artifactId: string; action: 'refresh' | 'reload' | 'fork' } | null;
  onOpenArtifact?: (artifactId: string) => void;
  onActivateArtifact?: (artifactId: string) => void;
  onRequestClose?: (artifactId: string) => void;
  onLoadCatalog?: () => void;
  onLoadMoreCatalog?: () => void;
  onLoadHistory?: (artifactId: string) => void;
  onLoadMoreHistory?: (artifactId: string) => void;
  onCompareRevision?: (artifactId: string, revisionId: string) => void;
  onCloseComparison?: () => void;
  onRefreshConflict?: (artifactId: string) => void;
  onCompareConflict?: (artifactId: string) => void;
  onReloadConflict?: (artifactId: string) => void;
  onForkConflict?: (artifactId: string) => void;
  onEditArtifact?: (artifactId: string, content: ArtifactWorkspaceState['tabs'][number]['draftContent']) => void;
  onRetrySave?: (artifactId: string) => void;
  onRestoreArtifact?: (artifactId: string, revisionId: string) => void;
  onExportArtifact?: (artifactId: string, format: ArtifactExportFormat, sheetId?: string) => void;
  onImportAsset?: (artifactId: string) => Promise<ArtifactAssetDescriptor | null>;
  onResolveAsset?: (assetId: string) => Promise<ArtifactAssetReadResult | null>;
  formRuntime?: FormSessionRuntime;
  onSubmitForm?: (request: ArtifactFormSubmissionRequest) => Promise<ArtifactFormSubmissionResult>;
  workspaceError?: ArtifactWorkspaceUiError | null;
  operationNotice?: string | null;
  onEditorSelectionChange?: (selection: ArtifactSelection | null) => void;
};

function stringifyPreview(value: unknown): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function previewLines(value: unknown): string[] {
  const text = stringifyPreview(value).trim();
  return text ? text.split('\n').slice(0, 28) : [];
}

function metadataLabel(artifact: ArtifactDescriptor, key: string, fallback: string): string {
  const value = artifact.metadata[key];
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function licenseLabel(artifact: ArtifactDescriptor): string {
  if (artifact.kind === 'canvas' || artifact.kind === 'spreadsheet') {
    return metadataLabel(artifact, 'licenseStatus', 'license required');
  }
  return metadataLabel(artifact, 'licenseStatus', 'built-in');
}

export function AssistantWorkbench({
  state,
  artifacts,
  selectedArtifactName,
  locale = 'en',
  onSelectArtifact,
  onViewRuns,
  workspaceState,
  catalog = [],
  catalogNextCursor = null,
  catalogLoading = false,
  history = [],
  historyNextCursor = null,
  historyLoading = false,
  comparison = null,
  conflictResolving = null,
  onOpenArtifact,
  onActivateArtifact,
  onRequestClose,
  onLoadCatalog,
  onLoadMoreCatalog,
  onLoadHistory,
  onLoadMoreHistory,
  onCompareRevision,
  onCloseComparison,
  onRefreshConflict,
  onCompareConflict,
  onReloadConflict,
  onForkConflict,
  onEditArtifact,
  onRetrySave,
  onRestoreArtifact,
  onExportArtifact,
  onImportAsset,
  onResolveAsset,
  formRuntime,
  onSubmitForm,
  workspaceError = null,
  operationNotice = null,
  onEditorSelectionChange,
  artifactFeatureFlags,
}: {
  state: AssistantSessionState;
  artifacts: AssistantWorkbenchArtifact[];
  selectedArtifactName: string;
  locale?: UiLocale;
  onSelectArtifact: (name: string) => void;
  onViewRuns: () => void;
} & WorkspaceProps) {
  const enabledFeatures = artifactFeatureFlags ?? {
    workspace: true,
    document: true,
    form: true,
    code: true,
    flow: true,
    spreadsheet: false,
    canvas: false,
    slides: true,
    export: true,
    assistantUiRuntime: false,
    aiSdkTauriTransport: false,
  };
  const [search, setSearch] = useState('');
  const [kindFilter, setKindFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [exportFormat, setExportFormat] = useState<ArtifactExportFormat | null>(null);
  const activeTabButtonRef = useRef<HTMLButtonElement>(null);
  const previousConflictArtifactId = useRef<string | null>(null);
  const previousSaveState = useRef<string | null>(null);
  const activeTurn = state.turns.find((turn) => turn.id === state.activeTurnId) ?? state.turns.at(-1);
  const message = activeTurn?.assistantMessage;
  const selectedArtifact = artifacts.find((artifact) => artifact.name === selectedArtifactName) ?? artifacts[0];
  const lines = previewLines(selectedArtifact?.value);
  const title = locale === 'tr' ? 'Çalışma alanı' : 'Workbench';
  const artifactTitle = locale === 'tr' ? 'Artifact önizleme' : 'Artifact preview';
  const actionTitle = locale === 'tr' ? 'Aktif çıktı' : 'Active output';
  const activeTab = workspaceState?.tabs.find(
    (tab) => tab.artifact.artifactId === workspaceState.activeArtifactId,
  );

  useEffect(() => {
    onEditorSelectionChange?.(null);
    setExportFormat(null);
  }, [activeTab?.artifact.artifactId, onEditorSelectionChange]);
  const filteredCatalog = useMemo(() => {
    const localeCode = locale === 'tr' ? 'tr' : 'en';
    const needle = search.trim().toLocaleLowerCase(localeCode);
    return catalog.filter((artifact) => {
      const matchesSearch =
        !needle ||
        artifact.title.toLocaleLowerCase(localeCode).includes(needle) ||
        artifact.artifactId.toLowerCase().includes(needle);
      return (
        matchesSearch &&
        (kindFilter === 'all' || artifact.kind === kindFilter) &&
        (statusFilter === 'all' || artifact.status === statusFilter)
      );
    });
  }, [catalog, kindFilter, locale, search, statusFilter]);
  const activeComparison = activeTab && comparison?.artifactId === activeTab.artifact.artifactId
    ? comparison
    : null;
  const activeSpreadsheet = activeTab?.artifact.kind === 'spreadsheet'
    ? SpreadsheetArtifactContentSchema.safeParse(activeTab.draftContent)
    : null;

  useEffect(() => {
    const currentConflictArtifactId = activeTab?.conflict ? activeTab.artifact.artifactId : null;
    if (previousConflictArtifactId.current && !currentConflictArtifactId) {
      queueMicrotask(() => {
        if (document.activeElement === document.body) {
          activeTabButtonRef.current?.focus();
        }
      });
    }
    previousConflictArtifactId.current = currentConflictArtifactId;
  }, [activeTab?.artifact.artifactId, activeTab?.conflict]);
  useEffect(() => {
    const currentSaveState = activeTab?.saveState ?? null;
    if (previousSaveState.current === 'error' && currentSaveState !== 'error') {
      queueMicrotask(() => {
        if (document.activeElement === document.body) {
          activeTabButtonRef.current?.focus();
        }
      });
    }
    previousSaveState.current = currentSaveState;
  }, [activeTab?.artifact.artifactId, activeTab?.saveState]);

  return (
    <aside className="assistant-workbench" aria-label={title}>
      <div className="assistant-workbench-head">
        <span>{title}</span>
        <Badge tone={state.status === 'failed' ? 'error' : state.status === 'awaiting_approval' ? 'warning' : 'info'}>
          {translateAssistantText(state.status, locale)}
        </Badge>
      </div>

      {workspaceState ? (
        <section className="assistant-workbench-panel artifact-workspace-chrome" aria-label="Artifact workspace">
          <div className="assistant-workbench-panel-head">
            <Icon name="grid" />
            <span>Artifact workspace</span>
            <Button variant="ghost" onClick={onLoadCatalog} disabled={catalogLoading}>
              {catalogLoading ? 'Loading…' : 'Refresh'}
            </Button>
          </div>

          {workspaceError ? (
            <p className="artifact-workspace-banner" role="alert">{workspaceError.message}</p>
          ) : null}
          {operationNotice ? (
            <p className="artifact-workspace-banner" role="status" aria-label="Artifact operation status">
              {operationNotice}
            </p>
          ) : null}

          <div className="artifact-workspace-filters">
            <input
              type="search"
              aria-label="Search artifacts"
              placeholder="Search title or ID"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <select aria-label="Filter artifact kind" value={kindFilter} onChange={(event) => setKindFilter(event.target.value)}>
              <option value="all">All kinds</option>
              {['document', 'form', 'code', 'flow', 'spreadsheet', 'canvas', 'slides'].map((kind) => (
                <option key={kind} value={kind}>{kind}</option>
              ))}
            </select>
            <select aria-label="Filter artifact status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All states</option>
              {['draft', 'active', 'archived', 'blocked', 'corrupt'].map((status) => (
                <option key={status} value={status}>{status}</option>
              ))}
            </select>
          </div>

          <div className="artifact-workspace-navigator" aria-label="Artifact navigator">
            {filteredCatalog.length > 0 ? filteredCatalog.map((artifact) => (
              <button type="button" key={artifact.artifactId} onClick={() => onOpenArtifact?.(artifact.artifactId)}>
                <strong>{artifact.title}</strong>
                <span>{artifact.kind} · {artifact.status} · r{artifact.currentRevisionNumber}</span>
              </button>
            )) : (
              <p className="assistant-empty-state">{catalogLoading ? 'Loading artifacts…' : 'No matching artifacts.'}</p>
            )}
          </div>
          {catalogNextCursor ? (
            <Button variant="ghost" onClick={onLoadMoreCatalog} disabled={catalogLoading}>
              Load more artifacts
            </Button>
          ) : null}

          {workspaceState.tabs.length > 0 ? (
            <div className="artifact-workspace-tabs" role="tablist" aria-label="Open artifacts">
              {workspaceState.tabs.map((tab) => (
                <button
                  className="artifact-workspace-tab-button"
                  key={tab.artifact.artifactId}
                  ref={tab.artifact.artifactId === workspaceState.activeArtifactId ? activeTabButtonRef : undefined}
                  type="button"
                  role="tab"
                  aria-selected={tab.artifact.artifactId === workspaceState.activeArtifactId}
                  onClick={() => onActivateArtifact?.(tab.artifact.artifactId)}
                >
                  {tab.artifact.title}{tab.dirty ? ' •' : ''}
                </button>
              ))}
            </div>
          ) : null}

          {activeTab ? (
            <div className="artifact-workspace-active" role="tabpanel">
              <div className="artifact-workspace-status-row" aria-label="Artifact status">
                <Badge tone={activeTab.saveState === 'conflict' || activeTab.saveState === 'error' ? 'error' : activeTab.dirty ? 'warning' : 'success'}>
                  {activeTab.saveState}
                </Badge>
                <Badge tone="info">Revision {activeTab.revision.revisionNumber}</Badge>
                <Badge>{activeTab.artifact.dataClass}</Badge>
                <Badge>{metadataLabel(activeTab.artifact, 'policyStatus', 'governed')}</Badge>
                <Badge tone={licenseLabel(activeTab.artifact).includes('required') ? 'warning' : 'success'}>
                  {licenseLabel(activeTab.artifact)}
                </Badge>
                <button
                  type="button"
                  aria-label={`Close ${activeTab.artifact.title}`}
                  onClick={() => onRequestClose?.(activeTab.artifact.artifactId)}
                >
                  Close
                </button>
              </div>
              {activeTab.artifact.status === 'archived' ? (
                <p className="artifact-workspace-banner">Archived artifacts are read-only.</p>
              ) : null}
              {activeTab.saveState === 'error' ? (
                <div className="artifact-workspace-banner" role="alert">
                  <p>{activeTab.saveError ?? 'Artifact autosave failed.'}</p>
                  <Button
                    variant="ghost"
                    onClick={() => onRetrySave?.(activeTab.artifact.artifactId)}
                  >
                    Retry save
                  </Button>
                </div>
              ) : null}
              {activeTab.conflict ? (
                <ArtifactConflictPanel
                  conflict={activeTab.conflict}
                  resolvingAction={conflictResolving?.artifactId === activeTab.artifact.artifactId ? conflictResolving.action : null}
                  comparisonOpen={activeComparison?.status === 'ready'}
                  onRefresh={() => onRefreshConflict?.(activeTab.artifact.artifactId)}
                  onCompare={() => onCompareConflict?.(activeTab.artifact.artifactId)}
                  onReload={() => onReloadConflict?.(activeTab.artifact.artifactId)}
                  onFork={() => onForkConflict?.(activeTab.artifact.artifactId)}
                />
              ) : null}
              {activeComparison?.status === 'loading' ? (
                <p className="artifact-workspace-banner" role="status">Loading revision comparison…</p>
              ) : null}
              {activeComparison?.status === 'error' && activeComparison.error ? (
                <p className="artifact-workspace-banner" role="alert">{activeComparison.error.message}</p>
              ) : null}
              {activeComparison?.status === 'ready' && activeComparison.result && activeComparison.beforeRevisionNumber !== null ? (
                <ArtifactDiffView
                  beforeRevisionNumber={activeComparison.beforeRevisionNumber}
                  afterRevisionNumber={activeComparison.afterRevisionNumber}
                  afterLabel={activeComparison.mode === 'conflict' ? 'Local draft' : undefined}
                  dirtyDraftExcluded={activeComparison.dirtyDraftExcluded}
                  result={activeComparison.result}
                  onClose={() => onCloseComparison?.()}
                />
              ) : null}
              <div hidden={activeComparison?.status === 'ready'} aria-hidden={activeComparison?.status === 'ready' || undefined}>
                <ArtifactEditorErrorBoundary
                  key={activeTab.artifact.artifactId}
                  artifactKind={activeTab.artifact.kind}
                  readOnlyFallback={<ArtifactReadOnlyContent artifact={activeTab.artifact} content={activeTab.draftContent} />}
                >
                  <ArtifactEditorHost
                    artifact={activeTab.artifact}
                    revision={activeTab.revision}
                    content={activeTab.draftContent}
                    mode={activeTab.artifact.status === 'archived' ? 'view' : 'edit'}
                    saveState={activeTab.saveState}
                    onChange={(next) => onEditArtifact?.(activeTab.artifact.artifactId, next)}
                    onSelectionChange={(selection) => {
                      onEditorSelectionChange?.(selection);
                    }}
                    onRequestExport={(format) => {
                      setExportFormat(format as ArtifactExportFormat);
                    }}
                    onImportAsset={() => onImportAsset?.(activeTab.artifact.artifactId) ?? Promise.resolve(null)}
                    onResolveAsset={onResolveAsset}
                    formRuntime={formRuntime}
                    onSubmitForm={onSubmitForm}
                    locale={locale}
                    workspaceEnabled={enabledFeatures.workspace}
                    documentEnabled={enabledFeatures.document}
                    formEnabled={enabledFeatures.form}
                    codeEnabled={enabledFeatures.code}
                    flowEnabled={enabledFeatures.flow}
                    spreadsheetEnabled={enabledFeatures.spreadsheet}
                    canvasEnabled={enabledFeatures.canvas}
                    slidesEnabled={enabledFeatures.slides}
                  />
                </ArtifactEditorErrorBoundary>
              </div>
              {enabledFeatures.export && activeComparison?.status !== 'ready' ? (
                <div className="artifact-workspace-export-actions" aria-label="Artifact export">
                  <Button
                    variant="ghost"
                    disabled={activeTab.dirty || activeTab.saveState === 'saving' || activeTab.saveState === 'error' || Boolean(activeTab.conflict)}
                    onClick={() => setExportFormat(ARTIFACT_EXPORT_FORMATS[activeTab.artifact.kind][0]?.value as ArtifactExportFormat)}
                  >
                    Export
                  </Button>
                </div>
              ) : null}
              {exportFormat ? (
                <ArtifactExportDialog
                  artifactTitle={activeTab.artifact.title}
                  formats={ARTIFACT_EXPORT_FORMATS[activeTab.artifact.kind]}
                  initialFormat={exportFormat}
                  suggestedFilename={suggestedArtifactExportFilename(activeTab.artifact.title, exportFormat)}
                  revisionNumber={activeTab.revision.revisionNumber}
                  dataClass={activeTab.artifact.dataClass}
                  policyState={metadataLabel(activeTab.artifact, 'policyStatus', 'governed')}
                  estimatedSizeBytes={new TextEncoder().encode(JSON.stringify(activeTab.draftContent)).byteLength}
                  securityWarning="Exported files leave workspace governance. Verify the destination and sharing policy."
                  onCancel={() => setExportFormat(null)}
                  onConfirm={(format) => {
                    const selected = format as ArtifactExportFormat;
                    setExportFormat(null);
                    const sheetId = selected === 'csv' && activeTab.artifact.kind === 'spreadsheet' && activeSpreadsheet?.success
                      ? activeSpreadsheet.data.sheets[0]?.id
                      : undefined;
                    if (sheetId) onExportArtifact?.(activeTab.artifact.artifactId, selected, sheetId);
                    else onExportArtifact?.(activeTab.artifact.artifactId, selected);
                  }}
                />
              ) : null}
              <div className="artifact-workspace-history" aria-label="Revision history">
                <div className="assistant-workbench-panel-head">
                  <span>Revision history</span>
                  {historyLoading ? <span>Loading…</span> : null}
                  <Button variant="ghost" onClick={() => onLoadHistory?.(activeTab.artifact.artifactId)} disabled={historyLoading}>
                    Refresh history
                  </Button>
                </div>
                {history.length > 0 ? history.map((item) => (
                  <article key={item.revisionId}>
                    <strong>Revision {item.revisionNumber}</strong>
                    <span>{item.changeSummary || item.mutationType}</span>
                    <time dateTime={item.createdAtUtc}>{new Date(item.createdAtUtc).toLocaleString()}</time>
                    {item.revisionId !== activeTab.revision.revisionId ? (
                      <>
                        <Button
                          variant="ghost"
                          aria-label={`Compare revision ${item.revisionNumber}`}
                          disabled={historyLoading}
                          onClick={() => onCompareRevision?.(activeTab.artifact.artifactId, item.revisionId)}
                        >
                          Compare
                        </Button>
                        <Button
                          variant="ghost"
                          aria-label={`Restore revision ${item.revisionNumber}`}
                          disabled={activeTab.artifact.status === 'archived' || activeTab.dirty || activeTab.saveState === 'saving' || Boolean(activeTab.conflict)}
                          onClick={() => onRestoreArtifact?.(activeTab.artifact.artifactId, item.revisionId)}
                        >
                          Restore
                        </Button>
                      </>
                    ) : null}
                  </article>
                )) : <p className="assistant-empty-state">No revision history loaded.</p>}
                {historyNextCursor ? (
                  <Button
                    variant="ghost"
                    onClick={() => onLoadMoreHistory?.(activeTab.artifact.artifactId)}
                    disabled={historyLoading}
                  >
                    Load more history
                  </Button>
                ) : null}
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="assistant-workbench-panel">
        <div className="assistant-workbench-panel-head">
          <Icon name="sparkle" />
          <span>{actionTitle}</span>
        </div>
        {message?.proposedAction ? (
          <dl className="assistant-workbench-dl">
            <div><dt>{locale === 'tr' ? 'Aksiyon' : 'Action'}</dt><dd>{translateAssistantText(message.proposedAction.title, locale)}</dd></div>
            <div><dt>{locale === 'tr' ? 'Hedef' : 'Target'}</dt><dd>{message.proposedAction.target}</dd></div>
            <div><dt>Risk</dt><dd>{message.proposedAction.risk}</dd></div>
          </dl>
        ) : message?.text ? (
          <p className="assistant-workbench-text">{translateAssistantText(message.text, locale)}</p>
        ) : (
          <p className="assistant-empty-state">{locale === 'tr' ? 'Asistan çıktısı burada sabitlenir.' : 'Assistant output will stay pinned here.'}</p>
        )}
      </section>

      <section className="assistant-workbench-panel">
        <div className="assistant-workbench-panel-head"><Icon name="terminal" /><span>{artifactTitle}</span></div>
        {artifacts.length > 0 ? (
          <>
            <div className="assistant-workbench-artifacts" role="tablist" aria-label={artifactTitle}>
              {artifacts.map((artifact) => (
                <button
                  type="button"
                  role="tab"
                  aria-selected={artifact.name === selectedArtifact?.name}
                  key={artifact.name}
                  className={artifact.name === selectedArtifact?.name ? 'assistant-workbench-artifact-active' : ''}
                  onClick={() => onSelectArtifact(artifact.name)}
                >
                  {artifact.name}
                </button>
              ))}
            </div>
            {selectedArtifact?.summary ? <p className="assistant-workbench-text">{selectedArtifact.summary}</p> : null}
            {lines.length > 0 ? (
              <pre className="assistant-workbench-preview"><code>{lines.join('\n')}</code></pre>
            ) : (
              <p className="assistant-empty-state">{locale === 'tr' ? 'Önizleme yok.' : 'No preview available.'}</p>
            )}
            <Button variant="ghost" icon={<Icon name="logs" />} onClick={onViewRuns}>
              {locale === 'tr' ? 'Artifactları aç' : 'Open artifacts'}
            </Button>
          </>
        ) : (
          <p className="assistant-empty-state">{locale === 'tr' ? 'Seçili run için artifact yok.' : 'No artifacts for the selected run.'}</p>
        )}
      </section>
    </aside>
  );
}
