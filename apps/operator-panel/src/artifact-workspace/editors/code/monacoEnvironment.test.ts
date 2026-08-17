import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.hoisted(() => {
  if (typeof document !== 'undefined') {
    Object.defineProperty(document, 'queryCommandSupported', {
      configurable: true,
      value: () => false,
    });
  }
});

const { config } = vi.hoisted(() => ({ config: vi.fn() }));
vi.mock('@monaco-editor/react', () => ({ loader: { config } }));
vi.mock('monaco-editor/esm/vs/editor/editor.api', () => ({ editor: {}, languages: {} }));
[
  'bat/bat', 'cpp/cpp', 'csharp/csharp', 'go/go', 'java/java', 'markdown/markdown',
  'powershell/powershell', 'python/python', 'rust/rust', 'shell/shell', 'sql/sql', 'xml/xml', 'yaml/yaml',
].forEach((module) => {
  vi.mock(`monaco-editor/esm/vs/basic-languages/${module}.contribution`, () => ({}));
});
vi.mock('monaco-editor/esm/vs/language/css/monaco.contribution', () => ({}));
vi.mock('monaco-editor/esm/vs/language/html/monaco.contribution', () => ({}));
vi.mock('monaco-editor/esm/vs/language/json/monaco.contribution', () => ({}));
vi.mock('monaco-editor/esm/vs/language/typescript/monaco.contribution', () => ({}));

vi.mock('monaco-editor/esm/vs/editor/editor.worker?worker', () => ({
  default: class { readonly kind = 'editor'; },
}));
vi.mock('monaco-editor/esm/vs/language/json/json.worker?worker', () => ({
  default: class { readonly kind = 'json'; },
}));
vi.mock('monaco-editor/esm/vs/language/css/css.worker?worker', () => ({
  default: class { readonly kind = 'css'; },
}));
vi.mock('monaco-editor/esm/vs/language/html/html.worker?worker', () => ({
  default: class { readonly kind = 'html'; },
}));
vi.mock('monaco-editor/esm/vs/language/typescript/ts.worker?worker', () => ({
  default: class { readonly kind = 'typescript'; },
}));

import { configureMonacoEnvironment, resetMonacoEnvironmentForTests } from './monacoEnvironment';

describe('secure Monaco environment', () => {
  beforeEach(() => {
    config.mockClear();
    resetMonacoEnvironmentForTests();
  });

  it('configures the local module once and routes only local workers', () => {
    configureMonacoEnvironment();
    configureMonacoEnvironment();

    expect(config).toHaveBeenCalledTimes(1);
    const environment = (globalThis as unknown as {
      MonacoEnvironment: { getWorker(moduleId: string, label: string): { kind: string } };
    }).MonacoEnvironment;
    expect(environment.getWorker('', 'json').kind).toBe('json');
    expect(environment.getWorker('', 'css').kind).toBe('css');
    expect(environment.getWorker('', 'scss').kind).toBe('css');
    expect(environment.getWorker('', 'html').kind).toBe('html');
    expect(environment.getWorker('', 'typescript').kind).toBe('typescript');
    expect(environment.getWorker('', 'javascript').kind).toBe('typescript');
    expect(environment.getWorker('', 'python').kind).toBe('editor');
  });
});
