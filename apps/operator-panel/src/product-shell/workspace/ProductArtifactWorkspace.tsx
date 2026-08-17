import { useEffect, useMemo, useRef, useState } from 'react';

import type { AssistantSessionState } from '../../assistant/assistantTypes';
import { AssistantWorkbench } from '../../components/assistant/AssistantWorkbench';
import { useAssistantArtifactWorkspaceController } from '../../artifact-workspace/useAssistantArtifactWorkspaceController';
import type { ArtifactExportFormat } from '../../artifact-workspace/artifactExportFormats';

type ProductArtifactWorkspaceProps = {
  state: AssistantSessionState;
  openRequest: number;
  requestedArtifactId?: string;
};

/**
 * Product Shell deliberately reuses the governed artifact controller rather
 * than copying an editor or storing artifact state in the renderer.
 */
export function ProductArtifactWorkspace({ state, openRequest, requestedArtifactId }: ProductArtifactWorkspaceProps) {
  const [selectedLegacyArtifactName, setSelectedLegacyArtifactName] = useState('');
  const lastRequestedArtifactId = useRef<string | null>(null);
  const lastOpenRequest = useRef(0);
  const legacyArtifacts = useMemo(
    () => state.referencedArtifacts.map((artifact) => ({
      name: artifact.name,
      summary: artifact.summary,
      value: artifact,
    })),
    [state.referencedArtifacts],
  );
  const workspace = useAssistantArtifactWorkspaceController({
    assistantState: state,
    legacyArtifacts,
    selectedLegacyArtifactName,
    onSelectLegacyArtifact: setSelectedLegacyArtifactName,
  });

  useEffect(() => {
    if (openRequest <= lastOpenRequest.current) return;
    lastOpenRequest.current = openRequest;
    workspace.actions.open();
  }, [openRequest, workspace.actions]);

  useEffect(() => {
    if (!requestedArtifactId || requestedArtifactId === lastRequestedArtifactId.current) return;
    lastRequestedArtifactId.current = requestedArtifactId;
    void workspace.actions.openArtifact(requestedArtifactId);
  }, [requestedArtifactId, workspace.actions]);

  if (!workspace.open) return null;

  const exportArtifact = (artifactId: string, format: ArtifactExportFormat, sheetId?: string) => {
    const kind = workspace.state.tabs.find((tab) => tab.artifact.artifactId === artifactId)?.artifact.kind;
    if (format === 'source' || format === 'txt') void workspace.actions.exportCode(artifactId, format);
    else if (format === 'pptx') void workspace.actions.exportSlides(artifactId);
    else if (format === 'submission-json' || (kind === 'form' && (format === 'json' || format === 'csv'))
      || ((kind === 'document' || kind === 'slides') && format === 'json')) {
      void workspace.actions.exportStructured(artifactId, format);
    } else if (kind === 'canvas' && (format === 'json' || format === 'svg' || format === 'png')) {
      void workspace.actions.exportCanvas(artifactId, format);
    } else if (format === 'json' || format === 'svg' || format === 'png') {
      void workspace.actions.exportFlow(artifactId, format);
    } else if (format === 'csv' || format === 'xlsx') {
      void workspace.actions.exportSpreadsheet(artifactId, format, sheetId);
    } else void workspace.actions.exportDocument(artifactId, format);
  };

  return <AssistantWorkbench
    state={state}
    artifacts={workspace.legacyArtifacts}
    selectedArtifactName={workspace.selectedLegacyArtifactName}
    onSelectArtifact={workspace.actions.selectLegacyArtifact}
    onViewRuns={() => void workspace.actions.loadCatalog()}
    workspaceState={workspace.state}
    catalog={workspace.catalog}
    catalogNextCursor={workspace.catalogNextCursor}
    catalogLoading={workspace.catalogLoading}
    history={workspace.history}
    historyNextCursor={workspace.historyNextCursor}
    historyLoading={Boolean(workspace.historyLoadingArtifactId)}
    comparison={workspace.comparison}
    conflictResolving={workspace.conflictResolving}
    workspaceError={workspace.error}
    operationNotice={workspace.operationNotice}
    formRuntime={workspace.formRuntime}
    onSubmitForm={workspace.actions.submitForm}
    onOpenArtifact={(artifactId) => void workspace.actions.openArtifact(artifactId)}
    onActivateArtifact={workspace.actions.activate}
    onRequestClose={workspace.actions.requestClose}
    onLoadCatalog={() => void workspace.actions.loadCatalog()}
    onLoadMoreCatalog={() => void workspace.actions.loadMoreCatalog()}
    onLoadHistory={(artifactId) => void workspace.actions.loadHistory(artifactId)}
    onLoadMoreHistory={(artifactId) => void workspace.actions.loadMoreHistory(artifactId)}
    onCompareRevision={(artifactId, revisionId) => void workspace.actions.compareRevision(artifactId, revisionId)}
    onCloseComparison={workspace.actions.closeComparison}
    onRefreshConflict={(artifactId) => void workspace.actions.refreshConflict(artifactId)}
    onCompareConflict={workspace.actions.compareConflict}
    onReloadConflict={(artifactId) => void workspace.actions.reloadConflict(artifactId)}
    onForkConflict={(artifactId) => void workspace.actions.forkConflict(artifactId)}
    onEditArtifact={workspace.actions.edit}
    onRetrySave={(artifactId) => void workspace.actions.retrySave(artifactId)}
    onRestoreArtifact={(artifactId, revisionId) => void workspace.actions.restore(artifactId, revisionId)}
    onImportAsset={workspace.actions.importAsset}
    onResolveAsset={workspace.actions.resolveAsset}
    onExportArtifact={exportArtifact}
  />;
}
