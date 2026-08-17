import { artifactBridge as defaultBridge, type ArtifactBridge } from './artifactBridge';
import type {
  ArtifactContent,
  ArtifactDescriptor,
  ArtifactOperationResult,
  ArtifactReadResult,
  ArtifactRevision,
} from './artifactContracts';


export type ArtifactSaveState = 'idle' | 'dirty' | 'saving' | 'saved' | 'error' | 'conflict';

export interface ArtifactConflict {
  status: 'loading' | 'ready' | 'error';
  baseRevisionNumber: number;
  baseRevisionId: string;
  remote: ArtifactReadResult | null;
  error: string | null;
  detectedAtUtc: string;
}

export interface ArtifactWorkspaceTab {
  artifact: ArtifactDescriptor;
  revision: ArtifactRevision;
  persistedContent: ArtifactContent;
  draftContent: ArtifactContent;
  dirty: boolean;
  saveState: ArtifactSaveState;
  saveError: string | null;
  conflict: ArtifactConflict | null;
}

export interface ArtifactWorkspaceState {
  tabs: ArtifactWorkspaceTab[];
  activeArtifactId: string | null;
  closeGuard: { artifactId: string; reason: 'dirty' | 'saving' } | null;
}

export type ArtifactWorkspaceAction =
  | { type: 'opened'; result: ArtifactReadResult }
  | { type: 'activated'; artifactId: string }
  | { type: 'edited'; artifactId: string; content: ArtifactContent }
  | { type: 'saveStarted'; artifactId: string }
  | {
      type: 'saveSucceeded';
      artifactId: string;
      operation: ArtifactOperationResult;
      content: ArtifactContent;
    }
  | { type: 'saveFailed'; artifactId: string; message: string }
  | { type: 'saveNoop'; artifactId: string }
  | { type: 'saveConflictDetected'; artifactId: string }
  | { type: 'saveConflicted'; artifactId: string; remote: ArtifactReadResult }
  | { type: 'saveConflictLoadFailed'; artifactId: string; message: string }
  | { type: 'conflictReloaded'; artifactId: string; remote: ArtifactReadResult }
  | { type: 'conflictForked'; artifactId: string; remote: ArtifactReadResult; fork: ArtifactReadResult }
  | { type: 'conflictForkOpened'; fork: ArtifactReadResult }
  | { type: 'metadataUpdated'; operation: ArtifactOperationResult }
  | { type: 'closeRequested'; artifactId: string }
  | { type: 'closeCancelled' }
  | { type: 'closeDiscarded'; artifactId: string };

export function createArtifactWorkspaceState(): ArtifactWorkspaceState {
  return { tabs: [], activeArtifactId: null, closeGuard: null };
}

function tabFromRead(result: ArtifactReadResult): ArtifactWorkspaceTab {
  return {
    artifact: result.artifact,
    revision: result.revision,
    persistedContent: result.content,
    draftContent: result.content,
    dirty: false,
    saveState: 'idle',
    saveError: null,
    conflict: null,
  };
}

function replaceTab(
  state: ArtifactWorkspaceState,
  artifactId: string,
  update: (tab: ArtifactWorkspaceTab) => ArtifactWorkspaceTab,
): ArtifactWorkspaceState {
  if (!state.tabs.some((tab) => tab.artifact.artifactId === artifactId)) {
    return state;
  }
  return {
    ...state,
    tabs: state.tabs.map((tab) => (tab.artifact.artifactId === artifactId ? update(tab) : tab)),
  };
}

function closeTab(state: ArtifactWorkspaceState, artifactId: string): ArtifactWorkspaceState {
  const index = state.tabs.findIndex((tab) => tab.artifact.artifactId === artifactId);
  if (index < 0) {
    return { ...state, closeGuard: null };
  }
  const tabs = state.tabs.filter((tab) => tab.artifact.artifactId !== artifactId);
  const activeArtifactId =
    state.activeArtifactId === artifactId
      ? (tabs[Math.min(index, tabs.length - 1)]?.artifact.artifactId ?? null)
      : state.activeArtifactId;
  return { tabs, activeArtifactId, closeGuard: null };
}

export function artifactWorkspaceReducer(
  state: ArtifactWorkspaceState,
  action: ArtifactWorkspaceAction,
): ArtifactWorkspaceState {
  switch (action.type) {
    case 'opened': {
      const artifactId = action.result.artifact.artifactId;
      const tab = tabFromRead(action.result);
      const exists = state.tabs.some((item) => item.artifact.artifactId === artifactId);
      return {
        ...state,
        tabs: exists
          ? state.tabs.map((item) => (item.artifact.artifactId === artifactId ? tab : item))
          : [...state.tabs, tab],
        activeArtifactId: artifactId,
        closeGuard: null,
      };
    }
    case 'activated':
      return state.tabs.some((tab) => tab.artifact.artifactId === action.artifactId)
        ? { ...state, activeArtifactId: action.artifactId }
        : state;
    case 'edited':
      return replaceTab(state, action.artifactId, (tab) => ({
        ...tab,
        draftContent: action.content,
        dirty: true,
        saveState: tab.conflict ? 'conflict' : 'dirty',
        saveError: null,
        conflict: tab.conflict,
      }));
    case 'saveStarted':
      return replaceTab(state, action.artifactId, (tab) => tab.conflict ? tab : ({
        ...tab, saveState: 'saving', saveError: null,
      }));
    case 'saveSucceeded':
      return replaceTab(state, action.artifactId, (tab) => {
        if (tab.conflict) return tab;
        const hasNewerDraft = tab.draftContent !== action.content;
        return {
          ...tab,
          artifact: action.operation.artifact,
          revision: action.operation.revision,
          persistedContent: action.content,
          draftContent: hasNewerDraft ? tab.draftContent : action.content,
          dirty: hasNewerDraft,
          saveState: hasNewerDraft
            ? 'dirty'
            : action.operation.disposition === 'no_op'
              ? 'idle'
              : 'saved',
          saveError: null,
          conflict: null,
        };
      });
    case 'saveFailed':
      return replaceTab(state, action.artifactId, (tab) => ({
        ...tab,
        dirty: true,
        saveState: 'error',
        saveError: action.message,
      }));
    case 'saveNoop':
      return replaceTab(state, action.artifactId, (tab) => tab.conflict ? tab : ({
        ...tab,
        persistedContent: tab.draftContent,
        dirty: false,
        saveState: 'idle',
        saveError: null,
        conflict: null,
      }));
    case 'saveConflictDetected':
      return replaceTab(state, action.artifactId, (tab) => ({
        ...tab,
        dirty: true,
        saveState: 'conflict',
        saveError: null,
        conflict: {
          status: 'loading',
          baseRevisionNumber: tab.revision.revisionNumber,
          baseRevisionId: tab.revision.revisionId,
          remote: null,
          error: null,
          detectedAtUtc: tab.conflict?.detectedAtUtc ?? new Date().toISOString(),
        },
      }));
    case 'saveConflicted':
      return replaceTab(state, action.artifactId, (tab) => ({
        ...tab,
        dirty: true,
        saveState: 'conflict',
        saveError: null,
        conflict: {
          status: 'ready',
          baseRevisionNumber: tab.conflict?.baseRevisionNumber ?? tab.revision.revisionNumber,
          baseRevisionId: tab.conflict?.baseRevisionId ?? tab.revision.revisionId,
          remote: action.remote,
          error: null,
          detectedAtUtc: tab.conflict?.detectedAtUtc ?? new Date().toISOString(),
        },
      }));
    case 'saveConflictLoadFailed':
      return replaceTab(state, action.artifactId, (tab) => ({
        ...tab,
        dirty: true,
        saveState: 'conflict',
        saveError: null,
        conflict: {
          status: 'error',
          baseRevisionNumber: tab.conflict?.baseRevisionNumber ?? tab.revision.revisionNumber,
          baseRevisionId: tab.conflict?.baseRevisionId ?? tab.revision.revisionId,
          remote: null,
          error: action.message,
          detectedAtUtc: tab.conflict?.detectedAtUtc ?? new Date().toISOString(),
        },
      }));
    case 'conflictReloaded':
      return replaceTab(state, action.artifactId, () => tabFromRead(action.remote));
    case 'conflictForked': {
      const original = tabFromRead(action.remote);
      const fork = tabFromRead(action.fork);
      const tabs = state.tabs
        .map((tab) => tab.artifact.artifactId === action.artifactId ? original : tab)
        .filter((tab) => tab.artifact.artifactId !== fork.artifact.artifactId);
      return { ...state, tabs: [...tabs, fork], activeArtifactId: fork.artifact.artifactId, closeGuard: null };
    }
    case 'conflictForkOpened': {
      const fork = tabFromRead(action.fork);
      const tabs = state.tabs.filter((tab) => tab.artifact.artifactId !== fork.artifact.artifactId);
      return { ...state, tabs: [...tabs, fork], activeArtifactId: fork.artifact.artifactId, closeGuard: null };
    }
    case 'metadataUpdated':
      return replaceTab(state, action.operation.artifact.artifactId, (tab) => ({
        ...tab,
        artifact: action.operation.artifact,
        revision: action.operation.revision,
        dirty: false,
        saveState: 'idle',
        saveError: null,
        conflict: null,
      }));
    case 'closeRequested': {
      const tab = state.tabs.find((item) => item.artifact.artifactId === action.artifactId);
      if (!tab) return state;
      if (tab.saveState === 'saving' || tab.dirty) {
        return {
          ...state,
          closeGuard: {
            artifactId: action.artifactId,
            reason: tab.saveState === 'saving' ? 'saving' : 'dirty',
          },
        };
      }
      return closeTab(state, action.artifactId);
    }
    case 'closeCancelled':
      return { ...state, closeGuard: null };
    case 'closeDiscarded':
      return closeTab(state, action.artifactId);
  }
}

type WorkspaceListener = (state: ArtifactWorkspaceState) => void;

export class ArtifactWorkspaceController {
  private state = createArtifactWorkspaceState();
  private readonly listeners = new Set<WorkspaceListener>();
  private readonly bridge: ArtifactBridge;
  private readonly tabIncarnations = new Map<string, number>();
  private readonly opening = new Map<string, Promise<void>>();
  private incarnationSequence = 0;

  constructor(bridge: ArtifactBridge = defaultBridge) {
    this.bridge = bridge;
  }

  getState(): ArtifactWorkspaceState {
    return this.state;
  }

  subscribe(listener: WorkspaceListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  dispatch(action: ArtifactWorkspaceAction): void {
    const next = artifactWorkspaceReducer(this.state, action);
    if (next === this.state) return;
    this.state = next;
    this.listeners.forEach((listener) => listener(this.state));
  }

  open(artifactId: string): Promise<void> {
    const existing = this.opening.get(artifactId);
    if (existing) return existing;
    const operation = (async () => {
      const result = await this.bridge.get({ artifactId });
      if (result.artifact.artifactId !== artifactId || result.revision.artifactId !== artifactId) {
        throw new Error('Artifact read identity does not match the requested artifact.');
      }
      this.incarnationSequence += 1;
      this.tabIncarnations.set(artifactId, this.incarnationSequence);
      this.dispatch({ type: 'opened', result });
    })();
    const tracked = operation.finally(() => {
      if (this.opening.get(artifactId) === tracked) this.opening.delete(artifactId);
    });
    this.opening.set(artifactId, tracked);
    return tracked;
  }

  activate(artifactId: string): void {
    this.dispatch({ type: 'activated', artifactId });
  }

  edit(artifactId: string, content: ArtifactContent): void {
    this.dispatch({ type: 'edited', artifactId, content });
  }

  requestClose(artifactId: string): void {
    this.dispatch({ type: 'closeRequested', artifactId });
    if (!this.state.tabs.some((tab) => tab.artifact.artifactId === artifactId)) {
      this.tabIncarnations.delete(artifactId);
    }
  }

  cancelClose(): void {
    this.dispatch({ type: 'closeCancelled' });
  }

  discardAndClose(artifactId: string): void {
    this.tabIncarnations.delete(artifactId);
    this.dispatch({ type: 'closeDiscarded', artifactId });
  }

  getTabIncarnation(artifactId: string): number | null {
    return this.tabIncarnations.get(artifactId) ?? null;
  }

  acceptConflictRemote(
    artifactId: string,
    remote: ArtifactReadResult,
    minimumRemote?: ArtifactRevision,
  ): void {
    const tab = this.requireTab(artifactId);
    if (!tab.conflict) throw new Error('Artifact is not conflicted.');
    this.assertReadIdentity(tab, remote);
    this.assertConflictRemoteRevision(tab, remote, minimumRemote);
    this.dispatch({ type: 'saveConflicted', artifactId, remote });
  }

  getConflictComparison(artifactId: string): { remote: ArtifactReadResult; local: ArtifactContent } {
    const tab = this.requireTab(artifactId);
    if (tab.conflict?.status !== 'ready' || !tab.conflict.remote) {
      throw new Error('Conflict remote revision is unavailable.');
    }
    this.assertReadIdentity(tab, tab.conflict.remote);
    this.assertConflictRemoteRevision(tab, tab.conflict.remote);
    return { remote: tab.conflict.remote, local: tab.draftContent };
  }

  async refreshConflict(artifactId: string): Promise<void> {
    const tab = this.requireTab(artifactId);
    if (!tab.conflict) throw new Error('Artifact is not conflicted.');
    const incarnation = this.requireTabIncarnation(artifactId);
    const minimumRemote = tab.conflict.remote?.revision;
    this.dispatch({ type: 'saveConflictDetected', artifactId });
    try {
      const remote = await this.bridge.get({ artifactId });
      this.assertCurrentIncarnation(artifactId, incarnation);
      this.acceptConflictRemote(artifactId, remote, minimumRemote);
    } catch {
      if (!this.isCurrentIncarnation(artifactId, incarnation)) return;
      this.dispatch({ type: 'saveConflictLoadFailed', artifactId, message: 'The latest remote revision could not be loaded.' });
    }
  }

  async reloadConflict(artifactId: string): Promise<'reloaded' | 'remote_advanced'> {
    const tab = this.requireTab(artifactId);
    if (!tab.conflict) throw new Error('Artifact is not conflicted.');
    const incarnation = this.requireTabIncarnation(artifactId);
    const reviewedRemoteId = tab.conflict.remote?.revision.revisionId ?? null;
    const remote = await this.bridge.get({ artifactId });
    this.assertCurrentIncarnation(artifactId, incarnation);
    this.assertReadIdentity(tab, remote);
    this.assertConflictRemoteRevision(tab, remote, tab.conflict.remote?.revision);
    if (reviewedRemoteId && remote.revision.revisionId !== reviewedRemoteId) {
      this.acceptConflictRemote(artifactId, remote, tab.conflict.remote?.revision);
      return 'remote_advanced';
    }
    this.dispatch({ type: 'conflictReloaded', artifactId, remote });
    return 'reloaded';
  }

  async forkConflict(
    artifactId: string,
    title: string,
    idempotencyKey: string,
  ): Promise<{ forkId: string; originalResolved: boolean }> {
    const tab = this.requireTab(artifactId);
    if (tab.conflict?.status !== 'ready' || !tab.conflict.remote) {
      throw new Error('Conflict remote revision is unavailable.');
    }
    this.assertReadIdentity(tab, tab.conflict.remote);
    this.assertConflictRemoteRevision(tab, tab.conflict.remote);
    const capturedDraft = tab.draftContent;
    const incarnation = this.requireTabIncarnation(artifactId);
    const operation = await this.bridge.duplicate({
      sourceArtifactId: artifactId,
      sourceRevisionId: tab.conflict.baseRevisionId,
      title,
      contentOverride: capturedDraft,
      idempotencyKey,
    });
    if (
      operation.revision.artifactId !== operation.artifact.artifactId
      || operation.artifact.workspaceId !== tab.artifact.workspaceId
      || operation.artifact.kind !== tab.artifact.kind
      || operation.artifact.schemaVersion !== tab.artifact.schemaVersion
      || operation.artifact.artifactId === artifactId
      || operation.artifact.currentRevisionId !== operation.revision.revisionId
      || operation.artifact.currentRevisionNumber !== operation.revision.revisionNumber
    ) {
      throw new Error('Conflict fork identity mismatch.');
    }
    const fork: ArtifactReadResult = {
      artifact: operation.artifact,
      revision: operation.revision,
      content: capturedDraft,
    };
    this.assertCurrentIncarnation(artifactId, incarnation);
    const latestOriginal = await this.bridge.get({ artifactId });
    this.assertCurrentIncarnation(artifactId, incarnation);
    this.assertReadIdentity(tab, latestOriginal);
    this.assertConflictRemoteRevision(tab, latestOriginal, tab.conflict.remote.revision);
    const current = this.requireTab(artifactId);
    if (current.draftContent !== capturedDraft) {
      this.dispatch({ type: 'conflictForkOpened', fork });
      return { forkId: operation.artifact.artifactId, originalResolved: false };
    }
    this.dispatch({ type: 'conflictForked', artifactId, remote: latestOriginal, fork });
    return { forkId: operation.artifact.artifactId, originalResolved: true };
  }

  async restore(artifactId: string, sourceRevisionId: string, idempotencyKey: string): Promise<void> {
    const tab = this.requireTab(artifactId);
    await this.bridge.restore({
      artifactId,
      sourceRevisionId,
      expectedRevisionNumber: tab.artifact.currentRevisionNumber,
      idempotencyKey,
      changeSummary: 'Revision restored',
    });
    await this.open(artifactId);
  }

  async archive(artifactId: string): Promise<void> {
    const tab = this.requireTab(artifactId);
    const operation = await this.bridge.archive({
      artifactId,
      expectedRevisionNumber: tab.artifact.currentRevisionNumber,
    });
    this.dispatch({ type: 'metadataUpdated', operation });
  }

  private requireTab(artifactId: string): ArtifactWorkspaceTab {
    const tab = this.state.tabs.find((item) => item.artifact.artifactId === artifactId);
    if (!tab) throw new Error('Artifact tab is not open.');
    return tab;
  }

  private assertReadIdentity(expected: ArtifactWorkspaceTab, result: ArtifactReadResult): void {
    const artifactId = expected.artifact.artifactId;
    if (
      result.artifact.artifactId !== artifactId
      || result.revision.artifactId !== artifactId
      || result.artifact.workspaceId !== expected.artifact.workspaceId
      || result.artifact.kind !== expected.artifact.kind
      || result.artifact.schemaVersion !== expected.artifact.schemaVersion
      || result.artifact.currentRevisionId !== result.revision.revisionId
      || result.artifact.currentRevisionNumber !== result.revision.revisionNumber
    ) {
      throw new Error('Artifact read identity mismatch.');
    }
  }

  private assertConflictRemoteRevision(
    tab: ArtifactWorkspaceTab,
    result: ArtifactReadResult,
    minimumRemote?: ArtifactRevision,
  ): void {
    const baseRevisionNumber = tab.conflict?.baseRevisionNumber ?? tab.revision.revisionNumber;
    const minimum = Math.max(baseRevisionNumber + 1, minimumRemote?.revisionNumber ?? 0);
    if (result.revision.revisionNumber < minimum) {
      throw new Error('Artifact conflict remote revision is stale.');
    }
    if (
      minimumRemote
      && result.revision.revisionNumber === minimumRemote.revisionNumber
      && result.revision.revisionId !== minimumRemote.revisionId
    ) {
      throw new Error('Artifact conflict remote revision identity changed without advancing.');
    }
  }

  private requireTabIncarnation(artifactId: string): number {
    const incarnation = this.getTabIncarnation(artifactId);
    if (incarnation === null) throw new Error('Artifact tab is not open.');
    return incarnation;
  }

  private isCurrentIncarnation(artifactId: string, incarnation: number): boolean {
    return this.getTabIncarnation(artifactId) === incarnation
      && this.state.tabs.some((tab) => tab.artifact.artifactId === artifactId);
  }

  private assertCurrentIncarnation(artifactId: string, incarnation: number): void {
    if (!this.isCurrentIncarnation(artifactId, incarnation)) {
      throw new Error('Artifact workspace context changed.');
    }
  }
}
