import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';

import type { AssistantSessionState } from '../assistant/assistantTypes';
import { ArtifactAutosaveQueue } from './artifactAutosave';
import { ArtifactBridgeError, artifactBridge as defaultBridge, type ArtifactBridge } from './artifactBridge';
import { compareArtifactContent, type ArtifactDiffResult } from './artifactDiff';
import type { ArtifactAssetReadResult, ArtifactContent, ArtifactDescriptor, ArtifactRevision } from './artifactContracts';
import type { ArtifactFormSubmissionRequest } from './artifactContracts';
import { FormSessionRuntime } from './editors/form/formSessionRuntime';
import { exportCodeArtifact, type CodeArtifactExportFormat } from './artifactCodeExport';
import { exportCanvasArtifact, type CanvasArtifactExportFormat } from './artifactCanvasExport';
import { exportDocumentArtifact, type DocumentArtifactExportFormat } from './artifactDocumentExport';
import { exportFlowArtifact, type FlowArtifactExportFormat } from './artifactFlowExport';
import { exportSpreadsheetArtifact, type SpreadsheetExportFormat } from './artifactSpreadsheetExport';
import { exportSlidesArtifact } from './artifactSlidesExport';
import { exportStructuredArtifact, type StructuredArtifactExportFormat } from './artifactStructuredExport';
import { formSessionKey } from './editors/form/formSessionRuntime';
import { ArtifactWorkspaceController } from './workspaceController';

export type LegacyWorkbenchArtifact = {
  name: string;
  summary?: string;
  value?: unknown;
};

export type ArtifactWorkspaceUiError = {
  code: string;
  message: string;
  retryable: boolean;
};

export type ArtifactRevisionComparison = {
  mode: 'history' | 'conflict';
  artifactId: string;
  selectedRevisionId: string;
  afterRevisionId: string;
  status: 'loading' | 'ready' | 'error';
  beforeRevisionNumber: number | null;
  afterRevisionNumber: number;
  dirtyDraftExcluded: boolean;
  result: ArtifactDiffResult | null;
  error: ArtifactWorkspaceUiError | null;
};

export type ArtifactProposalApplyRequest = {
  proposalId: string;
  artifactId: string;
  approvalId: string;
  baseRevisionNumber: number;
};

export interface AssistantArtifactWorkspaceControllerOptions {
  assistantState: AssistantSessionState;
  legacyArtifacts: LegacyWorkbenchArtifact[];
  selectedLegacyArtifactName: string;
  onSelectLegacyArtifact: (name: string) => void;
  bridge?: ArtifactBridge;
}

function normalizeWorkspaceError(
  error: unknown,
  fallback: ArtifactWorkspaceUiError = {
    code: 'ARTIFACT_WORKSPACE_OPEN_FAILED',
    message: 'The artifact could not be opened.',
    retryable: true,
  },
): ArtifactWorkspaceUiError {
  if (error instanceof ArtifactBridgeError) {
    return {
      code: error.code,
      message: error.message,
      retryable: error.retryable,
    };
  }
  return fallback;
}

function exportOperationNotice(
  outcome: { status: 'cancelled' } | { status: 'exported'; basename: string; sha256: string; sizeBytes: number; exportId?: string },
  format: string,
): string {
  if (outcome.status === 'cancelled') return 'Export cancelled.';
  return `Exported ${outcome.basename} · ${format.toUpperCase()} · ${outcome.sizeBytes} bytes · SHA-256 ${outcome.sha256.slice(0, 12)} · record ${outcome.exportId ?? 'unavailable'}.`;
}

export function useAssistantArtifactWorkspaceController({
  assistantState,
  legacyArtifacts,
  selectedLegacyArtifactName,
  onSelectLegacyArtifact,
  bridge = defaultBridge,
}: AssistantArtifactWorkspaceControllerOptions) {
  const [controller] = useState(() => new ArtifactWorkspaceController(bridge));
  const [autosave] = useState(() => new ArtifactAutosaveQueue(controller, bridge));
  const [formRuntime] = useState(() => new FormSessionRuntime());
  const [open, setOpen] = useState(false);
  const [loadingArtifactId, setLoadingArtifactId] = useState<string | null>(null);
  const [error, setError] = useState<ArtifactWorkspaceUiError | null>(null);
  const [operationNotice, setOperationNotice] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<ArtifactDescriptor[]>([]);
  const [catalogNextCursor, setCatalogNextCursor] = useState<string | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [historyByArtifact, setHistoryByArtifact] = useState<Record<string, ArtifactRevision[]>>({});
  const [historyNextCursor, setHistoryNextCursor] = useState<Record<string, string | null>>({});
  const [historyLoadingArtifactId, setHistoryLoadingArtifactId] = useState<string | null>(null);
  const [comparison, setComparison] = useState<ArtifactRevisionComparison | null>(null);
  const [conflictResolving, setConflictResolving] = useState<{ artifactId: string; action: 'refresh' | 'reload' | 'fork' } | null>(null);
  const comparisonRequestSequence = useRef(0);
  const conflictForkKeys = useRef(new Map<string, string>());
  const workspaceEpoch = useRef(0);
  const openRef = useRef(false);
  const state = useSyncExternalStore(
    useCallback((listener) => controller.subscribe(listener), [controller]),
    useCallback(() => controller.getState(), [controller]),
    useCallback(() => controller.getState(), [controller]),
  );

  const invalidateComparison = useCallback(() => {
    comparisonRequestSequence.current += 1;
    setComparison(null);
  }, []);

  useEffect(() => () => autosave.dispose(), [autosave]);

  useEffect(() => {
    if (!comparison) return;
    const tab = state.tabs.find((candidate) => candidate.artifact.artifactId === comparison.artifactId);
    if (!tab || tab.revision.revisionId !== comparison.afterRevisionId) invalidateComparison();
  }, [comparison, invalidateComparison, state.tabs]);

  const loadCatalog = useCallback(
    async (append = false) => {
      const requestEpoch = workspaceEpoch.current;
      setCatalogLoading(true);
      setError(null);
      setOperationNotice(null);
      try {
        const result = await bridge.list({
          cursor: append ? catalogNextCursor ?? undefined : undefined,
          limit: 50,
        });
        if (requestEpoch !== workspaceEpoch.current) return;
        setCatalog((previous) => (append ? [...previous, ...result.items] : result.items));
        setCatalogNextCursor(result.nextCursor);
      } catch (caught) {
        if (requestEpoch !== workspaceEpoch.current) return;
        setError(normalizeWorkspaceError(caught));
      } finally {
        if (requestEpoch === workspaceEpoch.current) setCatalogLoading(false);
      }
    },
    [bridge, catalogNextCursor],
  );

  const loadHistory = useCallback(
    async (artifactId: string, append = false) => {
      const requestEpoch = workspaceEpoch.current;
      setHistoryLoadingArtifactId(artifactId);
      setError(null);
      setOperationNotice(null);
      try {
        const result = await bridge.history({
          artifactId,
          cursor: append ? historyNextCursor[artifactId] ?? undefined : undefined,
          limit: 50,
        });
        if (requestEpoch !== workspaceEpoch.current) return;
        setHistoryByArtifact((previous) => {
          const combined = append ? [...(previous[artifactId] ?? []), ...result.items] : result.items;
          const seen = new Set<string>();
          return {
            ...previous,
            [artifactId]: combined.filter((revision) => {
              if (seen.has(revision.revisionId)) return false;
              seen.add(revision.revisionId);
              return true;
            }),
          };
        });
        setHistoryNextCursor((previous) => ({ ...previous, [artifactId]: result.nextCursor }));
      } catch (caught) {
        if (requestEpoch !== workspaceEpoch.current) return;
        setError(normalizeWorkspaceError(caught));
      } finally {
        if (requestEpoch === workspaceEpoch.current) setHistoryLoadingArtifactId(null);
      }
    },
    [bridge, historyNextCursor],
  );

  const openArtifact = useCallback(
    async (artifactId: string, revealWorkbench = true) => {
      invalidateComparison();
      if (revealWorkbench) setOpen(true);
      if (controller.getState().tabs.some((tab) => tab.artifact.artifactId === artifactId)) {
        controller.activate(artifactId);
        await loadHistory(artifactId, false);
        return;
      }
      setLoadingArtifactId(artifactId);
      setError(null);
      setOperationNotice(null);
      try {
        await controller.open(artifactId);
        await loadHistory(artifactId, false);
      } catch (caught) {
        setError(normalizeWorkspaceError(caught));
      } finally {
        setLoadingArtifactId(null);
      }
    },
    [controller, invalidateComparison, loadHistory],
  );

  const edit = useCallback(
    (artifactId: string, content: ArtifactContent) => autosave.schedule(artifactId, content),
    [autosave],
  );

  const compareRevision = useCallback(
    async (artifactId: string, revisionId: string) => {
      const tab = controller.getState().tabs.find((candidate) => candidate.artifact.artifactId === artifactId);
      if (!tab) return;
      const requestSequence = ++comparisonRequestSequence.current;
      setComparison({
        mode: 'history',
        artifactId,
        selectedRevisionId: revisionId,
        afterRevisionId: tab.revision.revisionId,
        status: 'loading',
        beforeRevisionNumber: null,
        afterRevisionNumber: tab.revision.revisionNumber,
        dirtyDraftExcluded: tab.dirty,
        result: null,
        error: null,
      });
      try {
        const historical = await bridge.get({ artifactId, revisionId });
        if (requestSequence !== comparisonRequestSequence.current) return;
        if (
          historical.artifact.artifactId !== artifactId ||
          historical.revision.artifactId !== artifactId ||
          historical.revision.revisionId !== revisionId
        ) {
          throw new Error('Historical revision identity mismatch.');
        }
        const current = controller.getState().tabs.find((candidate) => candidate.artifact.artifactId === artifactId);
        if (!current || current.artifact.kind !== historical.artifact.kind) {
          throw new Error('Artifact comparison context changed.');
        }
        if (current.revision.revisionId !== tab.revision.revisionId) {
          throw new Error('Artifact comparison context changed.');
        }
        setComparison({
          mode: 'history',
          artifactId,
          selectedRevisionId: revisionId,
          afterRevisionId: current.revision.revisionId,
          status: 'ready',
          beforeRevisionNumber: historical.revision.revisionNumber,
          afterRevisionNumber: current.revision.revisionNumber,
          dirtyDraftExcluded: current.dirty,
          result: compareArtifactContent(historical.content, current.persistedContent),
          error: null,
        });
      } catch (caught) {
        if (requestSequence !== comparisonRequestSequence.current) return;
        setComparison({
          mode: 'history',
          artifactId,
          selectedRevisionId: revisionId,
          afterRevisionId: tab.revision.revisionId,
          status: 'error',
          beforeRevisionNumber: null,
          afterRevisionNumber: tab.revision.revisionNumber,
          dirtyDraftExcluded: tab.dirty,
          result: null,
          error: normalizeWorkspaceError(caught, {
            code: 'ARTIFACT_COMPARISON_FAILED',
            message: 'The selected revisions could not be compared.',
            retryable: true,
          }),
        });
      }
    },
    [bridge, controller],
  );

  const closeComparison = useCallback(() => {
    invalidateComparison();
  }, [invalidateComparison]);

  const compareConflict = useCallback((artifactId: string) => {
    invalidateComparison();
    try {
      const { remote, local } = controller.getConflictComparison(artifactId);
      const tab = controller.getState().tabs.find((candidate) => candidate.artifact.artifactId === artifactId);
      if (!tab) throw new Error('Artifact tab is not open.');
      setComparison({
        mode: 'conflict',
        artifactId,
        selectedRevisionId: remote.revision.revisionId,
        afterRevisionId: tab.revision.revisionId,
        status: 'ready',
        beforeRevisionNumber: remote.revision.revisionNumber,
        afterRevisionNumber: tab.revision.revisionNumber,
        dirtyDraftExcluded: false,
        result: compareArtifactContent(remote.content, local),
        error: null,
      });
    } catch (caught) {
      setError(normalizeWorkspaceError(caught, {
        code: 'ARTIFACT_CONFLICT_COMPARISON_FAILED',
        message: 'The remote revision and local draft could not be compared.',
        retryable: true,
      }));
    }
  }, [controller, invalidateComparison]);

  const refreshConflict = useCallback(async (artifactId: string) => {
    const requestEpoch = workspaceEpoch.current;
    invalidateComparison();
    setConflictResolving({ artifactId, action: 'refresh' });
    setError(null);
    try {
      await controller.refreshConflict(artifactId);
      if (requestEpoch !== workspaceEpoch.current) return;
    } finally {
      if (requestEpoch === workspaceEpoch.current) setConflictResolving(null);
    }
  }, [controller, invalidateComparison]);

  const reloadConflict = useCallback(async (artifactId: string) => {
    const requestEpoch = workspaceEpoch.current;
    invalidateComparison();
    setConflictResolving({ artifactId, action: 'reload' });
    setError(null);
    try {
      const outcome = await controller.reloadConflict(artifactId);
      if (requestEpoch !== workspaceEpoch.current) return;
      if (outcome === 'remote_advanced') {
        setOperationNotice('The remote revision changed again. Review it before reloading.');
        return;
      }
      autosave.resolveConflict(artifactId);
      await loadHistory(artifactId, false);
      if (requestEpoch !== workspaceEpoch.current) return;
      setOperationNotice('Latest remote revision loaded. Local draft was discarded.');
    } catch (caught) {
      if (requestEpoch !== workspaceEpoch.current) return;
      setError(normalizeWorkspaceError(caught, {
        code: 'ARTIFACT_CONFLICT_RELOAD_FAILED',
        message: 'The latest remote revision could not be loaded.',
        retryable: true,
      }));
    } finally {
      if (requestEpoch === workspaceEpoch.current) setConflictResolving(null);
    }
  }, [autosave, controller, invalidateComparison, loadHistory]);

  const forkConflict = useCallback(async (artifactId: string) => {
    const requestEpoch = workspaceEpoch.current;
    invalidateComparison();
    setConflictResolving({ artifactId, action: 'fork' });
    setError(null);
    try {
      const tab = controller.getState().tabs.find((candidate) => candidate.artifact.artifactId === artifactId);
      if (!tab) throw new Error('Artifact tab is not open.');
      if (!tab.conflict) throw new Error('Artifact is not conflicted.');
      const logicalFork = `${artifactId}:${tab.conflict.baseRevisionId}`;
      const idempotencyKey = conflictForkKeys.current.get(logicalFork)
        ?? `fork-${artifactId.slice(0, 40)}-${tab.conflict.baseRevisionId.slice(0, 40)}-${globalThis.crypto.randomUUID()}`;
      conflictForkKeys.current.set(logicalFork, idempotencyKey);
      const outcome = await controller.forkConflict(artifactId, `${tab.artifact.title} (local draft)`, idempotencyKey);
      if (requestEpoch !== workspaceEpoch.current) return;
      conflictForkKeys.current.delete(logicalFork);
      if (outcome.originalResolved) autosave.resolveConflict(artifactId);
      await loadCatalog(false);
      if (requestEpoch !== workspaceEpoch.current) return;
      await loadHistory(outcome.forkId, false);
      if (requestEpoch !== workspaceEpoch.current) return;
      setOperationNotice(outcome.originalResolved
        ? 'Local draft forked into a new artifact.'
        : 'The captured draft was forked. A newer local draft remains preserved on the original artifact.');
    } catch (caught) {
      if (requestEpoch !== workspaceEpoch.current) return;
      setError(normalizeWorkspaceError(caught, {
        code: 'ARTIFACT_CONFLICT_FORK_FAILED',
        message: 'The local draft could not be forked.',
        retryable: true,
      }));
    } finally {
      if (requestEpoch === workspaceEpoch.current) setConflictResolving(null);
    }
  }, [autosave, controller, invalidateComparison, loadCatalog, loadHistory]);

  const restoreArtifact = useCallback(
    async (artifactId: string, revisionId: string) => {
      invalidateComparison();
      setError(null);
      setOperationNotice(null);
      try {
        await autosave.flush(artifactId);
        const current = controller.getState().tabs.find((tab) => tab.artifact.artifactId === artifactId);
        if (!current || current.dirty || current.saveState === 'error' || current.saveState === 'conflict') {
          throw new Error('Artifact must be saved before restoring history.');
        }
        if (current.artifact.status === 'archived') throw new Error('Archived artifacts are read-only.');
        const idempotencyKey = `restore:${artifactId}:${revisionId}:${globalThis.crypto.randomUUID()}`;
        await controller.restore(artifactId, revisionId, idempotencyKey);
        await loadHistory(artifactId, false);
        setOperationNotice('Revision restored.');
      } catch (caught) {
        setError(normalizeWorkspaceError(caught, {
          code: 'ARTIFACT_RESTORE_FAILED',
          message: 'The revision could not be restored.',
          retryable: true,
        }));
      }
    },
    [autosave, controller, invalidateComparison, loadHistory],
  );

  const applyProposal = useCallback(
    async (proposal: ArtifactProposalApplyRequest) => {
      invalidateComparison();
      setError(null);
      setOperationNotice(null);
      try {
        if (controller.getState().tabs.some((tab) => tab.artifact.artifactId === proposal.artifactId)) {
          await autosave.flush(proposal.artifactId);
          const tab = controller.getState().tabs.find((candidate) => candidate.artifact.artifactId === proposal.artifactId);
          if (!tab || tab.dirty || tab.saveState === 'saving' || tab.saveState === 'error' || tab.saveState === 'conflict') {
            throw new ArtifactBridgeError(
              'ARTIFACT_PROPOSAL_DIRTY',
              'Save or resolve the artifact draft before applying this proposal.',
              true,
              'bridge_artifact_apply_proposal',
            );
          }
          if (tab.revision.revisionNumber !== proposal.baseRevisionNumber) {
            throw new ArtifactBridgeError(
              'ARTIFACT_PROPOSAL_STALE',
              'Proposal base revision is stale. Review a new proposal before applying changes.',
              false,
              'bridge_artifact_apply_proposal',
            );
          }
        }
        const operation = await bridge.applyProposal({
          proposalId: proposal.proposalId,
          expectedRevisionNumber: proposal.baseRevisionNumber,
          approvalId: proposal.approvalId,
        });
        if (operation.artifact.artifactId !== proposal.artifactId) {
          throw new Error('Applied proposal returned a different artifact.');
        }
        await controller.open(proposal.artifactId);
        await loadHistory(proposal.artifactId, false);
        setOpen(true);
        setOperationNotice('Approved proposal applied.');
        return operation;
      } catch (caught) {
        setError(normalizeWorkspaceError(caught, {
          code: 'ARTIFACT_PROPOSAL_APPLY_FAILED',
          message: 'The approved proposal could not be applied.',
          retryable: true,
        }));
        throw caught;
      }
    },
    [autosave, bridge, controller, invalidateComparison, loadHistory],
  );

  const exportDocument = useCallback(
    async (artifactId: string, format: DocumentArtifactExportFormat) => {
      setError(null);
      setOperationNotice(null);
      try {
        await autosave.flush(artifactId);
        const tab = controller.getState().tabs.find((candidate) => candidate.artifact.artifactId === artifactId);
        if (!tab) throw new Error('Artifact tab is not open.');
        if (tab.dirty || tab.saveState === 'error' || tab.saveState === 'conflict') {
          throw new Error('Artifact must be saved before export.');
        }
        const outcome = await exportDocumentArtifact({
          artifact: tab.artifact,
          revision: tab.revision,
          content: tab.draftContent,
          format,
          bridge,
        });
        setOperationNotice(exportOperationNotice(outcome, format));
        return outcome;
      } catch (caught) {
        setError(normalizeWorkspaceError(caught, {
          code: 'ARTIFACT_EXPORT_FAILED',
          message: 'The document could not be exported.',
          retryable: true,
        }));
        return null;
      }
    },
    [autosave, bridge, controller],
  );

  const exportCode = useCallback(async (artifactId: string, format: CodeArtifactExportFormat) => {
    setError(null);
    setOperationNotice(null);
    try {
      await autosave.flush(artifactId);
      const tab = controller.getState().tabs.find((candidate) => candidate.artifact.artifactId === artifactId);
      if (!tab) throw new Error('Artifact tab is not open.');
      if (tab.dirty || tab.saveState === 'error' || tab.saveState === 'conflict') {
        throw new Error('Artifact must be saved before export.');
      }
      const outcome = await exportCodeArtifact({
        artifact: tab.artifact,
        revision: tab.revision,
        content: tab.draftContent,
        bridge, format,
      });
      setOperationNotice(exportOperationNotice(outcome, format));
      return outcome;
    } catch (caught) {
      setError(normalizeWorkspaceError(caught, {
        code: 'ARTIFACT_EXPORT_FAILED',
        message: 'The source could not be exported.',
        retryable: true,
      }));
      return null;
    }
  }, [autosave, bridge, controller]);

  const exportFlow = useCallback(async (artifactId: string, format: FlowArtifactExportFormat) => {
    setError(null);
    setOperationNotice(null);
    try {
      await autosave.flush(artifactId);
      const tab = controller.getState().tabs.find((candidate) => candidate.artifact.artifactId === artifactId);
      if (!tab) throw new Error('Artifact tab is not open.');
      if (tab.dirty || tab.saveState === 'error' || tab.saveState === 'conflict') {
        throw new Error('Artifact must be saved before export.');
      }
      const outcome = await exportFlowArtifact({
        artifact: tab.artifact,
        revision: tab.revision,
        content: tab.draftContent,
        format,
        bridge,
      });
      setOperationNotice(exportOperationNotice(outcome, format));
      return outcome;
    } catch (caught) {
      setError(normalizeWorkspaceError(caught, {
        code: 'ARTIFACT_EXPORT_FAILED',
        message: 'The flow could not be exported.',
        retryable: true,
      }));
      return null;
    }
  }, [autosave, bridge, controller]);

  const exportSpreadsheet = useCallback(async (
    artifactId: string,
    format: SpreadsheetExportFormat,
    sheetId?: string,
  ) => {
    setError(null);
    setOperationNotice(null);
    try {
      await autosave.flush(artifactId);
      const tab = controller.getState().tabs.find((candidate) => candidate.artifact.artifactId === artifactId);
      if (!tab) throw new Error('Artifact tab is not open.');
      if (tab.dirty || tab.saveState === 'error' || tab.saveState === 'conflict') {
        throw new Error('Artifact must be saved before export.');
      }
      const outcome = await exportSpreadsheetArtifact({
        artifact: tab.artifact,
        revision: tab.revision,
        content: tab.draftContent,
        format,
        sheetId,
        bridge,
      });
      setOperationNotice(exportOperationNotice(outcome, format));
      return outcome;
    } catch (caught) {
      setError(normalizeWorkspaceError(caught, {
        code: 'ARTIFACT_EXPORT_FAILED',
        message: 'The spreadsheet could not be exported.',
        retryable: true,
      }));
      return null;
    }
  }, [autosave, bridge, controller]);

  const exportCanvas = useCallback(async (artifactId: string, format: CanvasArtifactExportFormat) => {
    setError(null);
    setOperationNotice(null);
    try {
      await autosave.flush(artifactId);
      const tab = controller.getState().tabs.find((candidate) => candidate.artifact.artifactId === artifactId);
      if (!tab) throw new Error('Artifact tab is not open.');
      if (tab.dirty || tab.saveState === 'error' || tab.saveState === 'conflict') {
        throw new Error('Artifact must be saved before export.');
      }
      const outcome = await exportCanvasArtifact({
        artifact: tab.artifact,
        revision: tab.revision,
        content: tab.draftContent,
        format,
        bridge,
      });
      setOperationNotice(exportOperationNotice(outcome, format));
      return outcome;
    } catch (caught) {
      setError(normalizeWorkspaceError(caught, {
        code: 'ARTIFACT_EXPORT_FAILED',
        message: 'The canvas could not be exported.',
        retryable: true,
      }));
      return null;
    }
  }, [autosave, bridge, controller]);

  const exportSlides = useCallback(async (artifactId: string) => {
    setError(null);
    setOperationNotice(null);
    try {
      await autosave.flush(artifactId);
      const tab = controller.getState().tabs.find((candidate) => candidate.artifact.artifactId === artifactId);
      if (!tab) throw new Error('Artifact tab is not open.');
      if (tab.dirty || tab.saveState === 'error' || tab.saveState === 'conflict') {
        throw new Error('Artifact must be saved before export.');
      }
      const outcome = await exportSlidesArtifact({
        artifact: tab.artifact, revision: tab.revision, content: tab.draftContent, bridge,
      });
      setOperationNotice(exportOperationNotice(outcome, 'pptx'));
      return outcome;
    } catch (caught) {
      setError(normalizeWorkspaceError(caught, {
        code: 'ARTIFACT_EXPORT_FAILED', message: 'The slide deck could not be exported.', retryable: true,
      }));
      return null;
    }
  }, [autosave, bridge, controller]);

  const exportStructured = useCallback(async (artifactId: string, format: StructuredArtifactExportFormat) => {
    setError(null);
    setOperationNotice(null);
    try {
      await autosave.flush(artifactId);
      const tab = controller.getState().tabs.find((candidate) => candidate.artifact.artifactId === artifactId);
      if (!tab) throw new Error('Artifact tab is not open.');
      if (tab.dirty || tab.saveState === 'error' || tab.saveState === 'conflict') {
        throw new Error('Artifact must be saved before export.');
      }
      const submission = tab.artifact.kind === 'form'
        ? formRuntime.getSnapshot(formSessionKey(tab.artifact.artifactId, tab.revision.revisionId)).formData
        : undefined;
      const outcome = await exportStructuredArtifact({
        artifact: tab.artifact, revision: tab.revision, content: tab.draftContent, format, submission, bridge,
      });
      setOperationNotice(exportOperationNotice(outcome, format));
      return outcome;
    } catch (caught) {
      setError(normalizeWorkspaceError(caught, {
        code: 'ARTIFACT_EXPORT_FAILED', message: 'The structured artifact could not be exported.', retryable: true,
      }));
      return null;
    }
  }, [autosave, bridge, controller, formRuntime]);

  const importAsset = useCallback(async (artifactId: string) => {
    setError(null);
    setOperationNotice(null);
    try {
      const tab = controller.getState().tabs.find(
        (candidate) => candidate.artifact.artifactId === artifactId,
      );
      if (!tab || tab.artifact.status === 'archived') {
        throw new Error('Asset import requires an editable artifact.');
      }
      const selected = await bridge.selectAsset();
      if (selected.cancelled || !selected.ticket) return null;
      const imported = await bridge.importAsset({
        ticket: selected.ticket,
        dataClass: tab.artifact.dataClass,
        idempotencyKey: `asset-${artifactId.slice(0, 48)}-${globalThis.crypto.randomUUID()}`,
      });
      setOperationNotice(
        imported.disposition === 'deduplicated'
          ? 'Existing governed asset reused.'
          : 'Local asset imported.',
      );
      return imported.asset;
    } catch (caught) {
      setError(normalizeWorkspaceError(caught, {
        code: 'ARTIFACT_ASSET_UNSAFE',
        message: 'The local asset could not be imported safely.',
        retryable: false,
      }));
      return null;
    }
  }, [bridge, controller]);

  const resolveAsset = useCallback(async (assetId: string): Promise<ArtifactAssetReadResult | null> => {
    try {
      return await bridge.getAsset(assetId);
    } catch (caught) {
      setError(normalizeWorkspaceError(caught, {
        code: 'ARTIFACT_ASSET_UNSAFE',
        message: 'The governed local asset could not be loaded.',
        retryable: true,
      }));
      return null;
    }
  }, [bridge]);

  const submitForm = useCallback(async (request: ArtifactFormSubmissionRequest) => {
    setError(null);
    setOperationNotice(null);
    try {
      const result = await bridge.submitForm(request);
      setOperationNotice(result.status === 'pending_continuation'
        ? 'Form submitted. External continuation is awaiting approval.'
        : 'Form submitted.');
      return result;
    } catch (caught) {
      setError(normalizeWorkspaceError(caught, {
        code: 'FORM_SUBMISSION_FAILED',
        message: 'The form could not be submitted.',
        retryable: true,
      }));
      throw caught;
    }
  }, [bridge]);

  const reset = useCallback(() => {
    workspaceEpoch.current += 1;
    autosave.dispose();
    formRuntime.resetAll();
    controller.getState().tabs.forEach((tab) => controller.discardAndClose(tab.artifact.artifactId));
    openRef.current = false;
    setOpen(false);
    setLoadingArtifactId(null);
    setError(null);
    setOperationNotice(null);
    setCatalog([]);
    setCatalogNextCursor(null);
    setCatalogLoading(false);
    setHistoryByArtifact({});
    setHistoryNextCursor({});
    setHistoryLoadingArtifactId(null);
    conflictForkKeys.current.clear();
    setConflictResolving(null);
    invalidateComparison();
  }, [autosave, controller, formRuntime, invalidateComparison]);

  const openWorkspace = useCallback(() => {
    if (openRef.current) return;
    openRef.current = true;
    if (catalog.length === 0 && !catalogLoading) void loadCatalog(false);
    setOpen(true);
  }, [catalog.length, catalogLoading, loadCatalog]);

  const toggle = useCallback(() => {
    const nextOpen = !openRef.current;
    openRef.current = nextOpen;
    if (nextOpen && catalog.length === 0 && !catalogLoading) void loadCatalog(false);
    setOpen(nextOpen);
  }, [catalog.length, catalogLoading, loadCatalog]);

  const actions = useMemo(
    () => ({
      open: openWorkspace,
      toggle,
      reset,
      selectLegacyArtifact: onSelectLegacyArtifact,
      openArtifact,
      openInlineArtifact: (artifactId: string) => openArtifact(artifactId, false),
      activate: (artifactId: string) => {
        invalidateComparison();
        controller.activate(artifactId);
      },
      edit,
      compareRevision,
      compareConflict,
      closeComparison,
      refreshConflict,
      reloadConflict,
      forkConflict,
      flush: (artifactId?: string) => autosave.flush(artifactId),
      retrySave: (artifactId: string) => autosave.retry(artifactId),
      requestClose: (artifactId: string) => {
        controller.requestClose(artifactId);
        if (!controller.getState().tabs.some((tab) => tab.artifact.artifactId === artifactId)) {
          formRuntime.resetArtifact(artifactId);
        }
      },
      cancelClose: () => controller.cancelClose(),
      discardAndClose: (artifactId: string) => {
        workspaceEpoch.current += 1;
        autosave.retire(artifactId);
        formRuntime.resetArtifact(artifactId);
        controller.discardAndClose(artifactId);
      },
      restore: restoreArtifact,
      applyProposal,
        exportDocument,
        exportCode,
        exportFlow,
        exportSpreadsheet,
        exportCanvas,
        exportSlides,
        exportStructured,
        importAsset,
        resolveAsset,
        submitForm,
      archive: (artifactId: string) => controller.archive(artifactId),
      clearError: () => setError(null),
      clearOperationNotice: () => setOperationNotice(null),
      loadCatalog: () => loadCatalog(false),
      loadMoreCatalog: () => loadCatalog(true),
      loadHistory: (artifactId: string) => loadHistory(artifactId, false),
      loadMoreHistory: (artifactId: string) => loadHistory(artifactId, true),
    }),
    [applyProposal, autosave, closeComparison, compareConflict, compareRevision, controller, edit, exportCanvas, exportCode, exportDocument, exportFlow, exportSlides, exportSpreadsheet, exportStructured, formRuntime, forkConflict, importAsset, invalidateComparison, loadCatalog, loadHistory, onSelectLegacyArtifact, openArtifact, openWorkspace, refreshConflict, reloadConflict, reset, resolveAsset, restoreArtifact, submitForm, toggle],
  );

  const activeTab =
    state.tabs.find((tab) => tab.artifact.artifactId === state.activeArtifactId) ?? null;
  const available =
    assistantState.turns.length > 0 ||
    assistantState.referencedArtifacts.length > 0 ||
    legacyArtifacts.length > 0 ||
    state.tabs.length > 0;
  const visibleComparison = comparison
    && activeTab?.artifact.artifactId === comparison.artifactId
    && activeTab.revision.revisionId === comparison.afterRevisionId
    ? comparison
    : null;

  return {
    open,
    available,
    state,
    activeTab,
    loadingArtifactId,
    error,
    operationNotice,
    legacyArtifacts,
    selectedLegacyArtifactName,
    catalog,
    catalogNextCursor,
    catalogLoading,
    history: activeTab ? historyByArtifact[activeTab.artifact.artifactId] ?? [] : [],
    historyNextCursor: activeTab ? historyNextCursor[activeTab.artifact.artifactId] ?? null : null,
    historyLoadingArtifactId,
    comparison: visibleComparison,
    conflictResolving,
    formRuntime,
    actions,
  };
}
