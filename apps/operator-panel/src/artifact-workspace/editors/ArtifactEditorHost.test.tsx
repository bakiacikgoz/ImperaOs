import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ArtifactDescriptor, ArtifactRevision } from '../artifactContracts';
import { ArtifactEditorHost } from './ArtifactEditorHost';
import { FormSessionRuntime } from './form/formSessionRuntime';

vi.mock('./code/CodeArtifactEditor', () => ({
  CodeArtifactEditor: () => <div aria-label="Secure code editor">Execution is disabled.</div>,
}));
vi.mock('./flow/FlowArtifactEditor', () => ({
  FlowArtifactEditor: () => <div aria-label="Governed flow editor">Text outline</div>,
}));
vi.mock('./slides/SlidesArtifactEditor', () => ({
  SlidesArtifactEditor: () => <div aria-label="Structured slides editor">Slide navigator</div>,
}));
vi.mock('./spreadsheet/SpreadsheetArtifactEditor', () => ({
  SpreadsheetArtifactEditor: () => <div aria-label="Governed spreadsheet editor">Formula evaluation is disabled.</div>,
}));
vi.mock('./canvas/CanvasArtifactEditor', () => ({
  CanvasArtifactEditor: () => <div aria-label="Governed canvas editor">Local canvas fallback.</div>,
}));

const artifact = {
  artifactId: 'artifact-form-host', workspaceId: 'workspace-1', kind: 'form', title: 'Host form', status: 'active',
  schemaVersion: 1, dataClass: 'internal', currentRevisionId: 'revision-form-host', currentRevisionNumber: 4,
  sourceSessionId: null, sourceTurnId: null, createdByType: 'user', createdById: 'user-1', updatedById: 'user-1',
  createdAtUtc: '2026-07-16T08:00:00Z', updatedAtUtc: '2026-07-16T08:00:00Z', archivedAtUtc: null,
  etag: 'etag-4', metadata: {},
} satisfies ArtifactDescriptor;

const revision = {
  revisionId: 'revision-form-host', artifactId: artifact.artifactId, parentRevisionId: 'revision-form-3', baseRevisionId: null,
  revisionNumber: 4, schemaVersion: 1, mutationType: 'replace_content', contentRelpath: 'content/form.json', contentSha256: 'a'.repeat(64),
  contentSizeBytes: 100, contentEncoding: 'json', changeSummary: 'Updated', authorType: 'user', authorId: 'user-1',
  idempotencyKey: 'update-form-4', createdAtUtc: '2026-07-16T08:00:00Z',
} satisfies ArtifactRevision;

describe('ArtifactEditorHost form integration', () => {
  it('lazy-loads slides only through the scoped feature gate', async () => {
    const slidesArtifact = { ...artifact, artifactId: 'slides-1', kind: 'slides' as const, schemaVersion: 2 };
    const slidesRevision = { ...revision, artifactId: 'slides-1', schemaVersion: 2 };
    const content = {
      kind: 'slides' as const, schemaVersion: 2 as const,
      theme: { name: 'ImperaOS', backgroundColor: 'FFFFFF', foregroundColor: '172033', accentColor: '6E57FF' },
      slides: [{ id: 'slide-1', elements: [] }], assetIds: [],
    };
    const props = {
      artifact: slidesArtifact, revision: slidesRevision, content, mode: 'edit' as const,
      saveState: 'idle' as const, onChange: () => undefined, onSelectionChange: () => undefined,
      onRequestExport: () => undefined,
    };
    const { rerender } = render(<ArtifactEditorHost {...props} />);
    expect(screen.getByRole('status')).toHaveTextContent('disabled by policy');
    rerender(<ArtifactEditorHost {...props} slidesEnabled />);
    expect(await screen.findByLabelText('Structured slides editor')).toBeInTheDocument();
  });

  it('keeps the form editor forced off unless explicitly enabled', () => {
    render(
      <ArtifactEditorHost
        artifact={artifact}
        revision={revision}
        content={{ kind: 'form', schemaVersion: 1 }}
        mode="edit"
        saveState="idle"
        onChange={() => undefined}
        onSelectionChange={() => undefined}
        onRequestExport={() => undefined}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('disabled by policy');
    expect(screen.queryByRole('button', { name: 'Submit form' })).not.toBeInTheDocument();
  });

  it('lazy-loads the governed form editor and binds exact revision submission', async () => {
    const user = userEvent.setup();
    const onSubmitForm = vi.fn().mockResolvedValue({
      submissionId: 'submission-1', artifactId: artifact.artifactId, schemaRevisionId: revision.revisionId,
      status: 'accepted', responseSha256: 'b'.repeat(64), continuationAction: 'none',
      approvalId: null, reasonCode: 'FORM_CONTINUATION_NOT_REQUIRED', actionHash: null, disposition: 'created',
    });
    render(
      <ArtifactEditorHost
        artifact={artifact}
        revision={revision}
        content={{
          kind: 'form', schemaVersion: 1,
          schema: { type: 'object', properties: { email: { type: 'string', title: 'Email' } }, required: ['email'], additionalProperties: false },
          behavior: { submitMode: 'explicit', externalContinuation: 'deny' },
        }}
        mode="edit"
        saveState="idle"
        formRuntime={new FormSessionRuntime()}
        formEnabled
        onSubmitForm={onSubmitForm}
        onChange={() => undefined}
        onSelectionChange={() => undefined}
        onRequestExport={() => undefined}
      />,
    );
    await user.type(await screen.findByLabelText(/Email/, {}, { timeout: 5_000 }), 'ada@example.test');
    await user.click(screen.getByRole('button', { name: 'Submit form' }));
    expect(onSubmitForm).toHaveBeenCalledWith(expect.objectContaining({
      artifactId: artifact.artifactId,
      schemaRevisionId: revision.revisionId,
      response: { email: 'ada@example.test' },
      persistencePolicy: 'none',
      idempotencyKey: expect.stringMatching(/^form-submit-/),
    }));
    expect(await screen.findByRole('status')).toHaveTextContent('Form submitted.');
  }, 15_000);
});

describe('ArtifactEditorHost code integration', () => {
  const codeArtifact = { ...artifact, artifactId: 'artifact-code-host', kind: 'code' as const, title: 'Code', schemaVersion: 2 };
  const codeRevision = { ...revision, artifactId: codeArtifact.artifactId, revisionId: 'revision-code-host', schemaVersion: 2 };
  const codeContent = {
    kind: 'code' as const, schemaVersion: 2 as const, filename: 'main.ts', language: 'typescript' as const,
    text: 'export {};\n', lineEnding: 'lf' as const, executionPolicy: 'deny' as const,
  };

  it('keeps the code editor forced off unless explicitly enabled', () => {
    render(
      <ArtifactEditorHost
        artifact={codeArtifact}
        revision={codeRevision}
        content={codeContent}
        mode="edit"
        saveState="idle"
        onChange={() => undefined}
        onSelectionChange={() => undefined}
        onRequestExport={() => undefined}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('disabled by policy');
    expect(screen.queryByLabelText('Secure code editor')).not.toBeInTheDocument();
  });

  it('lazy-loads the governed code editor only when enabled', async () => {
    render(
      <ArtifactEditorHost
        artifact={codeArtifact}
        revision={codeRevision}
        content={codeContent}
        mode="edit"
        saveState="idle"
        codeEnabled
        onChange={() => undefined}
        onSelectionChange={() => undefined}
        onRequestExport={() => undefined}
      />,
    );
    expect(await screen.findByLabelText('Secure code editor')).toHaveTextContent('Execution is disabled');
  });
});

describe('ArtifactEditorHost flow integration', () => {
  const flowArtifact = { ...artifact, artifactId: 'artifact-flow-host', kind: 'flow' as const, title: 'Flow', schemaVersion: 2 };
  const flowRevision = { ...revision, artifactId: flowArtifact.artifactId, revisionId: 'revision-flow-host', schemaVersion: 2 };
  const flowContent = {
    kind: 'flow' as const, schemaVersion: 2 as const,
    nodes: [{ id: 'start', type: 'input' as const, position: { x: 0, y: 0 }, data: { label: 'Start' } }],
    edges: [], viewport: { x: 0, y: 0, zoom: 1 },
  };

  it('keeps the flow editor forced off unless explicitly enabled', () => {
    render(<ArtifactEditorHost
      artifact={flowArtifact} revision={flowRevision} content={flowContent} mode="edit" saveState="idle"
      onChange={() => undefined} onSelectionChange={() => undefined} onRequestExport={() => undefined}
    />);
    expect(screen.getByRole('status')).toHaveTextContent('disabled by policy');
  });

  it('lazy-loads the governed flow editor only when enabled', async () => {
    render(<ArtifactEditorHost
      artifact={flowArtifact} revision={flowRevision} content={flowContent} mode="edit" saveState="idle" flowEnabled
      onChange={() => undefined} onSelectionChange={() => undefined} onRequestExport={() => undefined}
    />);
    expect(await screen.findByLabelText('Governed flow editor')).toHaveTextContent('Text outline');
  });
});

describe('ArtifactEditorHost fallback editor integration', () => {
  const spreadsheetArtifact = { ...artifact, artifactId: 'spreadsheet-host', kind: 'spreadsheet' as const, schemaVersion: 2 };
  const spreadsheetRevision = { ...revision, artifactId: spreadsheetArtifact.artifactId, revisionId: 'spreadsheet-revision', schemaVersion: 2 };
  const spreadsheetContent = {
    kind: 'spreadsheet' as const, schemaVersion: 2 as const, calculationMode: 'disabled' as const,
    sheets: [{ id: 'sheet-1', name: 'Sheet 1', cells: {}, columns: [] }],
  };
  const canvasArtifact = { ...artifact, artifactId: 'canvas-host', kind: 'canvas' as const, schemaVersion: 2 };
  const canvasRevision = { ...revision, artifactId: canvasArtifact.artifactId, revisionId: 'canvas-revision', schemaVersion: 2 };
  const canvasContent = { kind: 'canvas' as const, schemaVersion: 2 as const, snapshot: { objects: [] }, assetIds: [], embeds: 'deny' as const, remoteAssets: 'deny' as const };

  it('loads governed open-source fallback editors when their rollout flags are enabled', async () => {
    const common = { mode: 'edit' as const, saveState: 'idle' as const, onChange: () => undefined, onSelectionChange: () => undefined, onRequestExport: () => undefined };
    const { rerender } = render(<ArtifactEditorHost {...common} artifact={spreadsheetArtifact} revision={spreadsheetRevision} content={spreadsheetContent} spreadsheetEnabled />);
    expect(await screen.findByLabelText('Governed spreadsheet editor')).toHaveTextContent('Formula evaluation is disabled');
    rerender(<ArtifactEditorHost {...common} artifact={canvasArtifact} revision={canvasRevision} content={canvasContent} canvasEnabled />);
    expect(await screen.findByLabelText('Governed canvas editor')).toHaveTextContent('Local canvas fallback');
  });
});
