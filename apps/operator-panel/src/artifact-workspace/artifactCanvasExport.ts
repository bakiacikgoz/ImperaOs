import { artifactBridge as defaultBridge, type ArtifactBridge } from './artifactBridge';
import {
  CanvasArtifactExportContentSchema,
  CanvasArtifactContentSchema,
  type ArtifactContent,
  type ArtifactDescriptor,
  type ArtifactRevision,
} from './artifactContracts';
import { renderFlowPng } from './artifactFlowExport';

export type CanvasArtifactExportFormat = 'json' | 'svg' | 'png';

export type CanvasExportOutcome =
  | { status: 'cancelled' }
  | { status: 'exported'; basename: string; sha256: string; sizeBytes: number; exportId?: string };

export function serializeCanvasJson(content: unknown): Uint8Array {
  const parsed = CanvasArtifactExportContentSchema.parse(content);
  return new TextEncoder().encode(`${JSON.stringify(parsed, null, 2)}\n`);
}

const PADDING = 32;
const MAX_RASTER_DIMENSION = 4_096;
type CanvasResolvedAssets = Record<string, { dataUrl: string; sha256: string }>;
type CanvasObject = ReturnType<typeof CanvasArtifactContentSchema.parse>['snapshot']['objects'][number];

function isCanvasImage(object: CanvasObject): object is CanvasObject & { type: 'image'; assetId: string } {
  return object.type === 'image' && typeof object.assetId === 'string';
}

function escapeXml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

export function serializeCanvasSvg(value: unknown, assets: CanvasResolvedAssets = {}): { text: string; width: number; height: number } {
  const canvas = CanvasArtifactContentSchema.parse(value);
  const objects = canvas.snapshot.objects;
  const minimumX = Math.min(0, ...objects.map((item) => item.x)) - PADDING;
  const minimumY = Math.min(0, ...objects.map((item) => item.y)) - PADDING;
  const maximumX = Math.max(1, ...objects.map((item) => item.x + item.width)) + PADDING;
  const maximumY = Math.max(1, ...objects.map((item) => item.y + item.height)) + PADDING;
  const viewWidth = Math.max(1, maximumX - minimumX);
  const viewHeight = Math.max(1, maximumY - minimumY);
  const scale = Math.min(1, MAX_RASTER_DIMENSION / viewWidth, MAX_RASTER_DIMENSION / viewHeight);
  const width = Math.max(1, Math.ceil(viewWidth * scale));
  const height = Math.max(1, Math.ceil(viewHeight * scale));
  const body = objects.map((item) => {
    if (isCanvasImage(item)) {
      const asset = assets[item.assetId];
      if (!asset) throw new Error(`Canvas image asset ${item.assetId} is unavailable.`);
      return `<g data-object-type="image" data-asset-sha256="${escapeXml(asset.sha256)}"><image x="${item.x}" y="${item.y}" width="${item.width}" height="${item.height}" href="${escapeXml(asset.dataUrl)}" preserveAspectRatio="xMidYMid meet"/></g>`;
    }
    const label = escapeXml(item.text ?? '');
    if (item.type === 'line' || item.type === 'arrow') {
      return `<line x1="${item.x}" y1="${item.y}" x2="${item.x + item.width}" y2="${item.y + item.height}"${item.type === 'arrow' ? ' marker-end="url(#arrow)"' : ''}/>`;
    }
    const shape = item.type === 'ellipse'
      ? `<ellipse cx="${item.x + item.width / 2}" cy="${item.y + item.height / 2}" rx="${item.width / 2}" ry="${item.height / 2}"/>`
      : `<rect x="${item.x}" y="${item.y}" width="${item.width}" height="${item.height}" rx="${item.type === 'note' ? 8 : 0}"/>`;
    const text = label
      ? `<text x="${item.x + item.width / 2}" y="${item.y + item.height / 2}" text-anchor="middle" dominant-baseline="middle">${label}</text>`
      : '';
    return `<g data-object-type="${item.type}">${shape}${text}</g>`;
  }).join('');
  return {
    width,
    height,
    text: `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="${minimumX} ${minimumY} ${viewWidth} ${viewHeight}" role="img" aria-label="Governed canvas"><defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"/></marker></defs><style>rect,ellipse{fill:#fff;stroke:#334155;stroke-width:2}line{stroke:#64748b;stroke-width:2}text{fill:#0f172a;font:14px system-ui,sans-serif}</style>${body}</svg>`,
  };
}

export async function exportCanvasArtifact({
  artifact,
  revision,
  content,
  format = 'json',
  bridge = defaultBridge,
  renderPng = renderFlowPng,
}: {
  artifact: ArtifactDescriptor;
  revision: ArtifactRevision;
  content: ArtifactContent;
  format?: CanvasArtifactExportFormat;
  bridge?: ArtifactBridge;
  renderPng?: (svg: { text: string; width: number; height: number }) => Promise<Uint8Array>;
}): Promise<CanvasExportOutcome> {
  if (
    artifact.kind !== 'canvas'
    || artifact.schemaVersion !== revision.schemaVersion
    || ![1, 2].includes(revision.schemaVersion)
  ) {
    throw new Error('Canvas export requires an exact supported canvas revision.');
  }
  if (revision.schemaVersion === 1 && format !== 'json') {
    throw new Error('Legacy canvas revisions support JSON export only.');
  }
  const begin = await bridge.beginExport({
    artifactId: artifact.artifactId,
    revisionId: revision.revisionId,
    format,
    idempotencyKey: `export-${artifact.artifactId.slice(0, 48)}-${revision.revisionId.slice(0, 48)}-${globalThis.crypto.randomUUID()}`,
  });
  if (begin.cancelled) return { status: 'cancelled' };
  if (!begin.ticket) throw new Error('Native export did not return a ticket.');
  let commitStarted = false;
  try {
    const assets: CanvasResolvedAssets = {};
    if (format !== 'json') {
      const parsed = CanvasArtifactContentSchema.parse(content);
      const referencedAssetIds = [...new Set(parsed.snapshot.objects
        .filter(isCanvasImage)
        .map((object) => object.assetId))];
      let aggregateAssetBytes = 0;
      for (const assetId of referencedAssetIds) {
        const resolved = await bridge.getAsset(assetId);
        if (resolved.asset.assetId !== assetId || resolved.asset.workspaceId !== artifact.workspaceId) {
          throw new Error('Resolved canvas asset identity mismatch.');
        }
        aggregateAssetBytes += resolved.asset.sizeBytes;
        if (aggregateAssetBytes > begin.maxBytes) throw new Error('Canvas assets exceed the native size limit.');
        assets[assetId] = {
          dataUrl: `data:${resolved.asset.mediaType};base64,${resolved.contentBase64}`,
          sha256: resolved.asset.sha256,
        };
      }
    }
    const svg = format === 'json' ? null : serializeCanvasSvg(content, assets);
    if (format === 'png' && svg && svg.width * svg.height * 4 > begin.maxBytes) {
      throw new Error('Canvas export exceeds the native size limit.');
    }
    const bytes = format === 'json'
      ? serializeCanvasJson(content)
      : format === 'svg'
        ? new TextEncoder().encode(svg?.text ?? '')
        : await renderPng(svg as { text: string; width: number; height: number });
    if (bytes.byteLength > begin.maxBytes) {
      throw new Error('Canvas export exceeds the native size limit.');
    }
    commitStarted = true;
    const result = await bridge.commitExport(begin.ticket, bytes);
    return { status: 'exported', ...result, ...(begin.exportId ? { exportId: begin.exportId } : {}) };
  } catch (error) {
    if (!commitStarted) await bridge.cancelExport(begin.ticket).catch(() => undefined);
    throw error;
  }
}
