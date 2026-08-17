import { StrictMode } from 'react';
import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const workspace = vi.hoisted(() => ({
  loadCatalog: vi.fn(),
  controller: {
    open: true,
    state: { tabs: [] },
    legacyArtifacts: [{ name: 'Release plan', summary: 'Ready', value: {} }],
    selectedLegacyArtifactName: 'Release plan',
    catalog: [],
    catalogNextCursor: null,
    catalogLoading: false,
    history: [],
    historyNextCursor: null,
    historyLoadingArtifactId: null,
    comparison: null,
    conflictResolving: null,
    error: null,
    operationNotice: null,
    formRuntime: undefined,
    actions: {
      open: vi.fn(),
      toggle: vi.fn(),
      openArtifact: vi.fn(),
      selectLegacyArtifact: vi.fn(),
      loadCatalog: vi.fn(),
      loadMoreCatalog: vi.fn(),
      activate: vi.fn(),
      requestClose: vi.fn(),
      loadHistory: vi.fn(),
      loadMoreHistory: vi.fn(),
      compareRevision: vi.fn(),
      closeComparison: vi.fn(),
      refreshConflict: vi.fn(),
      compareConflict: vi.fn(),
      reloadConflict: vi.fn(),
      forkConflict: vi.fn(),
      edit: vi.fn(),
      retrySave: vi.fn(),
      restore: vi.fn(),
      importAsset: vi.fn(),
      resolveAsset: vi.fn(),
      submitForm: vi.fn(),
      exportCode: vi.fn(),
      exportSlides: vi.fn(),
      exportStructured: vi.fn(),
      exportCanvas: vi.fn(),
      exportFlow: vi.fn(),
      exportSpreadsheet: vi.fn(),
      exportDocument: vi.fn(),
    },
  },
}));
workspace.controller.actions.loadCatalog = workspace.loadCatalog;

vi.mock('../../artifact-workspace/useAssistantArtifactWorkspaceController', () => ({
  useAssistantArtifactWorkspaceController: () => workspace.controller,
}));
vi.mock('../../components/assistant/AssistantWorkbench', () => ({
  AssistantWorkbench: ({ onViewRuns }: { onViewRuns: () => void }) => (
    <button type="button" onClick={onViewRuns}>Open artifacts</button>
  ),
}));

import { getAssistantFixture } from '../../assistant/assistantFixtures';
import { renderOperatorPanel } from '../../test/render';
import { ProductArtifactWorkspace } from './ProductArtifactWorkspace';

describe('ProductArtifactWorkspace', () => {
  it('requests an idempotent open exactly once for a workspace tab mount', () => {
    workspace.controller.open = false;
    workspace.controller.actions.open.mockClear();
    workspace.controller.actions.toggle.mockClear();

    renderOperatorPanel(
      <StrictMode>
        <ProductArtifactWorkspace state={getAssistantFixture('running')} openRequest={1} />
      </StrictMode>,
    );

    workspace.controller.open = true;
    expect(workspace.controller.actions.open).toHaveBeenCalledOnce();
    expect(workspace.controller.actions.toggle).not.toHaveBeenCalled();
  });

  it('refreshes the real governed catalog instead of leaving Open artifacts as a no-op', async () => {
    const { user } = renderOperatorPanel(
      <ProductArtifactWorkspace state={getAssistantFixture('running')} openRequest={1} />,
    );

    await user.click(screen.getByRole('button', { name: 'Open artifacts' }));

    expect(workspace.loadCatalog).toHaveBeenCalledOnce();
  });
});
