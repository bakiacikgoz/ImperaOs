import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../../context/ThemeContext';
import type { ArtifactDescriptor, ArtifactRevision } from '../../artifactContracts';

vi.mock('@xyflow/react', async () => {
  const React = await import('react');
  return {
    ReactFlow: (props: Record<string, unknown>) => React.createElement('div', { 'aria-label': 'Flow canvas' },
      React.createElement('button', {
        type: 'button',
        onClick: () => (props.onNodesChange as (changes: unknown[]) => void)([
          { id: 'start', type: 'position', position: { x: 40, y: 20 }, dragging: false },
        ]),
      }, 'Move Start'),
      React.createElement('button', {
        type: 'button',
        onClick: () => {
          (props.onEdgesChange as (changes: unknown[]) => void)([{ id: 'edge-1', type: 'remove' }]);
          (props.onNodesChange as (changes: unknown[]) => void)([{ id: 'start', type: 'remove' }]);
        },
      }, 'Delete Start'),
      React.createElement('button', {
        type: 'button',
        onClick: () => (props.onSelectionChange as (selection: unknown) => void)({
          nodes: [{ id: 'start' }], edges: [{ id: 'edge-1' }],
        }),
      }, 'Select Start'),
      props.children as React.ReactNode,
    ),
    Background: () => null,
    Controls: () => null,
    Handle: () => null,
    Position: { Left: 'left', Right: 'right' },
    applyNodeChanges: (changes: Array<{ id: string; type?: string; position?: { x: number; y: number } }>, nodes: Array<Record<string, unknown>>) => (
      nodes.filter((node) => !changes.some((item) => item.id === node.id && item.type === 'remove')).map((node) => {
        const change = changes.find((item) => item.id === node.id);
        return change?.position ? { ...node, position: change.position } : node;
      })
    ),
    applyEdgeChanges: (changes: Array<{ id: string; type?: string }>, edges: Array<{ id: string }>) => (
      edges.filter((edge) => !changes.some((item) => item.id === edge.id && item.type === 'remove'))
    ),
    addEdge: (edge: unknown, edges: unknown[]) => [...edges, edge],
  };
});

import { FlowArtifactEditor } from './FlowArtifactEditor';

const artifact = {
  artifactId: 'artifact-flow-1', workspaceId: 'workspace-1', kind: 'flow', title: 'Approval flow', status: 'active',
  schemaVersion: 2, dataClass: 'internal', currentRevisionId: 'revision-flow-1', currentRevisionNumber: 1,
  sourceSessionId: null, sourceTurnId: null, createdByType: 'user', createdById: 'user-1', updatedById: 'user-1',
  createdAtUtc: '2026-07-16T08:00:00Z', updatedAtUtc: '2026-07-16T08:00:00Z', archivedAtUtc: null,
  etag: 'etag-flow-1', metadata: {},
} satisfies ArtifactDescriptor;

const revision = {
  revisionId: 'revision-flow-1', artifactId: artifact.artifactId, parentRevisionId: null, baseRevisionId: null,
  revisionNumber: 1, schemaVersion: 2, mutationType: 'create', contentRelpath: 'content/flow.json', contentSha256: 'a'.repeat(64),
  contentSizeBytes: 256, contentEncoding: 'json', changeSummary: 'Created', authorType: 'user', authorId: 'user-1',
  idempotencyKey: 'create-flow-1', createdAtUtc: '2026-07-16T08:00:00Z',
} satisfies ArtifactRevision;

const content = {
  kind: 'flow' as const, schemaVersion: 2 as const,
  nodes: [
    { id: 'start', type: 'input' as const, position: { x: 0, y: 0 }, data: { label: 'Start' } },
    { id: 'end', type: 'output' as const, position: { x: 180, y: 0 }, data: { label: 'End' } },
  ],
  edges: [{ id: 'edge-1', source: 'start', target: 'end' }],
  viewport: { x: 0, y: 0, zoom: 1 },
};

describe('FlowArtifactEditor', () => {
  it('emits validated node movement and coordinate-free selection with an outline', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onSelectionChange = vi.fn();
    render(
      <ThemeProvider mode="light">
        <FlowArtifactEditor
          artifact={artifact}
          revision={revision}
          content={content}
          mode="edit"
          saveState="idle"
          onChange={onChange}
          onSelectionChange={onSelectionChange}
          onRequestExport={() => undefined}
        />
      </ThemeProvider>,
    );

    expect(screen.getByRole('navigation', { name: 'Flow outline' })).toHaveTextContent('Start');
    expect(screen.getByRole('navigation', { name: 'Flow outline' })).toHaveTextContent('End');
    await user.click(screen.getByRole('button', { name: 'Move Start' }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
      kind: 'flow', schemaVersion: 2,
      nodes: expect.arrayContaining([expect.objectContaining({ id: 'start', position: { x: 40, y: 20 } })]),
    }));
    await user.click(within(screen.getByLabelText('Flow canvas')).getByRole('button', { name: 'Select Start' }));
    expect(onSelectionChange).toHaveBeenCalledWith({ kind: 'flow', nodeIds: ['start'], edgeIds: ['edge-1'] });
  });

  it('atomically removes a connected node after React Flow removes its edge first', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ThemeProvider mode="light">
        <FlowArtifactEditor
          artifact={artifact}
          revision={revision}
          content={content}
          mode="edit"
          saveState="idle"
          onChange={onChange}
          onSelectionChange={() => undefined}
          onRequestExport={() => undefined}
        />
      </ThemeProvider>,
    );

    await user.click(screen.getByRole('button', { name: 'Delete Start' }));

    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      nodes: [expect.objectContaining({ id: 'end' })],
      edges: [],
    }));
  });
});
