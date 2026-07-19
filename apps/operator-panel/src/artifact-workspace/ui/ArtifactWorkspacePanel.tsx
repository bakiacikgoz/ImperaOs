import { useMemo, useRef, useState, type ReactNode } from 'react';

import type { ArtifactDescriptor, ArtifactRevision } from '../artifactContracts';
import type { ArtifactWorkspaceState } from '../workspaceController';
import { Badge } from '../../components/primitives/Badge';
import { Button } from '../../components/primitives/Button';
import { ArtifactExportDialog } from './ArtifactExportDialog';
import { ARTIFACT_EXPORT_FORMATS, type ArtifactExportFormat } from '../artifactExportFormats';

type ExportFormat = ArtifactExportFormat;

function archiveLabel(artifact: ArtifactDescriptor): string | null {
  if (artifact.status !== 'archived') return null;
  if (!artifact.archivedAtUtc) return 'Archived';
  return `Archived ${artifact.archivedAtUtc.slice(0, 10)}`;
}

function metadataLabel(artifact: ArtifactDescriptor, key: string, fallback: string): string {
  const value = artifact.metadata[key];
  return typeof value === 'string' && value.trim() ? value : fallback;
}

export function ArtifactWorkspacePanel({
  workspaceState, catalog = [], history = [], catalogLoading = false, historyLoading = false,
  workspaceError = null, operationNotice = null, onOpenArtifact, onActivateArtifact, onRequestClose,
  onRetrySave, onLoadCatalog, onLoadHistory, onLoadMoreCatalog, onLoadMoreHistory, onCompareRevision,
  onRestoreArtifact, onExportArtifact, onRenderEditor,
}: {
  workspaceState: ArtifactWorkspaceState; catalog?: ArtifactDescriptor[]; history?: ArtifactRevision[];
  catalogLoading?: boolean; historyLoading?: boolean; workspaceError?: { message: string } | null; operationNotice?: string | null;
  onOpenArtifact?: (artifactId: string) => void; onActivateArtifact?: (artifactId: string) => void; onRequestClose?: (artifactId: string) => void;
  onRetrySave?: (artifactId: string) => void; onLoadCatalog?: () => void; onLoadHistory?: (artifactId: string) => void;
  onLoadMoreCatalog?: () => void; onLoadMoreHistory?: (artifactId: string) => void; onCompareRevision?: (artifactId: string, revisionId: string) => void;
  onRestoreArtifact?: (artifactId: string, revisionId: string) => void; onExportArtifact?: (artifactId: string, format: ExportFormat) => void;
  onRenderEditor?: (tab: ArtifactWorkspaceState['tabs'][number]) => ReactNode;
}) {
  const [search, setSearch] = useState('');
  const [kindFilter, setKindFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [exportOpen, setExportOpen] = useState(false);
  const activeTabRef = useRef<HTMLButtonElement>(null);
  const activeTab = workspaceState.tabs.find((tab) => tab.artifact.artifactId === workspaceState.activeArtifactId);
  const filteredCatalog = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return catalog.filter((artifact) => (!needle || artifact.title.toLocaleLowerCase().includes(needle) || artifact.artifactId.toLowerCase().includes(needle))
      && (kindFilter === 'all' || artifact.kind === kindFilter) && (statusFilter === 'all' || artifact.status === statusFilter));
  }, [catalog, kindFilter, search, statusFilter]);
  const exportFormats = activeTab ? ARTIFACT_EXPORT_FORMATS[activeTab.artifact.kind] : [];
  const exportDisabled = !activeTab || activeTab.artifact.status === 'archived' || activeTab.dirty || activeTab.saveState === 'saving' || activeTab.saveState === 'error' || Boolean(activeTab.conflict);

  return <section className="artifact-workspace-panel" aria-label="Artifact workspace">
    <header className="artifact-workspace-panel-head"><h2>Artifact workspace</h2><Button variant="ghost" onClick={onLoadCatalog} disabled={catalogLoading}>{catalogLoading ? 'Loading…' : 'Refresh'}</Button></header>
    {workspaceError ? <p className="artifact-workspace-banner" role="alert">{workspaceError.message}</p> : null}
    {operationNotice ? <p className="artifact-workspace-banner" role="status">{operationNotice}</p> : null}
    <div className="artifact-workspace-filters">
      <input type="search" aria-label="Search artifacts" placeholder="Search title or ID" value={search} onChange={(event) => setSearch(event.target.value)} />
      <select aria-label="Filter artifact kind" value={kindFilter} onChange={(event) => setKindFilter(event.target.value)}><option value="all">All kinds</option>{Object.keys(ARTIFACT_EXPORT_FORMATS).map((kind) => <option key={kind} value={kind}>{kind}</option>)}</select>
      <select aria-label="Filter artifact status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">All states</option>{['draft', 'active', 'archived', 'blocked', 'corrupt'].map((status) => <option key={status} value={status}>{status}</option>)}</select>
    </div>
    <div className="artifact-workspace-navigator" aria-label="Artifact navigator">
      {filteredCatalog.map((artifact) => <button type="button" key={artifact.artifactId} onClick={() => onOpenArtifact?.(artifact.artifactId)}><strong>{artifact.title}</strong><span>{artifact.kind} · {artifact.status} · r{artifact.currentRevisionNumber}</span>{archiveLabel(artifact) ? <span>{archiveLabel(artifact)}</span> : null}</button>)}
      {!filteredCatalog.length ? <p>{catalogLoading ? 'Loading artifacts…' : 'No matching artifacts.'}</p> : null}
    </div>
    {onLoadMoreCatalog ? <Button variant="ghost" onClick={onLoadMoreCatalog} disabled={catalogLoading}>Load more artifacts</Button> : null}
    {workspaceState.tabs.length ? <div className="artifact-workspace-tabs" role="tablist" aria-label="Open artifacts">{workspaceState.tabs.map((tab) => <button className="artifact-workspace-tab-button" key={tab.artifact.artifactId} ref={tab.artifact.artifactId === workspaceState.activeArtifactId ? activeTabRef : undefined} type="button" role="tab" aria-selected={tab.artifact.artifactId === workspaceState.activeArtifactId} onClick={() => onActivateArtifact?.(tab.artifact.artifactId)}>{tab.artifact.title}{tab.dirty ? ' •' : ''}</button>)}</div> : null}
    {activeTab ? <div className="artifact-workspace-active" role="tabpanel">
      <div className="artifact-workspace-status-row" aria-label="Artifact status">
        <Badge tone={activeTab.saveState === 'error' || activeTab.saveState === 'conflict' ? 'error' : activeTab.dirty ? 'warning' : 'success'}>{activeTab.saveState}</Badge><Badge tone="info">Revision {activeTab.revision.revisionNumber}</Badge><Badge>{activeTab.artifact.dataClass}</Badge><Badge>{metadataLabel(activeTab.artifact, 'policyStatus', 'governed')}</Badge>{archiveLabel(activeTab.artifact) ? <Badge tone="warning">{archiveLabel(activeTab.artifact)}</Badge> : null}<button type="button" aria-label={`Close ${activeTab.artifact.title}`} onClick={() => onRequestClose?.(activeTab.artifact.artifactId)}>Close</button>
      </div>
      {activeTab.artifact.status === 'archived' ? <p className="artifact-workspace-banner">Archived artifacts are read-only.</p> : null}
      {activeTab.saveState === 'saving' ? <p className="artifact-workspace-banner" role="status">Saving draft…</p> : null}
      {activeTab.saveState === 'error' ? <div className="artifact-workspace-banner" role="alert"><p>{activeTab.saveError ?? 'Artifact autosave failed.'}</p><Button variant="ghost" onClick={() => onRetrySave?.(activeTab.artifact.artifactId)}>Retry save</Button></div> : null}
      {onRenderEditor?.(activeTab)}
      {exportFormats.length ? <Button variant="ghost" disabled={exportDisabled} onClick={() => setExportOpen(true)}>Export</Button> : null}
      <section className="artifact-workspace-history" aria-label="Revision history"><header><h3>Revision history</h3><Button variant="ghost" disabled={historyLoading} onClick={() => onLoadHistory?.(activeTab.artifact.artifactId)}>Refresh history</Button></header>
        {history.map((item) => <article key={item.revisionId}><strong>Revision {item.revisionNumber}</strong><span>{item.changeSummary || item.mutationType}</span><time dateTime={item.createdAtUtc}>{new Date(item.createdAtUtc).toLocaleString()}</time>{item.revisionId !== activeTab.revision.revisionId ? <div><Button variant="ghost" disabled={historyLoading} aria-label={`Compare revision ${item.revisionNumber}`} onClick={() => onCompareRevision?.(activeTab.artifact.artifactId, item.revisionId)}>Compare</Button><Button variant="ghost" disabled={exportDisabled} aria-label={`Restore revision ${item.revisionNumber}`} onClick={() => onRestoreArtifact?.(activeTab.artifact.artifactId, item.revisionId)}>Restore</Button></div> : null}</article>)}
        {onLoadMoreHistory ? <Button variant="ghost" disabled={historyLoading} onClick={() => onLoadMoreHistory(activeTab.artifact.artifactId)}>Load more history</Button> : null}
      </section>
    </div> : null}
    {exportOpen && activeTab ? <ArtifactExportDialog artifactTitle={activeTab.artifact.title} formats={exportFormats} revisionNumber={activeTab.revision.revisionNumber} dataClass={activeTab.artifact.dataClass} policyState={metadataLabel(activeTab.artifact, 'policyStatus', 'governed')} estimatedSizeBytes={new TextEncoder().encode(JSON.stringify(activeTab.draftContent)).byteLength} securityWarning="Exported files leave workspace governance. Verify the destination and sharing policy." onCancel={() => setExportOpen(false)} onConfirm={(format) => { setExportOpen(false); onExportArtifact?.(activeTab.artifact.artifactId, format as ExportFormat); }} /> : null}
  </section>;
}
