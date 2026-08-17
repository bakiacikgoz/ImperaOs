import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import { UI_LAB_THEME_MANIFEST } from '../src/product-shell/styles/uiLabThemeManifest';

const themeRoot = path.resolve(process.cwd(), 'src/product-shell/styles/ui-lab');
const results = UI_LAB_THEME_MANIFEST.files.map((sourceFile) => {
  const filename = sourceFile.replace('src/styles/', '');
  const targetPath = path.join(themeRoot, filename);
  const actual = createHash('sha256').update(fs.readFileSync(targetPath)).digest('hex');
  const expected = UI_LAB_THEME_MANIFEST.sha256[sourceFile];
  if (actual !== expected) {
    throw new Error(`${sourceFile} digest mismatch: expected ${expected}, received ${actual}`);
  }
  return { sourceFile, targetPath, sha256: actual };
});

console.log(JSON.stringify({
  status: 'passed',
  sourceSha: UI_LAB_THEME_MANIFEST.sourceSha,
  files: results,
}, null, 2));
