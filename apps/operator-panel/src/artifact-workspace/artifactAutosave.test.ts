import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ArtifactBridgeError, type ArtifactBridge } from './artifactBridge';
import type { ArtifactContent, ArtifactReadResult } from './artifactContracts';
import { ArtifactAutosaveQueue } from './artifactAutosave';
import { ArtifactWorkspaceController } from './workspaceController';


function readResult(text = 'v1', revisionNumber = 1): ArtifactReadResult {
  return {
    artifact: {
      artifactId: 'artifact-1',
      workspaceId: 'workspace-1',
      kind: 'document',
      title: 'Plan',
      status: 'draft',
      schemaVersion: 1,
      dataClass: 'internal',
      currentRevisionId: `revision-${revisionNumber}`,
      currentRevisionNumber: revisionNumber,
      sourceSessionId: null,
      sourceTurnId: null,
      createdByType: 'user',
      createdById: 'user-1',
      updatedById: 'user-1',
      createdAtUtc: '2026-07-16T08:00:00Z',
      updatedAtUtc: '2026-07-16T08:00:00Z',
      archivedAtUtc: null,
      etag: `etag-${revisionNumber}`,
      metadata: {},
    },
    revision: {
      revisionId: `revision-${revisionNumber}`,
      artifactId: 'artifact-1',
      parentRevisionId: revisionNumber > 1 ? `revision-${revisionNumber - 1}` : null,
      baseRevisionId: null,
      revisionNumber,
      schemaVersion: 1,
      mutationType: revisionNumber > 1 ? 'replace_content' : 'create',
      contentRelpath: `workspace-1/artifact-1/${revisionNumber}/revision-${revisionNumber}.json`,
      contentSha256: 'a'.repeat(64),
      contentSizeBytes: 10,
      contentEncoding: 'json',
      changeSummary: revisionNumber > 1 ? 'Autosave' : 'Created',
      authorType: 'user',
      authorId: 'user-1',
      idempotencyKey: `save-${revisionNumber}`,
      createdAtUtc: '2026-07-16T08:00:00Z',
    },
    content: documentContent(text),
  };
}

function documentContent(text: string): ArtifactContent {
  return { kind: 'document', schemaVersion: 1, text };
}

function operation(text: string, revisionNumber: number) {
  const read = readResult(text, revisionNumber);
  return {
    artifact: read.artifact,
    revision: read.revision,
    created: false,
    disposition: 'updated' as const,
  };
}

async function settle(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

describe('artifact autosave queue', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('debounces for 900ms and enforces a 5s maximum dirty window', async () => {
    const bridge = {
      get: vi.fn().mockResolvedValue(readResult()),
      mutate: vi.fn().mockResolvedValue(operation('latest', 2)),
    } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    const queue = new ArtifactAutosaveQueue(controller, bridge);

    queue.schedule('artifact-1', documentContent('v2'));
    await vi.advanceTimersByTimeAsync(899);
    expect(bridge.mutate).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(bridge.mutate).toHaveBeenCalledTimes(1);
    await settle();

    for (let elapsed = 0; elapsed < 4_800; elapsed += 800) {
      queue.schedule('artifact-1', documentContent(`latest-${elapsed}`));
      await vi.advanceTimersByTimeAsync(800);
    }
    expect(bridge.mutate).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(200);
    expect(bridge.mutate).toHaveBeenCalledTimes(2);
  });

  it('allows one in-flight mutation and coalesces edits to the newest draft', async () => {
    let resolveFirst!: (value: ReturnType<typeof operation>) => void;
    const first = new Promise<ReturnType<typeof operation>>((resolve) => {
      resolveFirst = resolve;
    });
    const bridge = {
      get: vi.fn().mockResolvedValue(readResult()),
      mutate: vi.fn().mockReturnValueOnce(first).mockResolvedValueOnce(operation('v4', 3)),
    } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    const queue = new ArtifactAutosaveQueue(controller, bridge);

    queue.schedule('artifact-1', documentContent('v2'));
    await vi.advanceTimersByTimeAsync(900);
    queue.schedule('artifact-1', documentContent('v3'));
    queue.schedule('artifact-1', documentContent('v4'));
    await vi.advanceTimersByTimeAsync(900);
    expect(bridge.mutate).toHaveBeenCalledTimes(1);

    resolveFirst(operation('v2', 2));
    await settle();
    expect(bridge.mutate).toHaveBeenCalledTimes(2);
    expect(bridge.mutate).toHaveBeenLastCalledWith(
      expect.objectContaining({
        expectedRevisionNumber: 2,
        content: documentContent('v4'),
      }),
    );
  });

  it('fails closed on revision conflict and preserves the local draft', async () => {
    const remote = readResult('remote', 2);
    const bridge = {
      get: vi.fn().mockResolvedValueOnce(readResult()).mockResolvedValueOnce(remote),
      mutate: vi
        .fn()
        .mockRejectedValue(
          new ArtifactBridgeError(
            'ARTIFACT_REVISION_CONFLICT',
            'stale revision',
            false,
            'bridge_artifact_mutate',
          ),
        ),
    } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    const queue = new ArtifactAutosaveQueue(controller, bridge);

    queue.schedule('artifact-1', documentContent('local'));
    await queue.flush('artifact-1');

    expect(controller.getState().tabs[0]).toMatchObject({
      dirty: true,
      saveState: 'conflict',
      draftContent: documentContent('local'),
      conflict: { status: 'ready', remote: { revision: { revisionNumber: 2 } } },
    });
    expect(queue.isConflictBlocked('artifact-1')).toBe(true);

    queue.schedule('artifact-1', documentContent('newer local'));
    await vi.advanceTimersByTimeAsync(5_000);
    expect(bridge.mutate).toHaveBeenCalledTimes(1);
    expect(controller.getState().tabs[0]).toMatchObject({
      saveState: 'conflict', draftContent: documentContent('newer local'),
    });
  });

  it('keeps autosave blocked when the remote conflict snapshot cannot be loaded', async () => {
    const bridge = {
      get: vi.fn().mockResolvedValueOnce(readResult()).mockRejectedValueOnce(new Error('remote unavailable')),
      mutate: vi.fn().mockRejectedValue(new ArtifactBridgeError(
        'ARTIFACT_REVISION_CONFLICT', 'stale revision', false, 'bridge_artifact_mutate',
      )),
    } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    const queue = new ArtifactAutosaveQueue(controller, bridge);

    queue.schedule('artifact-1', documentContent('local'));
    await expect(queue.flush('artifact-1')).resolves.toBeUndefined();

    expect(queue.isConflictBlocked('artifact-1')).toBe(true);
    expect(controller.getState().tabs[0]).toMatchObject({
      dirty: true, saveState: 'conflict', draftContent: documentContent('local'),
      conflict: { status: 'error', remote: null },
    });
    queue.schedule('artifact-1', documentContent('newer local'));
    await vi.advanceTimersByTimeAsync(5_000);
    expect(bridge.mutate).toHaveBeenCalledTimes(1);
  });

  it('rejects a misrouted or non-advanced remote conflict snapshot', async () => {
    const wrongArtifact = readResult('wrong', 2);
    wrongArtifact.artifact.artifactId = 'artifact-2';
    wrongArtifact.revision.artifactId = 'artifact-2';
    const bridge = {
      get: vi.fn().mockResolvedValueOnce(readResult()).mockResolvedValueOnce(wrongArtifact),
      mutate: vi.fn().mockRejectedValue(new ArtifactBridgeError(
        'ARTIFACT_REVISION_CONFLICT', 'stale revision', false, 'bridge_artifact_mutate',
      )),
    } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    const queue = new ArtifactAutosaveQueue(controller, bridge);

    queue.schedule('artifact-1', documentContent('local'));
    await queue.flush('artifact-1');

    expect(queue.isConflictBlocked('artifact-1')).toBe(true);
    expect(controller.getState().tabs[0]).toMatchObject({
      dirty: true,
      saveState: 'conflict',
      draftContent: documentContent('local'),
      conflict: { status: 'error', remote: null },
    });
  });

  it('skips no-op writes and retries an explicit failed draft', async () => {
    const bridge = {
      get: vi.fn().mockResolvedValue(readResult()),
      mutate: vi
        .fn()
        .mockRejectedValueOnce(
          new ArtifactBridgeError(
            'ARTIFACT_RPC_UNAVAILABLE',
            'C:\\private\\draft-canary.txt stack=secret-draft-canary',
            true,
            'bridge_artifact_mutate',
          ),
        )
        .mockResolvedValueOnce(operation('v2', 2))
        .mockResolvedValueOnce(operation('v3', 3)),
    } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    const queue = new ArtifactAutosaveQueue(controller, bridge);

    queue.schedule('artifact-1', documentContent('v1'));
    await queue.flush('artifact-1');
    expect(bridge.mutate).not.toHaveBeenCalled();
    expect(controller.getState().tabs[0].saveState).toBe('idle');

    queue.schedule('artifact-1', documentContent('v2'));
    await queue.flush('artifact-1');
    expect(controller.getState().tabs[0].saveState).toBe('error');
    expect(controller.getState().tabs[0].saveError).toBe('Artifact autosave failed. Retry the same save.');
    expect(controller.getState().tabs[0].saveError).not.toContain('secret-draft-canary');
    const failedRequest = vi.mocked(bridge.mutate).mock.calls[0][0];
    queue.schedule('artifact-1', documentContent('v3'));
    await queue.retry('artifact-1');

    expect(bridge.mutate).toHaveBeenCalledTimes(3);
    expect(vi.mocked(bridge.mutate).mock.calls[1][0]).toEqual(failedRequest);
    expect(vi.mocked(bridge.mutate).mock.calls[2][0]).toEqual(expect.objectContaining({
      expectedRevisionNumber: 2,
      content: documentContent('v3'),
    }));
    expect(vi.mocked(bridge.mutate).mock.calls[2][0].idempotencyKey).not.toBe(failedRequest.idempotencyKey);
    expect(controller.getState().tabs[0]).toMatchObject({ dirty: false, saveState: 'saved' });
  });

  it('retires pending and conflict-blocked state before discard and reopen', async () => {
    const bridge = {
      get: vi.fn().mockResolvedValue(readResult()),
      mutate: vi.fn().mockResolvedValue(operation('fresh', 2)),
    } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    const queue = new ArtifactAutosaveQueue(controller, bridge);

    queue.schedule('artifact-1', documentContent('discarded'));
    queue.retire('artifact-1');
    controller.discardAndClose('artifact-1');
    await controller.open('artifact-1');
    await vi.advanceTimersByTimeAsync(5_000);
    expect(bridge.mutate).not.toHaveBeenCalled();

    queue.schedule('artifact-1', documentContent('fresh'));
    await queue.flush('artifact-1');
    expect(bridge.mutate).toHaveBeenCalledOnce();
    expect(controller.getState().tabs[0]).toMatchObject({ dirty: false, saveState: 'saved' });
  });

  it('ignores an in-flight completion after the tab incarnation is retired', async () => {
    let resolveMutation!: (value: ReturnType<typeof operation>) => void;
    const mutation = new Promise<ReturnType<typeof operation>>((resolve) => { resolveMutation = resolve; });
    const bridge = {
      get: vi.fn().mockResolvedValue(readResult()),
      mutate: vi.fn().mockReturnValue(mutation),
    } as unknown as ArtifactBridge;
    const controller = new ArtifactWorkspaceController(bridge);
    await controller.open('artifact-1');
    const queue = new ArtifactAutosaveQueue(controller, bridge);
    queue.schedule('artifact-1', documentContent('discarded'));
    await vi.advanceTimersByTimeAsync(900);

    queue.retire('artifact-1');
    controller.discardAndClose('artifact-1');
    await controller.open('artifact-1');
    resolveMutation(operation('discarded', 2));
    await settle();

    expect(controller.getState().tabs[0]).toMatchObject({
      revision: { revisionNumber: 1 }, draftContent: documentContent('v1'), dirty: false, saveState: 'idle',
    });
  });
});
