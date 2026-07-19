import {
  SlidesArtifactContentSchema,
  type SlidesArtifactContent,
} from '../../artifactContracts';

export type SlidesArtifactSelection = {
  kind: 'slides';
  slideId: string;
  elementId: string | null;
};

export function parseSlidesArtifactContent(value: unknown): SlidesArtifactContent {
  return SlidesArtifactContentSchema.parse(value);
}

function nextId(prefix: string, existing: Iterable<string>): string {
  const used = new Set(existing);
  let index = 1;
  while (used.has(`${prefix}-${index}`)) index += 1;
  return `${prefix}-${index}`;
}

export function nextSlideId(content: SlidesArtifactContent): string {
  return nextId('slide', content.slides.map((slide) => slide.id));
}

export function nextSlideElementId(
  content: SlidesArtifactContent,
  slideId: string,
  type: SlidesArtifactContent['slides'][number]['elements'][number]['type'],
): string {
  const slide = content.slides.find((candidate) => candidate.id === slideId);
  if (!slide) throw new Error('Selected slide does not exist.');
  return nextId(type, slide.elements.map((element) => element.id));
}

export function serializeSlidesPreview(value: unknown): string {
  const content = parseSlidesArtifactContent(value);
  const preview = {
    theme: {
      name: content.theme.name,
      backgroundColor: content.theme.backgroundColor,
      foregroundColor: content.theme.foregroundColor,
      accentColor: content.theme.accentColor,
    },
    slides: content.slides.map((slide) => ({
      id: slide.id,
      title: slide.title ?? null,
      elements: slide.elements.map((element) => ({
        id: element.id,
        type: element.type,
        x: element.x,
        y: element.y,
        width: element.width,
        height: element.height,
      })),
    })),
  };
  return `${JSON.stringify(preview, null, 2)}\n`;
}
