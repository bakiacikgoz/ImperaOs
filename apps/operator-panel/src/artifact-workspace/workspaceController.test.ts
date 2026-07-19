import { describe, expect, it, vi } from 'vitest';

import type { ArtifactBridge } from './artifactBridge';
import type { ArtifactContent, ArtifactReadResult } from './artifactContracts';
import {
  ArtifactWorkspaceController,
  artifactWorkspaceReducer,
  createArtifactWorkspaceState,
} from './workspaceController';


function loaded(text = 'v1'): ArtifactReadResult {
  return {
    artifact: {
      artifactId: 'artifact-1',
      workspaceId: 'workspace-1',
      kind: 'document',
      title: 'Plan',
      status: 'draft',
      schemaVersion: 1,
      dataClass: 'internal',
      currentRevisionId: 'revision-1',
      currentRevisionNumber: 1,
      sourceSessionId: null,
      sourceTurnId: null,
      createdByType: 'user',
      createdById: 'user-1',
      updatedById: 'user-1',
      createdAtUtc: '2026-07-16T08:00:00Z',
      updatedAtUtc: '2026-07-16T08:00:00Z',
      archivedAtUtc: null,
      etag: 'etag-1',
      metadata: {},
    },
    revision: {
      revisionId: 'revision-1',
      artifactId: 'artifact-1',
      parentRevisionId: null,
      baseRevisionId: null,
      revisionNumber: 1,
      schemaVersion: 1,
      mutationType: 'create',
      contentRelpath: 'workspace-1/artifact-1/1/revision-1.json',
      contentSha256: 'a'.repeat(64),
      contentSizeBytes: 10,
      contentEncoding: 'json',
      changeSummary: 'Created',
      authorType: 'user',
      authorId: 'user-1',
      idempotencyKey: 'create-1',
      createdAtUtc: '2026-07-16T08:00:00Z',
    },
    content: { kind: 'document', schemaVersion: 1, text },
  };
}

describe('artifact workspace controller', () => {
  it('coalesces concurrent opens for the same artifact', async () => {
    let resolveGet: ((result: ArtifactReadResult) => void) | undefined;
    const get = vi.fn(() => new Promise<ArtifactReadResult>((resolve) => { resolveGet = resolve; }));
    const controller = new ArtifactWorkspaceController({ get } as unknown as ArtifactBridge);

    const first = controller.open('artifact-1');
    const second = controller.open('artifact-1');

    expect(get).toHaveBeenCalledOnce();
    resolveGet?.(loaded());
    await Promise.all([first, second]);
    expect(controller.getState().tabs).toHaveLength(1);
  });

  it('rejects an artifact read whose identity differs from the request', async () => {
    const controller = new ArtifactWorkspaceController({
      get: vi.fn().mockResolvedValue(loaded()),
    } as unknown as ArtifactBridge);

    await expect(controller.open('artifact-other')).rejects.toThrow('identity');
    expect(controller.getState().tabs).toHaveLength(0);
  });

  it('opens tabs once, tracks active tab, and marks edited content dirty', () => {
    let state = createArtifactWorkspaceState();
    state = artifactWorkspaceReducer(state, { type: 'opened', result: loaded() });
    state = artifactWorkspaceReducer(state, { type: 'opened', result: loaded() });
    const draft: ArtifactContent = { kind: 'document', schemaVersion: 1, text: 'v2' };
    state = artifactWorkspaceReducer(state, {
      type: 'edited',
      artifactId: 'artifact-1',
      content: draft,
    });

    expect(state.tabs).toHaveLength(1);
    expect(state.activeArtifactId).toBe('artifact-1');
    expect(state.tabs[0]).toMatchObject({ dirty: true, saveState: 'dirty', draftContent: draft });
  });

  it('guards dirty close and supports cancel or explicit discard', () => {
    let state = artifactWorkspaceReducer(createArtifactWorkspaceState(), {
      type: 'opened',
      result: loaded(),
    });
    state = artifactWorkspaceReducer(state, {
      type: 'edited',
      artifactId: 'artifact-1',
      content: { kind: 'document', schemaVersion: 1, text: 'v2' },
    });
    state = artifactWorkspaceReducer(state, { type: 'closeRequested', artifactId: 'artifact-1' });

    expect(state.closeGuard).toEqual({ artifactId: 'artifact-1', reason: 'dirty' });
    expect(state.tabs).toHaveLength(1);

    state = artifactWorkspaceReducer(state, { type: 'closeCancelled' });
    expect(state.closeGuard).toBeNull();
    state = artifactWorkspaceReducer(state, { type: 'closeRequested', artifactId: 'artifact-1' });
    state = artifactWorkspaceReducer(state, { type: 'closeDiscarded', artifactId: 'artifact-1' });
    expect(state.tabs).toHaveLength(0);
    expect(state.activeArtifactId).toBeNull();
  });

  it('records conflicts without replacing the local draft', () => {
    let state = artifactWorkspaceReducer(createArtifactWorkspaceState(), {
      type: 'opened',
      result: loaded(),
    });
    const draft: ArtifactContent = { kind: 'document', schemaVersion: 1, text: 'local' };
    state = artifactWorkspaceReducer(state, {
      type: 'edited',
      artifactId: 'artifact-1',
      content: draft,
    });
    state = artifactWorkspaceReducer(state, {
      type: 'saveConflicted',
      artifactId: 'artifact-1',
      remote: loaded('remote'),
    });

    expect(state.tabs[0]).toMatchObject({
      dirty: true,
      saveState: 'conflict',
      draftContent: draft,
      conflict: { status: 'ready', remote: { revision: { revisionNumber: 1 } } },
    });

    state = artifactWorkspaceReducer(state, {
      type: 'edited', artifactId: 'artifact-1', content: { ...draft, text: 'newer local' },
    });
    expect(state.tabs[0]).toMatchObject({
      dirty: true,
      saveState: 'conflict',
      draftContent: { text: 'newer local' },
      conflict: { status: 'ready' },
    });
  });

  it('reloads the latest remote revision only after explicit conflict resolution', async () => {
    const initial = loaded();
    const remote = loaded('remote');
    remote.artifact.currentRevisionId = 'revision-2';
    remote.artifact.currentRevisionNumber = 2;
    remote.revision.revisionId = 'revision-2';
    remote.revision.revisionNumber = 2;
    const bridge = { get: vi.fn().mockResolvedValueOnce(initial).mockResolvedValueOnce(remote) } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    controller.edit('artifact-1', { kind: 'document', schemaVersion: 1, text: 'local' });
    controller.dispatch({ type: 'saveConflicted', artifactId: 'artifact-1', remote });

    await controller.reloadConflict('artifact-1');

    expect(controller.getState().tabs[0]).toMatchObject({
      dirty: false, saveState: 'idle', draftContent: { text: 'remote' }, revision: { revisionNumber: 2 }, conflict: null,
    });
  });

  it('forks the captured local draft with governed duplicate and restores the original to remote', async () => {
    const initial = loaded();
    const remote = loaded('remote');
    remote.artifact.currentRevisionId = 'revision-2';
    remote.artifact.currentRevisionNumber = 2;
    remote.revision.revisionId = 'revision-2';
    remote.revision.revisionNumber = 2;
    const fork = loaded('local');
    fork.artifact = { ...fork.artifact, artifactId: 'artifact-fork', title: 'Plan (local draft)', currentRevisionId: 'fork-revision-1' };
    fork.revision = { ...fork.revision, artifactId: 'artifact-fork', revisionId: 'fork-revision-1' };
    const duplicate = vi.fn().mockResolvedValue({ artifact: fork.artifact, revision: fork.revision, created: true, disposition: 'created' });
    const bridge = { get: vi.fn().mockResolvedValueOnce(initial).mockResolvedValueOnce(remote), duplicate } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    const local = { kind: 'document' as const, schemaVersion: 1 as const, text: 'local' };
    controller.edit('artifact-1', local);
    controller.dispatch({ type: 'saveConflicted', artifactId: 'artifact-1', remote });

    const outcome = await controller.forkConflict('artifact-1', 'Plan (local draft)', 'fork-conflict-1');

    expect(duplicate).toHaveBeenCalledWith(expect.objectContaining({
      sourceArtifactId: 'artifact-1', sourceRevisionId: 'revision-1', contentOverride: local,
      title: 'Plan (local draft)', idempotencyKey: 'fork-conflict-1',
    }));
    expect(outcome).toEqual({ forkId: 'artifact-fork', originalResolved: true });
    expect(bridge.get).toHaveBeenLastCalledWith({ artifactId: 'artifact-1' });
    expect(controller.getState()).toMatchObject({ activeArtifactId: 'artifact-fork' });
    expect(controller.getState().tabs).toEqual(expect.arrayContaining([
      expect.objectContaining({ artifact: expect.objectContaining({ artifactId: 'artifact-1' }), draftContent: expect.objectContaining({ text: 'remote' }), conflict: null }),
      expect.objectContaining({ artifact: expect.objectContaining({ artifactId: 'artifact-fork' }), draftContent: local, dirty: false }),
    ]));
  });

  it('re-reads the original after fork creation and resolves it to the newest remote', async () => {
    const initial = loaded();
    const reviewed = loaded('remote-2');
    reviewed.artifact.currentRevisionId = 'revision-2';
    reviewed.artifact.currentRevisionNumber = 2;
    reviewed.revision.revisionId = 'revision-2';
    reviewed.revision.revisionNumber = 2;
    const advanced = loaded('remote-3');
    advanced.artifact.currentRevisionId = 'revision-3';
    advanced.artifact.currentRevisionNumber = 3;
    advanced.revision.revisionId = 'revision-3';
    advanced.revision.revisionNumber = 3;
    const fork = loaded('local');
    fork.artifact = { ...fork.artifact, artifactId: 'artifact-fork', currentRevisionId: 'fork-revision-1' };
    fork.revision = { ...fork.revision, artifactId: 'artifact-fork', revisionId: 'fork-revision-1' };
    const bridge = {
      get: vi.fn().mockResolvedValueOnce(initial).mockResolvedValueOnce(advanced),
      duplicate: vi.fn().mockResolvedValue({ artifact: fork.artifact, revision: fork.revision }),
    } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    controller.edit('artifact-1', { kind: 'document', schemaVersion: 1, text: 'local' });
    controller.dispatch({ type: 'saveConflicted', artifactId: 'artifact-1', remote: reviewed });

    await expect(controller.forkConflict('artifact-1', 'Fork', 'fork-key')).resolves.toEqual({
      forkId: 'artifact-fork', originalResolved: true,
    });

    expect(controller.getState().tabs.find((tab) => tab.artifact.artifactId === 'artifact-1')).toMatchObject({
      revision: { revisionNumber: 3 }, draftContent: { text: 'remote-3' }, conflict: null,
    });
  });

  it('keeps the conflict blocked when the original cannot be re-read after fork creation', async () => {
    const initial = loaded();
    const remote = loaded('remote');
    remote.artifact.currentRevisionId = 'revision-2';
    remote.artifact.currentRevisionNumber = 2;
    remote.revision.revisionId = 'revision-2';
    remote.revision.revisionNumber = 2;
    const fork = loaded('local');
    fork.artifact = { ...fork.artifact, artifactId: 'artifact-fork', currentRevisionId: 'fork-revision-1' };
    fork.revision = { ...fork.revision, artifactId: 'artifact-fork', revisionId: 'fork-revision-1' };
    const bridge = {
      get: vi.fn().mockResolvedValueOnce(initial).mockRejectedValueOnce(new Error('offline')),
      duplicate: vi.fn().mockResolvedValue({ artifact: fork.artifact, revision: fork.revision }),
    } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    controller.edit('artifact-1', { kind: 'document', schemaVersion: 1, text: 'local' });
    controller.dispatch({ type: 'saveConflicted', artifactId: 'artifact-1', remote });

    await expect(controller.forkConflict('artifact-1', 'Fork', 'fork-key')).rejects.toThrow('offline');

    expect(controller.getState().tabs).toHaveLength(1);
    expect(controller.getState().tabs[0]).toMatchObject({ dirty: true, saveState: 'conflict', draftContent: { text: 'local' } });
  });

  it('opens the captured fork without discarding a newer local draft', async () => {
    const initial = loaded();
    const remote = loaded('remote');
    remote.artifact.currentRevisionId = 'revision-2';
    remote.artifact.currentRevisionNumber = 2;
    remote.revision.revisionId = 'revision-2';
    remote.revision.revisionNumber = 2;
    const fork = loaded('local');
    fork.artifact = { ...fork.artifact, artifactId: 'artifact-fork', currentRevisionId: 'fork-revision-1' };
    fork.revision = { ...fork.revision, artifactId: 'artifact-fork', revisionId: 'fork-revision-1' };
    let releaseCreate!: () => void;
    const createGate = new Promise<void>((resolve) => { releaseCreate = resolve; });
    const bridge = {
      get: vi.fn().mockResolvedValueOnce(initial).mockResolvedValueOnce(remote),
      duplicate: vi.fn().mockImplementation(async () => {
        await createGate;
        return { artifact: fork.artifact, revision: fork.revision };
      }),
    } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    controller.edit('artifact-1', { kind: 'document', schemaVersion: 1, text: 'captured' });
    controller.dispatch({ type: 'saveConflicted', artifactId: 'artifact-1', remote });

    const pending = controller.forkConflict('artifact-1', 'Fork', 'fork-key');
    controller.edit('artifact-1', { kind: 'document', schemaVersion: 1, text: 'newer local' });
    releaseCreate();

    await expect(pending).resolves.toEqual({ forkId: 'artifact-fork', originalResolved: false });
    expect(controller.getState().tabs.find((tab) => tab.artifact.artifactId === 'artifact-1')).toMatchObject({
      dirty: true, saveState: 'conflict', draftContent: { text: 'newer local' }, conflict: { status: 'ready' },
    });
    expect(controller.getState().tabs.find((tab) => tab.artifact.artifactId === 'artifact-fork')).toMatchObject({
      dirty: false, draftContent: { text: 'captured' },
    });
  });

  it('rejects a same-id remote with incompatible workspace or kind', async () => {
    const initial = loaded();
    const remote = loaded('remote');
    remote.artifact = { ...remote.artifact, workspaceId: 'other-workspace' };
    const bridge = { get: vi.fn().mockResolvedValueOnce(initial).mockResolvedValueOnce(remote) } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    controller.edit('artifact-1', { kind: 'document', schemaVersion: 1, text: 'local' });
    controller.dispatch({ type: 'saveConflicted', artifactId: 'artifact-1', remote: loaded('reviewed') });

    await expect(controller.reloadConflict('artifact-1')).rejects.toThrow('Artifact read identity mismatch.');
    expect(controller.getState().tabs[0]).toMatchObject({ dirty: true, saveState: 'conflict', draftContent: { text: 'local' } });
  });

  it('rejects an unvalidated ready-conflict action before comparison', async () => {
    const initial = loaded();
    const wrong = loaded('wrong');
    wrong.artifact = { ...wrong.artifact, artifactId: 'artifact-2', currentRevisionId: 'revision-2', currentRevisionNumber: 2 };
    wrong.revision = { ...wrong.revision, artifactId: 'artifact-2', revisionId: 'revision-2', revisionNumber: 2 };
    const bridge = { get: vi.fn().mockResolvedValue(initial) } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    controller.edit('artifact-1', { kind: 'document', schemaVersion: 1, text: 'local' });
    controller.dispatch({ type: 'saveConflicted', artifactId: 'artifact-1', remote: wrong });

    expect(() => controller.getConflictComparison('artifact-1')).toThrow('Artifact read identity mismatch.');
  });

  it('rejects a fork operation whose descriptor and revision disagree', async () => {
    const initial = loaded();
    const remote = loaded('remote');
    remote.artifact.currentRevisionId = 'revision-2';
    remote.artifact.currentRevisionNumber = 2;
    remote.revision.revisionId = 'revision-2';
    remote.revision.revisionNumber = 2;
    const fork = loaded('local');
    fork.artifact = { ...fork.artifact, artifactId: 'artifact-fork', currentRevisionId: 'fork-revision-2', currentRevisionNumber: 2 };
    fork.revision = { ...fork.revision, artifactId: 'artifact-fork', revisionId: 'fork-revision-1', revisionNumber: 1 };
    const bridge = {
      get: vi.fn().mockResolvedValue(initial),
      duplicate: vi.fn().mockResolvedValue({ artifact: fork.artifact, revision: fork.revision }),
    } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    controller.edit('artifact-1', { kind: 'document', schemaVersion: 1, text: 'local' });
    controller.dispatch({ type: 'saveConflicted', artifactId: 'artifact-1', remote });

    await expect(controller.forkConflict('artifact-1', 'Fork', 'fork-key')).rejects.toThrow('Conflict fork identity mismatch.');
    expect(controller.getState().tabs).toHaveLength(1);
  });

  it('fails closed when a post-create read changes revision identity without advancing its number', async () => {
    const initial = loaded();
    const reviewed = loaded('remote');
    reviewed.artifact.currentRevisionId = 'revision-2-a';
    reviewed.artifact.currentRevisionNumber = 2;
    reviewed.revision.revisionId = 'revision-2-a';
    reviewed.revision.revisionNumber = 2;
    const equivocated = loaded('other remote');
    equivocated.artifact.currentRevisionId = 'revision-2-b';
    equivocated.artifact.currentRevisionNumber = 2;
    equivocated.revision.revisionId = 'revision-2-b';
    equivocated.revision.revisionNumber = 2;
    const fork = loaded('local');
    fork.artifact = { ...fork.artifact, artifactId: 'artifact-fork', currentRevisionId: 'fork-revision-1' };
    fork.revision = { ...fork.revision, artifactId: 'artifact-fork', revisionId: 'fork-revision-1' };
    const bridge = {
      get: vi.fn().mockResolvedValueOnce(initial).mockResolvedValueOnce(equivocated),
      duplicate: vi.fn().mockResolvedValue({ artifact: fork.artifact, revision: fork.revision }),
    } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    controller.edit('artifact-1', { kind: 'document', schemaVersion: 1, text: 'local' });
    controller.dispatch({ type: 'saveConflicted', artifactId: 'artifact-1', remote: reviewed });

    await expect(controller.forkConflict('artifact-1', 'Fork', 'fork-key')).rejects.toThrow(
      'Artifact conflict remote revision identity changed without advancing.',
    );
    expect(controller.getState().tabs[0]).toMatchObject({ dirty: true, saveState: 'conflict', draftContent: { text: 'local' } });
  });

  it('requires re-review when the remote advances again before reload confirmation completes', async () => {
    const initial = loaded();
    const reviewed = loaded('remote-2');
    reviewed.artifact.currentRevisionId = 'revision-2';
    reviewed.artifact.currentRevisionNumber = 2;
    reviewed.revision.revisionId = 'revision-2';
    reviewed.revision.revisionNumber = 2;
    const advanced = loaded('remote-3');
    advanced.artifact.currentRevisionId = 'revision-3';
    advanced.artifact.currentRevisionNumber = 3;
    advanced.revision.revisionId = 'revision-3';
    advanced.revision.revisionNumber = 3;
    const bridge = { get: vi.fn().mockResolvedValueOnce(initial).mockResolvedValueOnce(advanced) } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    controller.edit('artifact-1', { kind: 'document', schemaVersion: 1, text: 'local' });
    controller.dispatch({ type: 'saveConflicted', artifactId: 'artifact-1', remote: reviewed });

    await expect(controller.reloadConflict('artifact-1')).resolves.toBe('remote_advanced');

    expect(controller.getState().tabs[0]).toMatchObject({
      dirty: true, saveState: 'conflict', draftContent: { text: 'local' },
      conflict: { status: 'ready', remote: { revision: { revisionNumber: 3 } } },
    });
  });

  it('orchestrates open, restore, and archive through the typed bridge', async () => {
    const first = loaded();
    const restored = loaded('restored');
    restored.artifact.currentRevisionNumber = 2;
    restored.revision.revisionNumber = 2;
    const bridge = {
      get: vi.fn().mockResolvedValueOnce(first).mockResolvedValueOnce(restored),
      restore: vi.fn().mockResolvedValue({
        artifact: restored.artifact,
        revision: restored.revision,
        created: false,
        disposition: 'updated',
      }),
      archive: vi.fn().mockResolvedValue({
        artifact: { ...restored.artifact, status: 'archived' },
        revision: restored.revision,
        created: false,
        disposition: 'updated',
      }),
    } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);

    await controller.open('artifact-1');
    await controller.restore('artifact-1', 'revision-1', 'restore-1');
    await controller.archive('artifact-1');

    expect(bridge.restore).toHaveBeenCalledWith({
      artifactId: 'artifact-1',
      sourceRevisionId: 'revision-1',
      expectedRevisionNumber: 1,
      idempotencyKey: 'restore-1',
      changeSummary: 'Revision restored',
    });
    expect(controller.getState().tabs[0]).toMatchObject({
      dirty: false,
      saveState: 'idle',
      artifact: { status: 'archived', currentRevisionNumber: 2 },
    });
  });
});
