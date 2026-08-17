import { describe, expect, it } from 'vitest';

import { UI_LAB_THEME_MANIFEST } from './uiLabThemeManifest';

describe('UI Lab theme manifest', () => {
  it('pins the approved source revision and canonical theme files', () => {
    expect(UI_LAB_THEME_MANIFEST.sourceSha)
      .toBe('165208e90dd37376d5f0a21df22b7a1e7756aab5');
    expect(UI_LAB_THEME_MANIFEST.files).toEqual([
      'src/styles/tokens.css',
      'src/styles/globals.css',
      'src/styles/surfaces.css',
    ]);
  });
});
