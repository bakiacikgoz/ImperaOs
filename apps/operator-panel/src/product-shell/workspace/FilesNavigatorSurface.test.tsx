import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const artifacts = vi.hoisted(() => ({ list: vi.fn() }));

vi.mock('../../artifact-workspace/artifactBridge', () => ({ artifactBridge: artifacts }));

import { renderOperatorPanel } from '../../test/render';
import { FilesNavigatorSurface } from './FilesNavigatorSurface';

describe('FilesNavigatorSurface', () => {
  beforeEach(() => {
    artifacts.list.mockResolvedValue({
      items: [
        {
          artifactId: 'artifact-release',
          title: 'Release checklist',
          kind: 'document',
          status: 'active',
          updatedAtUtc: '2026-07-29T12:00:00Z',
          dataClass: 'internal',
        },
      ],
      nextCursor: null,
    });
  });

  it('lists governed artifacts and opens a selection through the workspace owner', async () => {
    const onOpenArtifact = vi.fn();
    const { user } = renderOperatorPanel(
      <FilesNavigatorSurface onOpenArtifact={onOpenArtifact} />,
    );

    await user.click(await screen.findByRole('button', { name: /Release checklist/ }));

    expect(artifacts.list).toHaveBeenCalledWith({ limit: 100 });
    expect(onOpenArtifact).toHaveBeenCalledWith('artifact-release');
    expect(screen.getByText(/arbitrary project filesystem access is not enabled/i)).toBeInTheDocument();
  });

  it('shows the exact governed catalog error instead of an empty fake file tree', async () => {
    artifacts.list.mockRejectedValue(new Error('Artifact catalog denied by policy'));

    renderOperatorPanel(<FilesNavigatorSurface onOpenArtifact={vi.fn()} />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Artifact catalog denied by policy');
  });
});
