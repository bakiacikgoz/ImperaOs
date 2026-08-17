import { ArtifactBridgeError, artifactBridge as defaultBridge, type ArtifactBridge } from './artifactBridge';
import type { ArtifactContent, ArtifactMutationRequest } from './artifactContracts';
import { ArtifactWorkspaceController } from './workspaceController';


const DEFAULT_DEBOUNCE_MS = 900;
const DEFAULT_MAX_DIRTY_MS = 5_000;

interface PendingSave {
  artifactId: string;
  content: ArtifactContent;
  lifecycleGeneration: number;
  artifactGeneration: number;
  debounceTimer: ReturnType<typeof setTimeout> | null;
  maxTimer: ReturnType<typeof setTimeout> | null;
  ready: boolean;
  request?: ArtifactMutationRequest;
}

interface FailedSave {
  content: ArtifactContent;
  request: ArtifactMutationRequest;
}

export interface ArtifactAutosaveOptions {
  debounceMs?: number;
  maxDirtyMs?: number;
}

type IdleWaiter = () => void;

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(',')}]`;
  }
  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`);
    return `{${entries.join(',')}}`;
  }
  return JSON.stringify(value) ?? 'null';
}

export class ArtifactAutosaveQueue {
  private readonly pending = new Map<string, PendingSave>();
  private readonly failed = new Map<string, FailedSave>();
  private readonly deferredAfterFailure = new Map<string, ArtifactContent>();
  private readonly conflictBlocked = new Set<string>();
  private readonly idleWaiters = new Set<IdleWaiter>();
  private readonly debounceMs: number;
  private readonly maxDirtyMs: number;
  private readonly controller: ArtifactWorkspaceController;
  private readonly bridge: ArtifactBridge;
  private inFlight = false;
  private idempotencySequence = 0;
  private lifecycleGeneration = 0;
  private readonly artifactGenerations = new Map<string, number>();

  constructor(
    controller: ArtifactWorkspaceController,
    bridge: ArtifactBridge = defaultBridge,
    options: ArtifactAutosaveOptions = {},
  ) {
    this.controller = controller;
    this.bridge = bridge;
    this.debounceMs = options.debounceMs ?? DEFAULT_DEBOUNCE_MS;
    this.maxDirtyMs = options.maxDirtyMs ?? DEFAULT_MAX_DIRTY_MS;
    if (this.debounceMs < 1 || this.maxDirtyMs < this.debounceMs) {
      throw new Error('Autosave timing boundary is invalid.');
    }
  }

  schedule(artifactId: string, content: ArtifactContent): void {
    this.controller.edit(artifactId, content);
    if (this.conflictBlocked.has(artifactId)) return;
    if (this.failed.has(artifactId)) {
      this.deferredAfterFailure.set(artifactId, content);
      return;
    }
    const existing = this.pending.get(artifactId);
    if (existing) {
      existing.content = content;
      existing.ready = false;
      if (existing.debounceTimer !== null) clearTimeout(existing.debounceTimer);
      existing.debounceTimer = setTimeout(() => this.markReady(artifactId), this.debounceMs);
      return;
    }
    const entry: PendingSave = {
      artifactId,
      content,
      lifecycleGeneration: this.lifecycleGeneration,
      artifactGeneration: this.artifactGenerations.get(artifactId) ?? 0,
      ready: false,
      debounceTimer: setTimeout(() => this.markReady(artifactId), this.debounceMs),
      maxTimer: setTimeout(() => this.markReady(artifactId), this.maxDirtyMs),
    };
    this.pending.set(artifactId, entry);
  }

  async flush(artifactId?: string): Promise<void> {
    if (artifactId) {
      this.markReady(artifactId);
    } else {
      [...this.pending.keys()].forEach((id) => this.markReady(id));
    }
    await this.waitUntilIdle();
  }

  async retry(artifactId: string): Promise<void> {
    if (this.conflictBlocked.has(artifactId)) return;
    const failed = this.failed.get(artifactId);
    if (!failed) return;
    this.failed.delete(artifactId);
    const entry: PendingSave = {
      artifactId,
      content: failed.content,
      lifecycleGeneration: this.lifecycleGeneration,
      artifactGeneration: this.artifactGenerations.get(artifactId) ?? 0,
      ready: false,
      debounceTimer: null,
      maxTimer: null,
      request: failed.request,
    };
    this.pending.set(artifactId, entry);
    this.markReady(artifactId);
    await this.waitUntilIdle();
    if (this.failed.has(artifactId)) return;
    const deferred = this.deferredAfterFailure.get(artifactId);
    if (!deferred) return;
    this.deferredAfterFailure.delete(artifactId);
    this.schedule(artifactId, deferred);
    this.markReady(artifactId);
    await this.waitUntilIdle();
  }

  dispose(): void {
    this.lifecycleGeneration += 1;
    this.pending.forEach((entry) => this.clearEntryTimers(entry));
    this.pending.clear();
    this.failed.clear();
    this.deferredAfterFailure.clear();
    this.conflictBlocked.clear();
    this.artifactGenerations.clear();
    this.resolveIdleIfNeeded();
  }

  retire(artifactId: string): void {
    this.artifactGenerations.set(artifactId, (this.artifactGenerations.get(artifactId) ?? 0) + 1);
    const pending = this.pending.get(artifactId);
    if (pending) this.clearEntryTimers(pending);
    this.pending.delete(artifactId);
    this.failed.delete(artifactId);
    this.deferredAfterFailure.delete(artifactId);
    this.conflictBlocked.delete(artifactId);
    this.resolveIdleIfNeeded();
  }

  isConflictBlocked(artifactId: string): boolean {
    return this.conflictBlocked.has(artifactId);
  }

  resolveConflict(artifactId: string): void {
    this.conflictBlocked.delete(artifactId);
  }

  private blockForConflict(artifactId: string): void {
    this.conflictBlocked.add(artifactId);
    const pending = this.pending.get(artifactId);
    if (pending) this.clearEntryTimers(pending);
    this.pending.delete(artifactId);
    this.failed.delete(artifactId);
    this.deferredAfterFailure.delete(artifactId);
  }

  private markReady(artifactId: string): void {
    const entry = this.pending.get(artifactId);
    if (!entry) return;
    entry.ready = true;
    this.clearEntryTimers(entry);
    void this.drain();
  }

  private async drain(): Promise<void> {
    if (this.inFlight) return;
    const entry = [...this.pending.values()].find((candidate) => candidate.ready);
    if (!entry) {
      this.resolveIdleIfNeeded();
      return;
    }
    this.pending.delete(entry.artifactId);
    this.inFlight = true;
    try {
      await this.save(entry);
    } finally {
      this.inFlight = false;
      await this.drain();
    }
  }

  private async save(entry: PendingSave): Promise<void> {
    const tab = this.controller
      .getState()
      .tabs.find((candidate) => candidate.artifact.artifactId === entry.artifactId);
    if (!tab) return;
    const tabIncarnation = this.controller.getTabIncarnation(entry.artifactId);
    if (tabIncarnation === null || !this.isCurrent(entry, tabIncarnation)) return;
    if (canonicalJson(entry.content) === canonicalJson(tab.persistedContent)) {
      this.controller.dispatch({ type: 'saveNoop', artifactId: entry.artifactId });
      return;
    }
    this.controller.dispatch({ type: 'saveStarted', artifactId: entry.artifactId });
    let request = entry.request;
    if (!request) {
      this.idempotencySequence += 1;
      request = {
        artifactId: entry.artifactId,
        expectedRevisionNumber: tab.artifact.currentRevisionNumber,
        mutationType: 'replace_content',
        content: entry.content,
        idempotencyKey: `autosave-${entry.artifactId.slice(0, 64)}-${tab.artifact.currentRevisionNumber + 1}-${this.idempotencySequence}`,
        changeSummary: 'Autosave',
      };
    }
    try {
      const operation = await this.bridge.mutate(request);
      if (!this.isCurrent(entry, tabIncarnation)) return;
      this.failed.delete(entry.artifactId);
      this.controller.dispatch({
        type: 'saveSucceeded',
        artifactId: entry.artifactId,
        operation,
        content: entry.content,
      });
    } catch (error) {
      if (!this.isCurrent(entry, tabIncarnation)) return;
      if (error instanceof ArtifactBridgeError && error.code === 'ARTIFACT_REVISION_CONFLICT') {
        this.blockForConflict(entry.artifactId);
        this.controller.dispatch({ type: 'saveConflictDetected', artifactId: entry.artifactId });
        try {
          const remote = await this.bridge.get({ artifactId: entry.artifactId });
          if (!this.isCurrent(entry, tabIncarnation)) return;
          this.controller.acceptConflictRemote(entry.artifactId, remote);
        } catch {
          if (!this.isCurrent(entry, tabIncarnation)) return;
          this.controller.dispatch({
            type: 'saveConflictLoadFailed',
            artifactId: entry.artifactId,
            message: 'The latest remote revision could not be loaded.',
          });
        }
        return;
      }
      const pending = this.pending.get(entry.artifactId);
      const newer = pending?.content;
      if (pending) this.clearEntryTimers(pending);
      if (newer) this.deferredAfterFailure.set(entry.artifactId, newer);
      this.failed.set(entry.artifactId, { content: entry.content, request });
      this.pending.delete(entry.artifactId);
      this.controller.dispatch({
        type: 'saveFailed',
        artifactId: entry.artifactId,
        message: 'Artifact autosave failed. Retry the same save.',
      });
    }
  }

  private clearEntryTimers(entry: PendingSave): void {
    if (entry.debounceTimer !== null) clearTimeout(entry.debounceTimer);
    if (entry.maxTimer !== null) clearTimeout(entry.maxTimer);
    entry.debounceTimer = null;
    entry.maxTimer = null;
  }

  private isCurrent(entry: PendingSave, tabIncarnation: number): boolean {
    return entry.lifecycleGeneration === this.lifecycleGeneration
      && entry.artifactGeneration === (this.artifactGenerations.get(entry.artifactId) ?? 0)
      && this.controller.getTabIncarnation(entry.artifactId) === tabIncarnation;
  }

  private waitUntilIdle(): Promise<void> {
    if (!this.inFlight && this.pending.size === 0) return Promise.resolve();
    return new Promise((resolve) => this.idleWaiters.add(resolve));
  }

  private resolveIdleIfNeeded(): void {
    if (this.inFlight || this.pending.size > 0) return;
    this.idleWaiters.forEach((resolve) => resolve());
    this.idleWaiters.clear();
  }
}
