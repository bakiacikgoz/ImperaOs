import { artifactBridge as defaultBridge, type ArtifactBridge } from './artifactBridge';
import type { ArtifactContent, ArtifactDescriptor, ArtifactRevision, FlowArtifactContent } from './artifactContracts';
import { parseFlowArtifactContent } from './editors/flow/flowAdapter';

export type FlowArtifactExportFormat = 'json' | 'svg' | 'png';
export type FlowArtifactExportOutcome =
  | { status: 'cancelled' }
  | { status: 'exported'; basename: string; sha256: string; sizeBytes: number; exportId?: string };

const NODE_WIDTH = 160;
const NODE_HEIGHT = 56;
const PADDING = 32;
const MAX_RASTER_DIMENSION = 4_096;
const MAX_RASTER_PIXELS = 16_000_000;

function escapeXml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

export function serializeFlowSvg(value: unknown): { text: string; width: number; height: number } {
  const flow = parseFlowArtifactContent(value);
  const minimumX = Math.min(0, ...flow.nodes.map((node) => node.position.x)) - PADDING;
  const minimumY = Math.min(0, ...flow.nodes.map((node) => node.position.y)) - PADDING;
  const maximumX = Math.max(NODE_WIDTH, ...flow.nodes.map((node) => node.position.x + NODE_WIDTH)) + PADDING;
  const maximumY = Math.max(NODE_HEIGHT, ...flow.nodes.map((node) => node.position.y + NODE_HEIGHT)) + PADDING;
  const viewWidth = Math.max(1, maximumX - minimumX);
  const viewHeight = Math.max(1, maximumY - minimumY);
  const scale = Math.min(1, MAX_RASTER_DIMENSION / viewWidth, MAX_RASTER_DIMENSION / viewHeight);
  const width = Math.max(1, Math.ceil(viewWidth * scale));
  const height = Math.max(1, Math.ceil(viewHeight * scale));
  const byId = new Map(flow.nodes.map((node) => [node.id, node]));
  const edges = flow.edges.map((edge) => {
    const source = byId.get(edge.source) as FlowArtifactContent['nodes'][number];
    const target = byId.get(edge.target) as FlowArtifactContent['nodes'][number];
    const label = edge.label
      ? `<text x="${(source.position.x + target.position.x + NODE_WIDTH) / 2}" y="${(source.position.y + target.position.y + NODE_HEIGHT) / 2 - 6}" text-anchor="middle">${escapeXml(edge.label)}</text>`
      : '';
    return `<g><line x1="${source.position.x + NODE_WIDTH / 2}" y1="${source.position.y + NODE_HEIGHT / 2}" x2="${target.position.x + NODE_WIDTH / 2}" y2="${target.position.y + NODE_HEIGHT / 2}" marker-end="url(#arrow)"/>${label}</g>`;
  }).join('');
  const nodes = flow.nodes.map((node) => (
    `<g data-node-type="${node.type}"><rect x="${node.position.x}" y="${node.position.y}" width="${NODE_WIDTH}" height="${NODE_HEIGHT}" rx="10"/><text x="${node.position.x + NODE_WIDTH / 2}" y="${node.position.y + NODE_HEIGHT / 2 + 5}" text-anchor="middle">${escapeXml(node.data.label)}</text></g>`
  )).join('');
  return {
    width,
    height,
    text: `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="${minimumX} ${minimumY} ${viewWidth} ${viewHeight}" role="img" aria-label="Governed flow"><defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"/></marker></defs><style>rect{fill:#fff;stroke:#334155;stroke-width:2}line{stroke:#64748b;stroke-width:2}text{fill:#0f172a;font:14px system-ui,sans-serif}</style>${edges}${nodes}</svg>`,
  };
}

export async function renderFlowPng(svg: { text: string; width: number; height: number }): Promise<Uint8Array> {
  if (svg.width * svg.height > MAX_RASTER_PIXELS) throw new Error('Flow PNG exceeds the raster pixel limit.');
  const blob = new Blob([svg.text], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  try {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error('Flow SVG could not be rasterized.'));
      image.src = url;
    });
    const canvas = document.createElement('canvas');
    canvas.width = svg.width;
    canvas.height = svg.height;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Flow PNG canvas is unavailable.');
    context.drawImage(image, 0, 0, svg.width, svg.height);
    const png = await new Promise<Blob>((resolve, reject) => canvas.toBlob(
      (value) => value ? resolve(value) : reject(new Error('Flow PNG encoding failed.')),
      'image/png',
    ));
    return new Uint8Array(await png.arrayBuffer());
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function exportFlowArtifact({
  artifact,
  revision,
  content,
  format,
  bridge = defaultBridge,
  renderPng = renderFlowPng,
}: {
  artifact: ArtifactDescriptor;
  revision: ArtifactRevision;
  content: ArtifactContent | FlowArtifactContent;
  format: FlowArtifactExportFormat;
  bridge?: ArtifactBridge;
  renderPng?: (svg: { text: string; width: number; height: number }) => Promise<Uint8Array>;
}): Promise<FlowArtifactExportOutcome> {
  if (artifact.kind !== 'flow') throw new Error('Only flow artifacts may use flow export.');
  if (revision.schemaVersion !== 2 || artifact.schemaVersion !== 2) throw new Error('Flow export requires schema version 2.');
  const parsed = parseFlowArtifactContent(content);
  const svg = format === 'json' ? null : serializeFlowSvg(parsed);
  const bytes = format === 'json'
    ? new TextEncoder().encode(`${JSON.stringify(parsed, null, 2)}\n`)
    : format === 'svg'
      ? new TextEncoder().encode(svg?.text ?? '')
      : await renderPng(svg as { text: string; width: number; height: number });
  const begin = await bridge.beginExport({
    artifactId: artifact.artifactId,
    revisionId: revision.revisionId,
    format,
    idempotencyKey: `export-${artifact.artifactId.slice(0, 48)}-${revision.revisionId.slice(0, 48)}-${globalThis.crypto.randomUUID()}`,
  });
  if (begin.cancelled) return { status: 'cancelled' };
  if (!begin.ticket) throw new Error('Native export did not return a ticket.');
  if (bytes.byteLength > begin.maxBytes) {
    await bridge.cancelExport(begin.ticket).catch(() => undefined);
    throw new Error('Flow export exceeds the native size limit.');
  }
  const result = await bridge.commitExport(begin.ticket, bytes);
  return { status: 'exported', ...result, ...(begin.exportId ? { exportId: begin.exportId } : {}) };
}
