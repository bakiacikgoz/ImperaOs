import { describe, expect, it } from 'vitest';

import { nextSlideElementId, nextSlideId, parseSlidesArtifactContent, serializeSlidesPreview } from './slidesAdapter';

const content = {
  kind: 'slides', schemaVersion: 2,
  theme: { name: 'ImperaOS', backgroundColor: 'FFFFFF', foregroundColor: '172033', accentColor: '6E57FF' },
  slides: [{ id: 'slide-1', title: 'One', elements: [
    { id: 'text-1', type: 'text', x: 1, y: 1, width: 5, height: 1, text: 'Hello' },
  ] }],
  assetIds: [],
};

describe('slides adapter', () => {
  it('parses strict content and allocates deterministic local ids', () => {
    const parsed = parseSlidesArtifactContent(content);
    expect(nextSlideId(parsed)).toBe('slide-2');
    expect(nextSlideElementId(parsed, 'slide-1', 'text')).toBe('text-2');
  });

  it('emits a stable bounded preview independent from input key order', () => {
    const reordered = {
      assetIds: [], slides: content.slides, theme: content.theme,
      schemaVersion: 2, kind: 'slides',
    };
    expect(serializeSlidesPreview(reordered)).toBe(serializeSlidesPreview(content));
    expect(serializeSlidesPreview(content)).not.toContain('Hello');
  });
});
