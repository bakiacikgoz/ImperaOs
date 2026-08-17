import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  Controls,
  ReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type Viewport,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { FlowArtifactContent } from '../../artifactContracts';
import type { ArtifactEditorProps } from '../ArtifactEditorHost';
import {
  flowOutline,
  flowSelection,
  parseFlowArtifactContent,
  toReactFlowEdges,
  toReactFlowNodes,
} from './flowAdapter';

const PERSISTED_NODE_CHANGES = new Set(['add', 'remove', 'replace', 'position']);
const PERSISTED_EDGE_CHANGES = new Set(['add', 'remove', 'replace']);

function contentFromModels(
  nodes: Node[],
  edges: Edge[],
  viewport: Viewport,
): FlowArtifactContent {
  return parseFlowArtifactContent({
    kind: 'flow',
    schemaVersion: 2,
    nodes: nodes.map((node) => {
      const { artifactNodeType, label, description, artifactId } = node.data;
      return {
        id: node.id,
        type: artifactNodeType,
        position: node.position,
        data: {
          label,
          ...(description === undefined ? {} : { description }),
          ...(artifactId === undefined ? {} : { artifactId }),
        },
      };
    }),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      ...(typeof edge.label === 'string' ? { label: edge.label } : {}),
    })),
    viewport,
  });
}

export function FlowArtifactEditor({
  artifact,
  content,
  mode,
  saveState,
  onChange,
  onSelectionChange,
}: ArtifactEditorProps) {
  const flow = useMemo(() => parseFlowArtifactContent(content), [content]);
  const [nodes, setNodes] = useState<Node[]>(() => toReactFlowNodes(flow));
  const [edges, setEdges] = useState<Edge[]>(() => toReactFlowEdges(flow));
  const [viewport, setViewport] = useState<Viewport>(flow.viewport);
  const [validationMessage, setValidationMessage] = useState('');
  const models = useRef({
    nodes: toReactFlowNodes(flow),
    edges: toReactFlowEdges(flow),
    viewport: flow.viewport,
  });
  const editable = mode !== 'view' && artifact.status !== 'archived';
  const outline = useMemo(() => flowOutline(flow), [flow]);

  useEffect(() => {
    const nextNodes = toReactFlowNodes(flow);
    const nextEdges = toReactFlowEdges(flow);
    models.current = { nodes: nextNodes, edges: nextEdges, viewport: flow.viewport };
    setNodes(nextNodes);
    setEdges(nextEdges);
    setViewport(flow.viewport);
  }, [flow]);

  const emit = useCallback((nextNodes: Node[], nextEdges: Edge[], nextViewport = models.current.viewport) => {
    try {
      const next = contentFromModels(nextNodes, nextEdges, nextViewport);
      setValidationMessage('');
      onChange(next);
      return true;
    } catch {
      setValidationMessage('That change would make the governed flow invalid.');
      return false;
    }
  }, [onChange]);

  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    if (!editable) return;
    const nextNodes = applyNodeChanges(changes, models.current.nodes);
    const removedNodeIds = new Set(
      changes.filter((change) => change.type === 'remove').map((change) => change.id),
    );
    const nextEdges = removedNodeIds.size
      ? models.current.edges.filter(
        (edge) => !removedNodeIds.has(edge.source) && !removedNodeIds.has(edge.target),
      )
      : models.current.edges;
    models.current = { ...models.current, nodes: nextNodes, edges: nextEdges };
    setNodes(nextNodes);
    if (nextEdges !== edges) setEdges(nextEdges);
    if (changes.some((change) => PERSISTED_NODE_CHANGES.has(change.type))) {
      emit(nextNodes, nextEdges);
    }
  }, [edges, editable, emit]);

  const handleEdgesChange = useCallback((changes: EdgeChange[]) => {
    if (!editable) return;
    const nextEdges = applyEdgeChanges(changes, models.current.edges);
    models.current = { ...models.current, edges: nextEdges };
    setEdges(nextEdges);
    if (changes.some((change) => PERSISTED_EDGE_CHANGES.has(change.type))) {
      emit(models.current.nodes, nextEdges);
    }
  }, [editable, emit]);

  const handleConnect = useCallback((connection: Connection) => {
    if (!editable || !connection.source || !connection.target) return;
    const next = addEdge({
      ...connection,
      id: `edge-${globalThis.crypto.randomUUID()}`,
    }, models.current.edges);
    if (emit(models.current.nodes, next)) {
      models.current = { ...models.current, edges: next };
      setEdges(next);
    }
  }, [editable, emit]);

  return (
    <section className="flow-artifact-editor" aria-label={`Flow editor: ${artifact.title}`}>
      <div className="flow-artifact-toolbar" role="toolbar" aria-label="Flow artifact information">
        <strong>{artifact.title}</strong>
        <span>{nodes.length} nodes</span>
        <span>{edges.length} edges</span>
        <span role="status" aria-live="polite">{saveState}</span>
      </div>
      {validationMessage ? <p className="artifact-workspace-banner" role="alert">{validationMessage}</p> : null}
      <div className="flow-artifact-layout">
        <div className="flow-artifact-canvas" aria-label="Governed flow canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onConnect={handleConnect}
            onSelectionChange={({ nodes: selectedNodes, edges: selectedEdges }) => {
              onSelectionChange(flowSelection(
                selectedNodes.map((node) => node.id),
                selectedEdges.map((edge) => edge.id),
              ));
            }}
            onMoveEnd={(_event, nextViewport) => {
              if (!editable) return;
              models.current = { ...models.current, viewport: nextViewport };
              setViewport(nextViewport);
              emit(models.current.nodes, models.current.edges, nextViewport);
            }}
            defaultViewport={viewport}
            minZoom={0.05}
            maxZoom={8}
            nodesDraggable={editable}
            nodesConnectable={editable}
            elementsSelectable
            deleteKeyCode={editable ? ['Backspace', 'Delete'] : null}
            fitView
          >
            <Background />
            <Controls showInteractive={editable} />
          </ReactFlow>
        </div>
        <nav className="flow-artifact-outline" aria-label="Flow outline">
          <strong>Text outline</strong>
          <ol>
            {outline.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onSelectionChange(flowSelection([item.id], []))}
                  aria-label={`Select ${item.label}`}
                >
                  <span>{item.label}</span>
                  <small>{item.type}{item.outgoing.length ? ` → ${item.outgoing.join(', ')}` : ''}</small>
                </button>
              </li>
            ))}
          </ol>
        </nav>
      </div>
    </section>
  );
}
