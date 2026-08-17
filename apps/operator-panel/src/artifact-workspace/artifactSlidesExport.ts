import SlidesPptxWorker from './slidesPptx.worker?worker';
import { artifactBridge as defaultBridge, type ArtifactBridge } from './artifactBridge';
import {
  SlidesArtifactContentSchema,
  type ArtifactContent,
  type ArtifactDescriptor,
  type ArtifactRevision,
} from './artifactContracts';
import type { SlidesPptxSerializeRequest } from './slidesPptxSerializer';

export type SlidesExportOutcome =
  | { status: 'cancelled' }
  | { status: 'exported'; basename: string; sha256: string; sizeBytes: number; exportId?: string };

export function serializeSlidesInWorker(request: SlidesPptxSerializeRequest): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const worker = new SlidesPptxWorker();
    worker.onmessage = (event: MessageEvent<{ ok: boolean; bytes?: Uint8Array; error?: string }>) => {
      worker.terminate();
      if (event.data.ok && event.data.bytes) resolve(new Uint8Array(event.data.bytes));
      else reject(new Error(event.data.error ?? 'Slides PPTX serialization failed safely.'));
    };
    worker.onerror = () => {
      worker.terminate();
      reject(new Error('Slides PPTX worker failed safely.'));
    };
    worker.postMessage(request);
  });
}

export async function exportSlidesArtifact({
  artifact, revision, content, bridge = defaultBridge, serialize = serializeSlidesInWorker,
}: {
  artifact: ArtifactDescriptor;
  revision: ArtifactRevision;
  content: ArtifactContent;
  bridge?: ArtifactBridge;
  serialize?: (request: SlidesPptxSerializeRequest) => Promise<Uint8Array>;
}): Promise<SlidesExportOutcome> {
  if (artifact.kind !== 'slides' || artifact.schemaVersion !== 2 || revision.schemaVersion !== 2) {
    throw new Error('PPTX export requires an exact slides.v2 revision.');
  }
  const parsed = SlidesArtifactContentSchema.parse(content);
  const begin = await bridge.beginExport({
    artifactId: artifact.artifactId,
    revisionId: revision.revisionId,
    format: 'pptx',
    idempotencyKey: `export-${artifact.artifactId.slice(0, 48)}-${revision.revisionId.slice(0, 48)}-${globalThis.crypto.randomUUID()}`,
  });
  if (begin.cancelled) return { status: 'cancelled' };
  if (!begin.ticket) throw new Error('Native export did not return a ticket.');
  let commitStarted = false;
  try {
    const referencedAssetIds = [...new Set(parsed.slides.flatMap((slide) =>
      slide.elements.filter((element) => element.type === 'image').map((element) => element.assetId),
    ))];
    const assets: Record<string, { dataUrl: string; sha256: string }> = {};
    let aggregateAssetBytes = 0;
    for (const assetId of referencedAssetIds) {
      const resolved = await bridge.getAsset(assetId);
      if (resolved.asset.assetId !== assetId) throw new Error('Resolved slide asset identity mismatch.');
      aggregateAssetBytes += resolved.asset.sizeBytes;
      if (aggregateAssetBytes > begin.maxBytes) {
        throw new Error('Slides assets exceed the native export size limit.');
      }
      assets[assetId] = {
        dataUrl: `data:${resolved.asset.mediaType};base64,${resolved.contentBase64}`,
        sha256: resolved.asset.sha256,
      };
    }
    const bytes = await serialize({ content: parsed, assets });
    if (bytes.byteLength > begin.maxBytes) {
      throw new Error('Slides PPTX export exceeds the native size limit.');
    }
    commitStarted = true;
    const result = await bridge.commitExport(begin.ticket, bytes);
    return { status: 'exported', ...result, ...(begin.exportId ? { exportId: begin.exportId } : {}) };
  } catch (error) {
    if (!commitStarted) await bridge.cancelExport(begin.ticket).catch(() => undefined);
    throw error;
  }
}
