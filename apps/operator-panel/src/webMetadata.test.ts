import { describe, expect, it } from 'vitest';

import rootPackageJson from '../../../package.json?raw';
import html from '../index.html?raw';
import appPackageJson from '../package.json?raw';

type PackageManifest = { name?: string };

function readJson(source: string): PackageManifest {
  return JSON.parse(source) as PackageManifest;
}

describe('web workspace metadata', () => {
  it('uses the canonical ImperaOS package and document identities', () => {
    const rootPackage = readJson(rootPackageJson);
    const appPackage = readJson(appPackageJson);

    expect(rootPackage.name).toBe('imperaos-workspace');
    expect(appPackage.name).toBe('imperaos-operator-panel');
    expect(html).toContain('<title>ImperaOS Operator Panel</title>');
  });

  it('keeps the approved brand-neutral favicon reference', () => {
    expect(html).toContain('href="/vite.svg"');
  });
});
