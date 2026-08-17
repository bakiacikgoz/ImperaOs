import type { RJSFValidationError } from '@rjsf/utils';

export interface FormSessionSnapshot {
  formData: Record<string, unknown>;
  errors: RJSFValidationError[];
  submissionKey: string | null;
  submissionState: 'idle' | 'submitting' | 'failed' | 'submitted' | 'pending';
  version: number;
}

const EMPTY_SNAPSHOT: FormSessionSnapshot = Object.freeze({
  formData: Object.freeze({}),
  errors: Object.freeze([]) as unknown as RJSFValidationError[],
  submissionKey: null,
  submissionState: 'idle',
  version: 0,
});

function sameJson(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left) && Array.isArray(right)
      && left.length === right.length
      && left.every((value, index) => sameJson(value, right[index]));
  }
  if (typeof left !== 'object' || left === null || typeof right !== 'object' || right === null) return false;
  const leftRecord = left as Record<string, unknown>;
  const rightRecord = right as Record<string, unknown>;
  const leftKeys = Object.keys(leftRecord).sort();
  const rightKeys = Object.keys(rightRecord).sort();
  return leftKeys.length === rightKeys.length
    && leftKeys.every((key, index) => key === rightKeys[index] && sameJson(leftRecord[key], rightRecord[key]));
}

export class FormSessionRuntime {
  private readonly snapshots = new Map<string, FormSessionSnapshot>();
  private readonly listeners = new Set<() => void>();

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  prepare(key: string): FormSessionSnapshot {
    const existing = this.snapshots.get(key);
    if (existing) return existing;
    const snapshot: FormSessionSnapshot = {
      formData: {}, errors: [], submissionKey: null, submissionState: 'idle', version: 0,
    };
    this.snapshots.set(key, snapshot);
    return snapshot;
  }

  getSnapshot(key: string): FormSessionSnapshot {
    return this.snapshots.get(key) ?? EMPTY_SNAPSHOT;
  }

  update(key: string, formData: Record<string, unknown>, errors: RJSFValidationError[]): void {
    const previous = this.prepare(key);
    const changed = !sameJson(previous.formData, formData);
    this.snapshots.set(key, {
      formData,
      errors,
      submissionKey: changed ? null : previous.submissionKey,
      submissionState: changed ? 'idle' : previous.submissionState,
      version: previous.version + 1,
    });
    this.emit();
  }

  beginSubmission(key: string, createKey: () => string): string | null {
    const previous = this.prepare(key);
    if (previous.submissionState === 'submitting'
      || previous.submissionState === 'submitted'
      || previous.submissionState === 'pending') return null;
    const submissionKey = previous.submissionKey ?? createKey();
    this.snapshots.set(key, {
      ...previous,
      submissionKey,
      submissionState: 'submitting',
      version: previous.version + 1,
    });
    this.emit();
    return submissionKey;
  }

  failSubmission(key: string): void {
    this.setSubmissionState(key, 'failed');
  }

  completeSubmission(key: string, state: 'submitted' | 'pending'): void {
    this.setSubmissionState(key, state);
  }

  resetAll(): void {
    this.snapshots.clear();
    this.emit();
  }

  resetArtifact(artifactId: string): void {
    const prefix = `${artifactId}@`;
    let changed = false;
    for (const key of this.snapshots.keys()) {
      if (key.startsWith(prefix)) {
        this.snapshots.delete(key);
        changed = true;
      }
    }
    if (changed) this.emit();
  }

  private setSubmissionState(
    key: string,
    submissionState: 'failed' | 'submitted' | 'pending',
  ): void {
    const previous = this.prepare(key);
    this.snapshots.set(key, {
      ...previous,
      submissionState,
      version: previous.version + 1,
    });
    this.emit();
  }

  private emit(): void {
    this.listeners.forEach((listener) => listener());
  }
}

export function formSessionKey(artifactId: string, revisionId: string): string {
  return `${artifactId}@${revisionId}`;
}
