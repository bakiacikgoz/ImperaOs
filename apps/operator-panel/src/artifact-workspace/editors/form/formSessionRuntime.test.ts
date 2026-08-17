import { describe, expect, it, vi } from 'vitest';

import { FormSessionRuntime } from './formSessionRuntime';

describe('form session runtime', () => {
  it('shares one in-memory snapshot and isolates revisions', () => {
    const runtime = new FormSessionRuntime();
    const listener = vi.fn();
    runtime.subscribe(listener);
    runtime.prepare('artifact-1@revision-1');
    runtime.prepare('artifact-1@revision-2');

    runtime.update('artifact-1@revision-1', { name: 'private-in-memory-draft' }, []);

    expect(runtime.getSnapshot('artifact-1@revision-1').formData).toEqual({ name: 'private-in-memory-draft' });
    expect(runtime.getSnapshot('artifact-1@revision-2').formData).toEqual({});
    expect(listener).toHaveBeenCalled();
    runtime.resetAll();
    expect(JSON.stringify(runtime.getSnapshot('artifact-1@revision-1'))).not.toContain('private-in-memory-draft');
  });

  it('keeps retry identity across blur/remount and locks terminal submissions until data changes', () => {
    const runtime = new FormSessionRuntime();
    const key = 'artifact-1@revision-1';
    runtime.update(key, { name: 'Ada' }, []);
    expect(runtime.beginSubmission(key, () => 'stable-key')).toBe('stable-key');
    runtime.failSubmission(key);
    runtime.update(key, { name: 'Ada' }, []);
    expect(runtime.beginSubmission(key, () => 'different-key')).toBe('stable-key');
    runtime.completeSubmission(key, 'pending');
    expect(runtime.beginSubmission(key, () => 'third-key')).toBeNull();
    runtime.update(key, { name: 'Grace' }, []);
    expect(runtime.beginSubmission(key, () => 'new-data-key')).toBe('new-data-key');
  });
});
