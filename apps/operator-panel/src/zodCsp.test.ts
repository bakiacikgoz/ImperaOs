import { describe, expect, it } from 'vitest';
import { z } from 'zod';

import './zodCsp';

describe('Zod CSP configuration', () => {
  it('disables dynamic-code schema compilation globally', () => {
    expect(z.config().jitless).toBe(true);
    expect(z.object({ value: z.string() }).parse({ value: 'safe' })).toEqual({ value: 'safe' });
  });
});
