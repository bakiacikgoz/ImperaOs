import { Position, type Edge, type Node } from '@xyflow/react';

import {
  FlowArtifactContentSchema,
  type FlowArtifactContent,
} from '../../artifactContracts';

const BOUNDED_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const FLOW_NODE_WIDTH = 160;
const FLOW_NODE_HEIGHT = 56;
const FLOW_HANDLE_SIZE = 8;

export type FlowArtifactSelection = {
  kind: 'flow';
  nodeIds: string[];
  edgeIds: string[];
};

export type FlowOutlineItem = {
  id: string;
  label: string;
  type: FlowArtifactContent['nodes'][number]['type'];
  outgoing: string[];
};

export function parseFlowArtifactContent(value: unknown): FlowArtifactContent {
  return FlowArtifactContentSchema.parse(value);
}

export function toReactFlowNodes(value: unknown): Node[] {
  return parseFlowArtifactContent(value).nodes.map((node) => ({
    id: node.id,
    type: 'default',
    position: node.position,
    data: { ...node.data, artifactNodeType: node.type },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    width: FLOW_NODE_WIDTH,
    height: FLOW_NODE_HEIGHT,
    initialWidth: FLOW_NODE_WIDTH,
    initialHeight: FLOW_NODE_HEIGHT,
    measured: { width: FLOW_NODE_WIDTH, height: FLOW_NODE_HEIGHT },
    handles: [
      {
        id: null,
        type: 'target',
        position: Position.Left,
        x: -FLOW_HANDLE_SIZE / 2,
        y: (FLOW_NODE_HEIGHT - FLOW_HANDLE_SIZE) / 2,
        width: FLOW_HANDLE_SIZE,
        height: FLOW_HANDLE_SIZE,
      },
      {
        id: null,
        type: 'source',
        position: Position.Right,
        x: FLOW_NODE_WIDTH - FLOW_HANDLE_SIZE / 2,
        y: (FLOW_NODE_HEIGHT - FLOW_HANDLE_SIZE) / 2,
        width: FLOW_HANDLE_SIZE,
        height: FLOW_HANDLE_SIZE,
      },
    ],
  }));
}

export function toReactFlowEdges(value: unknown): Edge[] {
  return parseFlowArtifactContent(value).edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label ?? undefined,
  }));
}

function uniqueBoundedIds(values: string[]): string[] {
  const unique = [...new Set(values)];
  if (unique.length > 5_000 || unique.some((value) => !BOUNDED_ID.test(value))) {
    throw new Error('Flow selection contains an invalid ID.');
  }
  return unique;
}

export function flowSelection(nodeIds: string[], edgeIds: string[]): FlowArtifactSelection {
  return {
    kind: 'flow',
    nodeIds: uniqueBoundedIds(nodeIds),
    edgeIds: uniqueBoundedIds(edgeIds),
  };
}

export function flowOutline(value: unknown): FlowOutlineItem[] {
  const flow = parseFlowArtifactContent(value);
  const outgoing = new Map(flow.nodes.map((node) => [node.id, [] as string[]]));
  flow.edges.forEach((edge) => outgoing.get(edge.source)?.push(edge.target));
  return flow.nodes.map((node) => ({
    id: node.id,
    label: node.data.label,
    type: node.type,
    outgoing: outgoing.get(node.id) ?? [],
  }));
}
