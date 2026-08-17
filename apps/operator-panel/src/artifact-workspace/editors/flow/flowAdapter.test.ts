import { describe, expect, it } from 'vitest';

import {
  flowOutline,
  flowSelection,
  parseFlowArtifactContent,
  toReactFlowEdges,
  toReactFlowNodes,
} from './flowAdapter';

const content = {
  kind: 'flow' as const,
  schemaVersion: 2 as const,
  nodes: [
    { id: 'start', type: 'input' as const, position: { x: 0, y: 0 }, data: { label: 'Start' } },
    { id: 'end', type: 'output' as const, position: { x: 180, y: 0 }, data: { label: 'End' } },
  ],
  edges: [{ id: 'edge-1', source: 'start', target: 'end' }],
  viewport: { x: 0, y: 0, zoom: 1 },
};

describe('flow artifact adapter', () => {
  it('parses only a strict DAG and produces bounded React Flow models', () => {
    expect(parseFlowArtifactContent(content)).toEqual(content);
    expect(toReactFlowNodes(content)).toHaveLength(2);
    expect(toReactFlowEdges(content)).toHaveLength(1);
    expect(() => parseFlowArtifactContent({
      ...content,
      edges: [...content.edges, { id: 'edge-2', source: 'end', target: 'start' }],
    })).toThrow(/acyclic/i);
    expect(() => parseFlowArtifactContent({
      ...content,
      nodes: [{ ...content.nodes[0], data: { label: 'Start', url: 'https://example.com' } }],
      edges: [],
    })).toThrow();
  });

  it('keeps selection coordinate-free and exposes a textual outline', () => {
    expect(flowSelection(['end', 'start', 'start'], ['edge-1'])).toEqual({
      kind: 'flow', nodeIds: ['end', 'start'], edgeIds: ['edge-1'],
    });
    expect(flowOutline(content)).toEqual([
      { id: 'start', label: 'Start', type: 'input', outgoing: ['end'] },
      { id: 'end', label: 'End', type: 'output', outgoing: [] },
    ]);
  });
});
