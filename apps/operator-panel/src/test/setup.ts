import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

if (typeof Document !== 'undefined' && !Document.prototype.elementsFromPoint) {
  Object.defineProperty(Document.prototype, 'elementsFromPoint', {
    configurable: true,
    value: () => [],
  });
}

afterEach(() => {
  cleanup();
});
