import { describe, expect, it } from 'vitest';

import { frontendQaE2eBlockers } from './frontend-qa-policy';

describe('frontendQaE2eBlockers', () => {
  it('ignores stale failed E2E evidence in static-only mode', () => {
    expect(frontendQaE2eBlockers('failed', false)).toEqual([]);
  });

  it('blocks a failed E2E suite when E2E is required', () => {
    expect(frontendQaE2eBlockers('failed', true)).toEqual(['Playwright E2E failed']);
  });

  it('blocks a skipped E2E suite when E2E is required', () => {
    expect(frontendQaE2eBlockers('skipped', true)).toEqual(['Playwright E2E did not run']);
  });
});
