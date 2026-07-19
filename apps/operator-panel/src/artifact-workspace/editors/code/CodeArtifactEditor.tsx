import MonacoEditor, { type OnMount } from '@monaco-editor/react';
import { useEffect, useMemo, useRef } from 'react';

import { useTheme } from '../../../context/ThemeContext';
import type { ArtifactEditorProps } from '../ArtifactEditorHost';
import {
  codeModelUri,
  codeSelectionFromMonaco,
  parseCodeArtifactContent,
} from './codeAdapter';
import { configureMonacoEnvironment } from './monacoEnvironment';

const LARGE_CODE_READONLY_BYTES = 1024 * 1024;

configureMonacoEnvironment();

export function CodeArtifactEditor({
  artifact,
  revision,
  content,
  mode,
  saveState,
  onChange,
  onSelectionChange,
}: ArtifactEditorProps) {
  const code = useMemo(() => parseCodeArtifactContent(content), [content]);
  const { resolvedTheme } = useTheme();
  const subscriptions = useRef<Array<{ dispose(): void }>>([]);
  const contentBytes = useMemo(() => new TextEncoder().encode(code.text).byteLength, [code.text]);
  const largeReadonly = contentBytes > LARGE_CODE_READONLY_BYTES;
  const legacyReadonly = (
    typeof content === 'object'
    && content !== null
    && 'schemaVersion' in content
    && content.schemaVersion === 1
  );
  const editable = mode !== 'view' && artifact.status !== 'archived' && !largeReadonly && !legacyReadonly;

  useEffect(() => () => {
    subscriptions.current.forEach((subscription) => subscription.dispose());
    subscriptions.current = [];
  }, []);

  const handleMount: OnMount = (editor) => {
    subscriptions.current.forEach((subscription) => subscription.dispose());
    subscriptions.current = [
      editor.onDidChangeCursorSelection((event) => {
        onSelectionChange(codeSelectionFromMonaco(event.selection));
      }),
      editor.onDidBlurEditorText(() => onSelectionChange(null)),
    ];
  };

  return (
    <section className="code-artifact-editor" aria-label={`Code editor: ${artifact.title}`}>
      <div className="code-artifact-toolbar" role="toolbar" aria-label="Code artifact information">
        <strong>{code.filename}</strong>
        <span>{code.language}</span>
        <span role="status" aria-live="polite">{saveState}</span>
      </div>
      <p className="artifact-workspace-banner" role="status">
        Code execution is disabled. This workspace only edits and exports text.
      </p>
      {largeReadonly ? (
        <p className="artifact-workspace-banner">Large code artifacts are read-only above 1 MiB.</p>
      ) : null}
      {legacyReadonly ? (
        <p className="artifact-workspace-banner">
          Legacy code revision opened read-only. Create a new current-schema code artifact to edit a reviewed copy.
        </p>
      ) : null}
      {!largeReadonly && !editable ? (
        <p className="artifact-workspace-banner">This revision is read-only.</p>
      ) : null}
      <MonacoEditor
        height="min(60vh, 720px)"
        path={codeModelUri(artifact.artifactId, code.filename)}
        language={code.language}
        theme={resolvedTheme === 'dark' ? 'vs-dark' : 'vs'}
        value={code.text}
        onMount={handleMount}
        onChange={(value) => {
          if (!editable || value === undefined) return;
          const normalizedText = code.lineEnding === 'crlf'
            ? value.replace(/\r?\n/g, '\r\n')
            : value.replace(/\r\n?/g, '\n');
          onChange(parseCodeArtifactContent({ ...code, text: normalizedText }));
        }}
        options={{
          accessibilitySupport: 'auto',
          ariaLabel: `Code text: ${code.filename}`,
          automaticLayout: true,
          codeLens: false,
          domReadOnly: !editable,
          editContext: false,
          links: false,
          minimap: { enabled: false },
          readOnly: !editable,
          scrollBeyondLastLine: false,
          wordWrap: 'off',
        }}
      />
      <span className="sr-only">Revision {revision.revisionNumber}. Execution policy deny.</span>
    </section>
  );
}
