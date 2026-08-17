import { describe, expect, it } from 'vitest';

import { resolveProductShellMode } from './product-shell/productShellMode';

describe('resolveProductShellMode', () => {
  it('runs the product shell by default and retains an explicit legacy rollback', () => {
    expect(resolveProductShellMode({} as ImportMetaEnv)).toBe('v2');
    expect(resolveProductShellMode({ VITE_IMPERAOS_PRODUCT_SHELL: 'legacy' } as unknown as ImportMetaEnv)).toBe('legacy');
  });
});
