import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../terminal/TerminalSurface', () => ({ TerminalSurface: ({ projectRootRef, active }: { projectRootRef?: string; active?: boolean }) => <div>Terminal surface {projectRootRef ?? 'runtime-root'} · {active ? 'active' : 'inactive'}</div> }));
vi.mock('../browser/BrowserSurface', () => ({ BrowserSurface: () => <div>Browser surface</div> }));
vi.mock('../browser/PreviewSurface', () => ({ PreviewSurface: () => <div>Preview surface</div> }));
vi.mock('./ProductArtifactWorkspace', () => ({ ProductArtifactWorkspace: ({ requestedArtifactId }: { requestedArtifactId?: string }) => <div>Artifact surface {requestedArtifactId ?? 'catalog'}</div> }));
vi.mock('./DataExplorerSurface', () => ({ DataExplorerSurface: () => <div>Data explorer surface</div> }));
vi.mock('./FilesNavigatorSurface', () => ({ FilesNavigatorSurface: () => <div>Files navigator surface</div> }));

import { getAssistantFixture } from '../../assistant/assistantFixtures';
import { renderOperatorPanel } from '../../test/render';
import { WorkspaceTabs } from './WorkspaceTabs';
import { createWorkspaceTab } from './workspaceTabState';

describe('WorkspaceTabs', () => {
  it('uses unique runtime tab IDs and delegates activation and close lifecycle', async () => {
    const first = createWorkspaceTab('terminal');
    const second = createWorkspaceTab('terminal');
    const onActivate = vi.fn();
    const onClose = vi.fn();
    expect(first.id).not.toBe(second.id);

    const { user } = renderOperatorPanel(<WorkspaceTabs tabs={[first, second]} activeTabId={second.id} assistantState={getAssistantFixture('running')} taskId="task-1" onActivate={onActivate} onClose={onClose} onUpdate={vi.fn()} onOpen={vi.fn()} />);

    expect(document.querySelector('.workspace-tab-strip .workspace-tab-list')).toBeInTheDocument();
    expect(document.querySelector('.workspace-tab.is-active')).toBeInTheDocument();
    expect(document.querySelector('.surface-content')).toBeInTheDocument();
    expect(screen.getByText('Terminal surface runtime-root · active')).toBeInTheDocument();
    await user.click(screen.getAllByRole('tab', { name: 'Terminal' })[0]);
    await user.click(screen.getAllByRole('button', { name: 'Close Terminal' })[1]);

    expect(onActivate).toHaveBeenCalledWith(first.id);
    expect(onClose).toHaveBeenCalledWith(second.id);
  });

  it('gives separately opened artifacts unique tabs instead of collapsing them into one workspace', () => {
    const document = createWorkspaceTab('artifacts', 'artifact-document');
    const spreadsheet = createWorkspaceTab('artifacts', 'artifact-spreadsheet');

    expect(document.id).not.toBe(spreadsheet.id);
  });

  it('hands an artifact-card selection to the canonical artifact workspace', () => {
    const artifact = createWorkspaceTab('artifacts', 'artifact-release-plan');

    renderOperatorPanel(<WorkspaceTabs tabs={[artifact]} activeTabId={artifact.id} assistantState={getAssistantFixture('running')} taskId="task-1" onActivate={vi.fn()} onClose={vi.fn()} onUpdate={vi.fn()} onOpen={vi.fn()} />);

    expect(screen.getByText('Artifact surface artifact-release-plan')).toBeInTheDocument();
  });

  it('passes only the opaque project-root reference to a user terminal', () => {
    const terminal = createWorkspaceTab('terminal');

    renderOperatorPanel(<WorkspaceTabs tabs={[terminal]} activeTabId={terminal.id} assistantState={getAssistantFixture('running')} taskId="task-1" projectRootRef="root-release" projectRootDisplayName="Release workspace" onActivate={vi.fn()} onClose={vi.fn()} onUpdate={vi.fn()} onOpen={vi.fn()} />);

    expect(screen.getByText('Terminal surface root-release · active')).toBeInTheDocument();
  });

  it('keeps inactive runtime surfaces mounted so a terminal session survives tab changes', () => {
    const first = createWorkspaceTab('terminal');
    const second = createWorkspaceTab('terminal');

    renderOperatorPanel(<WorkspaceTabs tabs={[first, second]} activeTabId={second.id} assistantState={getAssistantFixture('running')} taskId="task-1" onActivate={vi.fn()} onClose={vi.fn()} onUpdate={vi.fn()} onOpen={vi.fn()} />);

    expect(screen.getByText('Terminal surface runtime-root · inactive')).toBeInTheDocument();
    expect(screen.getByText('Terminal surface runtime-root · active')).toBeInTheDocument();
  });

  it('renders the first surviving workspace tab when the active id is stale', () => {
    const terminal = createWorkspaceTab('terminal');

    renderOperatorPanel(<WorkspaceTabs tabs={[terminal]} activeTabId="removed-tab" assistantState={getAssistantFixture('running')} taskId="task-1" onActivate={vi.fn()} onClose={vi.fn()} onUpdate={vi.fn()} onOpen={vi.fn()} />);

    expect(screen.getByText('Terminal surface runtime-root · active')).toBeInTheDocument();
  });

  it('opens every governed runtime surface from the UI Lab new-tab menu', async () => {
    const artifact = createWorkspaceTab('artifacts');
    const onOpen = vi.fn();
    const { user } = renderOperatorPanel(
      <WorkspaceTabs
        tabs={[artifact]}
        activeTabId={artifact.id}
        assistantState={getAssistantFixture('running')}
        taskId="task-1"
        onActivate={vi.fn()}
        onClose={vi.fn()}
        onUpdate={vi.fn()}
        onOpen={onOpen}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'New workspace tab' }));
    await user.click(screen.getByRole('menuitem', { name: /Terminal/ }));

    expect(onOpen).toHaveBeenCalledWith('terminal');
  });

  it.each([
    ['Data', 'data'],
    ['Files', 'files'],
  ] as const)('opens the real %s workspace surface from the new-tab menu', async (label, kind) => {
    const artifact = createWorkspaceTab('artifacts');
    const onOpen = vi.fn();
    const { user } = renderOperatorPanel(
      <WorkspaceTabs
        tabs={[artifact]}
        activeTabId={artifact.id}
        assistantState={getAssistantFixture('running')}
        taskId="task-1"
        onActivate={vi.fn()}
        onClose={vi.fn()}
        onUpdate={vi.fn()}
        onOpen={onOpen}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'New workspace tab' }));
    await user.click(screen.getByRole('menuitem', { name: new RegExp(label) }));

    expect(onOpen).toHaveBeenCalledWith(kind);
  });

  it('keeps the new-tab control available after the last workspace tab closes', () => {
    renderOperatorPanel(
      <WorkspaceTabs
        tabs={[]}
        activeTabId={null}
        assistantState={getAssistantFixture('running')}
        taskId="task-1"
        onActivate={vi.fn()}
        onClose={vi.fn()}
        onUpdate={vi.fn()}
        onOpen={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'New workspace tab' })).toBeEnabled();
  });
});
