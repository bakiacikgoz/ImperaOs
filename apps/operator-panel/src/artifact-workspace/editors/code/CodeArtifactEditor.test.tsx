import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../../context/ThemeContext';
import type { ArtifactDescriptor, ArtifactRevision } from '../../artifactContracts';

vi.mock('./monacoEnvironment', () => ({ configureMonacoEnvironment: vi.fn() }));
vi.mock('@monaco-editor/react', async () => {
  const React = await import('react');
  type MockEditorProps = {
    value?: string;
    language?: string;
    path?: string;
    theme?: string;
    options?: { readOnly?: boolean; links?: boolean; accessibilitySupport?: string; editContext?: boolean };
    onChange?(value: string | undefined): void;
    onMount?(editor: {
      onDidChangeCursorSelection(listener: (event: { selection: Record<string, number> }) => void): { dispose(): void };
      onDidBlurEditorText(listener: () => void): { dispose(): void };
    }): void;
  };
  function MockMonacoEditor(props: MockEditorProps) {
      const selectionListener = React.useRef<((event: { selection: Record<string, number> }) => void) | null>(null);
      React.useEffect(() => {
        props.onMount?.({
          onDidChangeCursorSelection: (listener) => {
            selectionListener.current = listener;
            return { dispose: () => { selectionListener.current = null; } };
          },
          onDidBlurEditorText: () => ({ dispose: () => undefined }),
        });
      }, []);
      return React.createElement(React.Fragment, null,
        React.createElement('textarea', {
          'aria-label': 'Monaco code input',
          value: props.value,
          readOnly: props.options?.readOnly,
          onChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => props.onChange?.(event.target.value),
          'data-language': props.language,
          'data-path': props.path,
          'data-theme': props.theme,
          'data-links': String(props.options?.links),
          'data-accessibility': props.options?.accessibilitySupport,
          'data-edit-context': String(props.options?.editContext),
        }),
        React.createElement('button', {
          type: 'button',
          onClick: () => selectionListener.current?.({
            selection: { startLineNumber: 1, startColumn: 1, endLineNumber: 1, endColumn: 3 },
          }),
        }, 'Emit selection'),
      );
  }
  return {
    default: MockMonacoEditor,
  };
});

import { CodeArtifactEditor } from './CodeArtifactEditor';

const artifact = {
  artifactId: 'artifact-code-1', workspaceId: 'workspace-1', kind: 'code', title: 'Safe code', status: 'active',
  schemaVersion: 2, dataClass: 'internal', currentRevisionId: 'revision-code-1', currentRevisionNumber: 1,
  sourceSessionId: null, sourceTurnId: null, createdByType: 'user', createdById: 'user-1', updatedById: 'user-1',
  createdAtUtc: '2026-07-16T08:00:00Z', updatedAtUtc: '2026-07-16T08:00:00Z', archivedAtUtc: null,
  etag: 'etag-1', metadata: {},
} satisfies ArtifactDescriptor;

const revision = {
  revisionId: 'revision-code-1', artifactId: artifact.artifactId, parentRevisionId: null, baseRevisionId: null,
  revisionNumber: 1, schemaVersion: 2, mutationType: 'create', contentRelpath: 'content/code.json', contentSha256: 'a'.repeat(64),
  contentSizeBytes: 100, contentEncoding: 'json', changeSummary: 'Created', authorType: 'user', authorId: 'user-1',
  idempotencyKey: 'create-code-1', createdAtUtc: '2026-07-16T08:00:00Z',
} satisfies ArtifactRevision;

const content = {
  kind: 'code' as const, schemaVersion: 2 as const, filename: 'main.ts', language: 'typescript' as const,
  text: 'export {};\n', lineEnding: 'lf' as const, executionPolicy: 'deny' as const,
};

function renderEditor(overrides: Partial<React.ComponentProps<typeof CodeArtifactEditor>> = {}) {
  const props = {
    artifact,
    revision,
    content,
    mode: 'edit' as const,
    saveState: 'idle' as const,
    onChange: vi.fn(),
    onSelectionChange: vi.fn(),
    onRequestExport: vi.fn(),
    ...overrides,
  };
  render(<ThemeProvider mode="dark"><CodeArtifactEditor {...props} /></ThemeProvider>);
  return props;
}

describe('CodeArtifactEditor', () => {
  it('edits validated content, emits coordinate-only selection and exposes no execution UI', async () => {
    const user = userEvent.setup();
    const props = renderEditor();
    const editor = screen.getByLabelText('Monaco code input');
    expect(editor).not.toHaveAttribute('readonly');
    expect(editor).toHaveAttribute('data-language', 'typescript');
    expect(editor).toHaveAttribute('data-links', 'false');
    expect(editor).toHaveAttribute('data-accessibility', 'auto');
    expect(editor).toHaveAttribute('data-edit-context', 'false');
    expect(editor).toHaveAttribute('data-theme', 'vs-dark');
    fireEvent.change(editor, { target: { value: 'export {};\n// safe' } });
    expect(props.onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      kind: 'code', filename: 'main.ts', executionPolicy: 'deny', text: expect.stringContaining('// safe'),
    }));
    await user.click(screen.getByRole('button', { name: 'Emit selection' }));
    expect(props.onSelectionChange).toHaveBeenCalledWith({
      kind: 'code', startLineNumber: 1, startColumn: 1, endLineNumber: 1, endColumn: 3,
    });
    expect(screen.getByText(/execution is disabled/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /run|execute|terminal/i })).not.toBeInTheDocument();
  });

  it('keeps content over one MiB visible but read-only', () => {
    renderEditor({ content: { ...content, text: 'x'.repeat(1024 * 1024 + 1) } });
    expect(screen.getByLabelText('Monaco code input')).toHaveAttribute('readonly');
    expect(screen.getByText(/large code artifacts are read-only/i)).toBeInTheDocument();
  });

  it('opens compatible legacy v1 revisions read-only', () => {
    renderEditor({ content: { ...content, schemaVersion: 1 } });
    expect(screen.getByLabelText('Monaco code input')).toHaveAttribute('readonly');
    expect(screen.getByText(/legacy code revision opened read-only/i)).toBeInTheDocument();
  });
});
