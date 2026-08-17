import {
  CanvasArtifactContentSchema,
  type CanvasArtifactContent,
} from '../../artifactContracts';

const BOUNDED_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const MIN_COORDINATE = -1_000_000;
const MAX_COORDINATE = 1_000_000;
const MIN_SIZE = 1;
const MAX_SIZE = 1_000_000;

export type CanvasArtifactSelection = {
  kind: 'canvas';
  objectIds: string[];
};

export type CanvasShapeType = Exclude<CanvasArtifactContent['snapshot']['objects'][number]['type'], 'image'>;

export type CanvasOutlineItem = {
  id: string;
  label: string;
  type: CanvasArtifactContent['snapshot']['objects'][number]['type'];
};

export function parseCanvasArtifactContent(value: unknown): CanvasArtifactContent {
  return CanvasArtifactContentSchema.parse(value);
}

function nextId(prefix: string, existing: Iterable<string>): string {
  const used = new Set(existing);
  let index = 1;
  while (used.has(`${prefix}-${index}`)) index += 1;
  return `${prefix}-${index}`;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, Number.isFinite(value) ? value : minimum));
}

function labelFor(object: CanvasArtifactContent['snapshot']['objects'][number]): string {
  if (object.text?.trim()) return object.text.trim().slice(0, 120);
  if (object.type === 'image') return `Local asset ${object.assetId}`;
  return `${object.type[0].toUpperCase()}${object.type.slice(1)}`;
}

export function canvasSelection(objectIds: string[]): CanvasArtifactSelection {
  const unique = [...new Set(objectIds)];
  if (unique.length === 0 || unique.length > 500 || unique.some((id) => !BOUNDED_ID.test(id))) {
    throw new Error('Canvas selection contains an invalid object ID.');
  }
  return { kind: 'canvas', objectIds: unique };
}

export function canvasOutline(value: unknown): CanvasOutlineItem[] {
  return parseCanvasArtifactContent(value).snapshot.objects.map((object) => ({
    id: object.id,
    label: labelFor(object),
    type: object.type,
  }));
}

export function addCanvasShape(value: unknown, type: CanvasShapeType): CanvasArtifactContent {
  const canvas = parseCanvasArtifactContent(value);
  const object = {
    id: nextId(type, canvas.snapshot.objects.map((item) => item.id)),
    type,
    x: 80 + (canvas.snapshot.objects.length % 8) * 24,
    y: 80 + (canvas.snapshot.objects.length % 8) * 24,
    width: type === 'line' || type === 'arrow' ? 180 : 160,
    height: type === 'line' || type === 'arrow' ? 80 : 96,
    ...((type === 'text' || type === 'note') ? { text: type === 'note' ? 'New note' : 'New text' } : {}),
  } as CanvasArtifactContent['snapshot']['objects'][number];
  return parseCanvasArtifactContent({
    ...canvas,
    snapshot: { objects: [...canvas.snapshot.objects, object] },
  });
}

export function addCanvasFreeDrawStroke(
  value: unknown,
  points: Array<{ x: number; y: number }>,
): { content: CanvasArtifactContent; objectIds: string[] } {
  const canvas = parseCanvasArtifactContent(value);
  const bounded = points.slice(0, 500).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  if (bounded.length < 2) return { content: canvas, objectIds: [] };
  const objects = [...canvas.snapshot.objects];
  const objectIds: string[] = [];
  for (let index = 1; index < bounded.length; index += 1) {
    const start = bounded[index - 1];
    const end = bounded[index];
    const id = nextId('draw', objects.map((item) => item.id));
    objectIds.push(id);
    objects.push({
      id,
      type: 'line',
      x: clamp(Math.min(start.x, end.x), MIN_COORDINATE, MAX_COORDINATE),
      y: clamp(Math.min(start.y, end.y), MIN_COORDINATE, MAX_COORDINATE),
      width: clamp(Math.abs(end.x - start.x), MIN_SIZE, MAX_SIZE),
      height: clamp(Math.abs(end.y - start.y), MIN_SIZE, MAX_SIZE),
    });
  }
  return {
    content: parseCanvasArtifactContent({ ...canvas, snapshot: { objects } }),
    objectIds,
  };
}

export function deleteCanvasObjects(value: unknown, objectIds: string[]): CanvasArtifactContent {
  const canvas = parseCanvasArtifactContent(value);
  const selected = new Set(canvasSelection(objectIds).objectIds);
  return parseCanvasArtifactContent({
    ...canvas,
    snapshot: { objects: canvas.snapshot.objects.filter((object) => !selected.has(object.id)) },
  });
}

export function withImportedCanvasAsset(value: unknown, assetId: string): CanvasArtifactContent {
  const canvas = parseCanvasArtifactContent(value);
  if (!BOUNDED_ID.test(assetId)) throw new Error('Canvas assets require a local bounded asset ID.');
  const object = {
    id: nextId('image', canvas.snapshot.objects.map((item) => item.id)),
    type: 'image' as const,
    x: 100 + (canvas.snapshot.objects.length % 8) * 24,
    y: 100 + (canvas.snapshot.objects.length % 8) * 24,
    width: 240,
    height: 160,
    assetId,
  };
  return parseCanvasArtifactContent({
    ...canvas,
    assetIds: canvas.assetIds.includes(assetId) ? canvas.assetIds : [...canvas.assetIds, assetId],
    snapshot: { objects: [...canvas.snapshot.objects, object] },
  });
}

export function moveCanvasObjects(
  value: unknown,
  objectIds: string[],
  deltaX: number,
  deltaY: number,
): CanvasArtifactContent {
  const canvas = parseCanvasArtifactContent(value);
  const selected = new Set(canvasSelection(objectIds).objectIds);
  return parseCanvasArtifactContent({
    ...canvas,
    snapshot: {
      objects: canvas.snapshot.objects.map((object) => selected.has(object.id)
        ? {
            ...object,
            x: clamp(object.x + deltaX, MIN_COORDINATE, MAX_COORDINATE),
            y: clamp(object.y + deltaY, MIN_COORDINATE, MAX_COORDINATE),
          }
        : object),
    },
  });
}

export function resizeCanvasObject(
  value: unknown,
  objectId: string,
  width: number,
  height: number,
): CanvasArtifactContent {
  const canvas = parseCanvasArtifactContent(value);
  if (!BOUNDED_ID.test(objectId) || !canvas.snapshot.objects.some((object) => object.id === objectId)) {
    throw new Error('Canvas object does not exist.');
  }
  return parseCanvasArtifactContent({
    ...canvas,
    snapshot: {
      objects: canvas.snapshot.objects.map((object) => object.id === objectId
        ? { ...object, width: clamp(width, MIN_SIZE, MAX_SIZE), height: clamp(height, MIN_SIZE, MAX_SIZE) }
        : object),
    },
  });
}
