import { describe, expect, it } from 'vitest';

import {
  addCanvasShape,
  canvasOutline,
  canvasSelection,
  moveCanvasObjects,
  parseCanvasArtifactContent,
  resizeCanvasObject,
  withImportedCanvasAsset,
} from './canvasAdapter';

const content = {
  kind: 'canvas' as const,
  schemaVersion: 2 as const,
  snapshot: { objects: [
    { id: 'note-1', type: 'note' as const, x: 10, y: 20, width: 200, height: 100, text: 'Local note' },
    { id: 'ellipse-1', type: 'ellipse' as const, x: 300, y: 40, width: 120, height: 80 },
  ] },
  assetIds: [],
  embeds: 'deny' as const,
  remoteAssets: 'deny' as const,
};

describe('canvas adapter', () => {
  it('accepts only the strict local canvas contract and publishes coordinate-free selection', () => {
    expect(parseCanvasArtifactContent(content)).toEqual(content);
    expect(() => parseCanvasArtifactContent({ ...content, remoteAssets: 'allow' })).toThrow();
    expect(() => parseCanvasArtifactContent({ ...content, embeds: 'allow' })).toThrow();
    expect(canvasSelection(['ellipse-1', 'note-1', 'note-1'])).toEqual({
      kind: 'canvas', objectIds: ['ellipse-1', 'note-1'],
    });
  });

  it('adds allowed local shapes and uses imported local asset IDs without source URLs', () => {
    const shape = addCanvasShape(content, 'rectangle');
    expect(shape.snapshot.objects.at(-1)).toMatchObject({ id: 'rectangle-1', type: 'rectangle' });

    const image = withImportedCanvasAsset(content, 'asset-1');
    expect(image.assetIds).toEqual(['asset-1']);
    expect(image.snapshot.objects.at(-1)).toEqual(expect.objectContaining({
      id: 'image-1', type: 'image', assetId: 'asset-1',
    }));
    expect(JSON.stringify(image)).not.toContain('http');
  });

  it('moves and resizes selected shapes inside governed coordinate bounds', () => {
    expect(moveCanvasObjects(content, ['note-1', 'ellipse-1'], 15, -5).snapshot.objects).toEqual([
      expect.objectContaining({ id: 'note-1', x: 25, y: 15 }),
      expect.objectContaining({ id: 'ellipse-1', x: 315, y: 35 }),
    ]);
    expect(resizeCanvasObject(content, 'note-1', 240, 80).snapshot.objects[0]).toMatchObject({
      width: 240, height: 80,
    });
  });

  it('exposes a textual outline without raw markup', () => {
    expect(canvasOutline(content)).toEqual([
      { id: 'note-1', label: 'Local note', type: 'note' },
      { id: 'ellipse-1', label: 'Ellipse', type: 'ellipse' },
    ]);
  });
});
