import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from 'react';

import type { CanvasArtifactContent } from '../../artifactContracts';
import type { ArtifactEditorProps } from '../ArtifactEditorHost';
import {
  addCanvasShape,
  addCanvasFreeDrawStroke,
  canvasOutline,
  canvasSelection,
  deleteCanvasObjects,
  moveCanvasObjects,
  parseCanvasArtifactContent,
  resizeCanvasObject,
  withImportedCanvasAsset,
  type CanvasShapeType,
} from './canvasAdapter';

type PointerOperation =
  | { kind: 'move'; objectIds: string[]; clientX: number; clientY: number }
  | { kind: 'resize'; objectId: string; originX: number; originY: number; width: number; height: number }
  | { kind: 'pan'; clientX: number; clientY: number; panX: number; panY: number }
  | { kind: 'draw'; points: Array<{ x: number; y: number }> };

type CanvasObject = CanvasArtifactContent['snapshot']['objects'][number];
type CachedCanvasAsset = { source: string; encodedBytes: number; sha256: string };

function isCanvasImage(object: CanvasObject): object is CanvasObject & { type: 'image'; assetId: string } {
  return object.type === 'image' && typeof object.assetId === 'string';
}

const SHAPES: Array<{ type: CanvasShapeType; label: string }> = [
  { type: 'rectangle', label: 'Rectangle' },
  { type: 'ellipse', label: 'Ellipse' },
  { type: 'text', label: 'Text' },
  { type: 'line', label: 'Line' },
  { type: 'arrow', label: 'Arrow' },
  { type: 'note', label: 'Note' },
];
const CANVAS_STAGE_FALLBACK_WIDTH = 900;
const CANVAS_STAGE_FALLBACK_HEIGHT = 420;
const MAX_VISIBLE_IMAGE_ASSETS = 32;
const MAX_DISPLAY_ASSET_ENCODED_BYTES = 32 * 1024 * 1024;
const MAX_ASSET_LOAD_CONCURRENCY = 4;

function contentKey(value: CanvasArtifactContent): string {
  return JSON.stringify(value);
}

export function CanvasArtifactEditor(props: ArtifactEditorProps) {
  const incoming = useMemo(() => parseCanvasArtifactContent(props.content), [props.content]);
  const incomingKey = useMemo(() => contentKey(incoming), [incoming]);
  const [canvas, setCanvas] = useState<CanvasArtifactContent>(incoming);
  const canvasRef = useRef(canvas);
  const emittedKey = useRef(incomingKey);
  const [history, setHistory] = useState<CanvasArtifactContent[]>([incoming]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [stageViewport, setStageViewport] = useState({
    width: CANVAS_STAGE_FALLBACK_WIDTH,
    height: CANVAS_STAGE_FALLBACK_HEIGHT,
  });
  const stageRef = useRef<HTMLDivElement | null>(null);
  const operation = useRef<PointerOperation | null>(null);
  const [importing, setImporting] = useState(false);
  const [assetSourceState, setAssetSourceState] = useState<{
    workspaceId: string;
    sources: Record<string, string>;
  }>({ workspaceId: props.artifact.workspaceId, sources: {} });
  const [assetLoadFailures, setAssetLoadFailures] = useState<string[]>([]);
  const [deferredAssetCount, setDeferredAssetCount] = useState(0);
  const assetCache = useRef(new Map<string, CachedCanvasAsset>());
  const assetCacheWorkspaceId = useRef(props.artifact.workspaceId);
  const assetLoadLanes = useRef(Array.from(
    { length: MAX_ASSET_LOAD_CONCURRENCY },
    () => Promise.resolve(),
  ));
  const nextAssetLoadLane = useRef(0);
  const assetLoadGeneration = useRef(0);
  const [freeDraw, setFreeDraw] = useState(false);
  const editable = props.mode !== 'view' && props.artifact.status !== 'archived';
  const outline = useMemo(() => canvasOutline(canvas), [canvas]);
  const visibleImageAssetIds = useMemo(() => {
    const left = -pan.x / zoom;
    const top = -pan.y / zoom;
    const right = left + stageViewport.width / zoom;
    const bottom = top + stageViewport.height / zoom;
    return [...new Set(canvas.snapshot.objects
      .filter(isCanvasImage)
      .filter((object) => object.x < right && object.x + object.width > left
        && object.y < bottom && object.y + object.height > top)
      .map((object) => object.assetId))];
  }, [canvas.snapshot.objects, pan.x, pan.y, stageViewport.height, stageViewport.width, zoom]);
  const visibleImageAssetKey = visibleImageAssetIds.join('\u0000');

  useEffect(() => {
    if (incomingKey === emittedKey.current) return;
    canvasRef.current = incoming;
    setCanvas(incoming);
    setHistory([incoming]);
    setHistoryIndex(0);
    setSelectedIds([]);
  }, [incoming, incomingKey]);

  useEffect(() => {
    const element = stageRef.current;
    if (!element || typeof ResizeObserver === 'undefined') return;
    const updateViewport = () => {
      const bounds = element.getBoundingClientRect();
      if (bounds.width > 0 && bounds.height > 0) {
        setStageViewport({ width: bounds.width, height: bounds.height });
      }
    };
    updateViewport();
    const observer = new ResizeObserver(updateViewport);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (assetCacheWorkspaceId.current !== props.artifact.workspaceId) {
      assetCache.current.clear();
      assetCacheWorkspaceId.current = props.artifact.workspaceId;
    }
    const generation = assetLoadGeneration.current + 1;
    assetLoadGeneration.current = generation;
    const allVisibleAssetIds = visibleImageAssetKey ? visibleImageAssetKey.split('\u0000') : [];
    const assetIds = allVisibleAssetIds.slice(0, MAX_VISIBLE_IMAGE_ASSETS);
    const overflowCount = Math.max(0, allVisibleAssetIds.length - assetIds.length);
    if (!assetIds.length || !props.onResolveAsset) {
      setAssetSourceState({ workspaceId: props.artifact.workspaceId, sources: {} });
      setAssetLoadFailures([]);
      setDeferredAssetCount(overflowCount);
      return;
    }
    let cancelled = false;
    const targetIds = new Set(assetIds);
    const sources: Record<string, string> = {};
    const failures: string[] = [];
    let deferred = overflowCount;
    let cachedEncodedBytes = Array.from(assetCache.current.values())
      .reduce((total, entry) => total + entry.encodedBytes, 0);
    for (const assetId of assetIds) {
      const cached = assetCache.current.get(assetId);
      if (cached) sources[assetId] = cached.source;
    }
    setAssetSourceState({ workspaceId: props.artifact.workspaceId, sources: { ...sources } });
    const pendingIds = assetIds.filter((assetId) => !assetCache.current.has(assetId));
    const resolveInBoundedLane = (assetId: string) => {
      const laneIndex = nextAssetLoadLane.current % MAX_ASSET_LOAD_CONCURRENCY;
      nextAssetLoadLane.current += 1;
      const request = assetLoadLanes.current[laneIndex]
        .then(() => generation === assetLoadGeneration.current
          ? props.onResolveAsset?.(assetId) ?? null
          : null);
      assetLoadLanes.current[laneIndex] = request.then(() => undefined, () => undefined);
      return request;
    };
    void Promise.all(pendingIds.map(async (assetId) => {
      try {
        const resolved = await resolveInBoundedLane(assetId);
        if (!resolved || resolved.asset.assetId !== assetId || resolved.asset.workspaceId !== props.artifact.workspaceId) {
          if (generation !== assetLoadGeneration.current) return;
          throw new Error(`Canvas asset ${assetId} could not be resolved safely.`);
        }
        if (generation !== assetLoadGeneration.current
          || assetCacheWorkspaceId.current !== props.artifact.workspaceId) return;
        const source = `data:${resolved.asset.mediaType};base64,${resolved.contentBase64}`;
        const encodedBytes = source.length;
        for (const [cachedId, cached] of assetCache.current) {
          if (cachedEncodedBytes + encodedBytes <= MAX_DISPLAY_ASSET_ENCODED_BYTES) break;
          if (targetIds.has(cachedId)) continue;
          assetCache.current.delete(cachedId);
          cachedEncodedBytes -= cached.encodedBytes;
        }
        if (cachedEncodedBytes + encodedBytes > MAX_DISPLAY_ASSET_ENCODED_BYTES) {
          deferred += 1;
          return;
        }
        assetCache.current.set(assetId, {
          source,
          encodedBytes,
          sha256: resolved.asset.sha256,
        });
        cachedEncodedBytes += encodedBytes;
        sources[assetId] = source;
      } catch {
        failures.push(assetId);
      }
    })).then(() => {
      if (!cancelled) {
        setAssetSourceState({ workspaceId: props.artifact.workspaceId, sources: { ...sources } });
        setAssetLoadFailures(failures);
        setDeferredAssetCount(deferred);
      }
    });
    return () => { cancelled = true; };
  }, [props.artifact.workspaceId, props.onResolveAsset, visibleImageAssetKey]);

  const select = useCallback((objectIds: string[]) => {
    const next = objectIds.length ? canvasSelection(objectIds).objectIds : [];
    setSelectedIds(next);
    props.onSelectionChange(next.length ? canvasSelection(next) : null);
    return next;
  }, [props]);

  const preview = useCallback((next: CanvasArtifactContent) => {
    canvasRef.current = next;
    setCanvas(next);
  }, []);

  const persist = useCallback((next: CanvasArtifactContent, nextSelection = selectedIds) => {
    const parsed = parseCanvasArtifactContent(next);
    const key = contentKey(parsed);
    preview(parsed);
    emittedKey.current = key;
    setHistory((previous) => [...previous.slice(0, historyIndex + 1), parsed]);
    setHistoryIndex((previous) => Math.min(previous + 1, historyIndex + 1));
    props.onChange(parsed, nextSelection.length ? canvasSelection(nextSelection) : undefined);
  }, [historyIndex, preview, props, selectedIds]);

  const moveSelected = useCallback((deltaX: number, deltaY: number) => {
    if (!editable || selectedIds.length === 0) return;
    persist(moveCanvasObjects(canvasRef.current, selectedIds, deltaX, deltaY));
  }, [editable, persist, selectedIds]);

  const undo = () => {
    if (!editable || historyIndex === 0) return;
    const next = history[historyIndex - 1];
    const remaining = selectedIds.filter((id) => next.snapshot.objects.some((object) => object.id === id));
    preview(next);
    emittedKey.current = contentKey(next);
    setHistoryIndex(historyIndex - 1);
    select(remaining);
    props.onChange(next, remaining.length ? canvasSelection(remaining) : undefined);
  };

  const redo = () => {
    if (!editable || historyIndex >= history.length - 1) return;
    const next = history[historyIndex + 1];
    const remaining = selectedIds.filter((id) => next.snapshot.objects.some((object) => object.id === id));
    preview(next);
    emittedKey.current = contentKey(next);
    setHistoryIndex(historyIndex + 1);
    select(remaining);
    props.onChange(next, remaining.length ? canvasSelection(remaining) : undefined);
  };

  const onObjectPointerDown = (event: PointerEvent<HTMLDivElement>, objectId: string) => {
    if (!editable) return;
    event.preventDefault();
    event.stopPropagation();
    const nextSelection = event.shiftKey
      ? selectedIds.includes(objectId)
        ? selectedIds.filter((id) => id !== objectId)
        : [...selectedIds, objectId]
      : selectedIds.includes(objectId) ? selectedIds : [objectId];
    const normalized = select(nextSelection);
    operation.current = { kind: 'move', objectIds: normalized, clientX: event.clientX, clientY: event.clientY };
  };

  const onStagePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const active = operation.current;
    if (!active) return;
    if (active.kind === 'move') {
      const deltaX = (event.clientX - active.clientX) / zoom;
      const deltaY = (event.clientY - active.clientY) / zoom;
      if (deltaX || deltaY) {
        preview(moveCanvasObjects(canvasRef.current, active.objectIds, deltaX, deltaY));
        operation.current = { ...active, clientX: event.clientX, clientY: event.clientY };
      }
    } else if (active.kind === 'resize') {
      const nextWidth = active.width + (event.clientX - active.originX) / zoom;
      const nextHeight = active.height + (event.clientY - active.originY) / zoom;
      preview(resizeCanvasObject(canvasRef.current, active.objectId, nextWidth, nextHeight));
    } else if (active.kind === 'pan') {
      setPan({ x: active.panX + event.clientX - active.clientX, y: active.panY + event.clientY - active.clientY });
    } else {
      active.points.push({ x: (event.clientX - pan.x) / zoom, y: (event.clientY - pan.y) / zoom });
    }
  };

  const onStagePointerUp = () => {
    const active = operation.current;
    operation.current = null;
    if (!active || active.kind === 'pan') return;
    if (active.kind === 'draw') {
      const stroke = addCanvasFreeDrawStroke(canvasRef.current, active.points);
      if (stroke.objectIds.length) {
        select(stroke.objectIds);
        persist(stroke.content, stroke.objectIds);
      }
      return;
    }
    persist(canvasRef.current, active.kind === 'move' ? active.objectIds : selectedIds);
  };

  const selectedObject = selectedIds.length === 1
    ? canvas.snapshot.objects.find((object) => object.id === selectedIds[0])
    : undefined;

  return (
    <section aria-label={`Canvas editor: ${props.artifact.title}`} style={{ display: 'grid', gap: 12 }}>
      <header style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
        <strong>{props.artifact.title}</strong>
        <span role="status" aria-live="polite">{props.saveState === 'saving' ? 'Saving canvas…' : 'Canvas ready'}</span>
        {editable ? <span>{selectedIds.length ? `${selectedIds.length} selected` : 'No selection'}</span> : <span>Read-only</span>}
      </header>

      <div role="toolbar" aria-label="Canvas tools" style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {SHAPES.map((shape) => (
          <button key={shape.type} type="button" disabled={!editable} onClick={() => {
            const next = addCanvasShape(canvasRef.current, shape.type);
            const id = next.snapshot.objects.at(-1)?.id;
            const nextSelection = id ? select([id]) : [];
            persist(next, nextSelection);
          }}>Add {shape.label.toLowerCase()}</button>
        ))}
        <button type="button" disabled={!editable} aria-pressed={freeDraw} onClick={() => setFreeDraw((value) => !value)}>Free draw</button>
        <button type="button" disabled={!editable || selectedIds.length === 0} onClick={() => {
          persist(deleteCanvasObjects(canvasRef.current, selectedIds), []);
          select([]);
        }}>Delete selection</button>
        <button type="button" disabled={!editable || importing || !props.onImportAsset} onClick={async () => {
          if (!props.onImportAsset) return;
          setImporting(true);
          try {
            const asset = await props.onImportAsset();
            if (!asset) return;
            const next = withImportedCanvasAsset(canvasRef.current, asset.assetId);
            const id = next.snapshot.objects.at(-1)?.id;
            const nextSelection = id ? select([id]) : [];
            persist(next, nextSelection);
          } finally {
            setImporting(false);
          }
        }}>{importing ? 'Importing local image…' : 'Import local image'}</button>
        <button type="button" disabled={!editable || historyIndex === 0} onClick={undo}>Undo</button>
        <button type="button" disabled={!editable || historyIndex >= history.length - 1} onClick={redo}>Redo</button>
        <button type="button" onClick={() => props.onRequestExport('json')}>Export JSON</button>
        <button type="button" onClick={() => props.onRequestExport('svg')}>Export SVG</button>
        <button type="button" onClick={() => props.onRequestExport('png')}>Export PNG</button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(180px, 260px)', gap: 12 }}>
        <div
          ref={stageRef}
          aria-label="Canvas stage"
          onPointerDown={(event) => {
            if (!editable || event.target !== event.currentTarget) return;
            operation.current = freeDraw
              ? { kind: 'draw', points: [{ x: (event.clientX - pan.x) / zoom, y: (event.clientY - pan.y) / zoom }] }
              : { kind: 'pan', clientX: event.clientX, clientY: event.clientY, panX: pan.x, panY: pan.y };
          }}
          onPointerMove={onStagePointerMove}
          onPointerUp={onStagePointerUp}
          onPointerCancel={onStagePointerUp}
          onWheel={(event) => {
            if (!event.ctrlKey && !event.metaKey) return;
            event.preventDefault();
            setZoom((current) => Math.min(4, Math.max(0.25, current + (event.deltaY < 0 ? 0.1 : -0.1))));
          }}
          style={{ position: 'relative', overflow: 'hidden', minHeight: 420, border: '1px solid #94a3b8', borderRadius: 8, background: 'repeating-linear-gradient(0deg, transparent, transparent 23px, rgba(100,116,139,.12) 24px), repeating-linear-gradient(90deg, transparent, transparent 23px, rgba(100,116,139,.12) 24px)', touchAction: 'none' }}
        >
          <div style={{ position: 'absolute', inset: 0, transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: '0 0' }}>
            {canvas.snapshot.objects.map((object) => {
              const selected = selectedIds.includes(object.id);
              const isLine = object.type === 'line' || object.type === 'arrow';
              const imageAssetId = isCanvasImage(object) ? object.assetId : null;
              return (
                <div
                  key={object.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`${object.type} ${object.id}`}
                  aria-pressed={selected}
                  onPointerDown={(event) => onObjectPointerDown(event, object.id)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      select(event.shiftKey ? [...selectedIds, object.id] : [object.id]);
                    }
                    if (editable && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
                      event.preventDefault();
                      const delta = event.shiftKey ? 10 : 1;
                      moveSelected(event.key === 'ArrowLeft' ? -delta : event.key === 'ArrowRight' ? delta : 0, event.key === 'ArrowUp' ? -delta : event.key === 'ArrowDown' ? delta : 0);
                    }
                  }}
                  style={{ position: 'absolute', left: object.x, top: object.y, width: object.width, height: object.height, boxSizing: 'border-box', cursor: editable ? 'move' : 'default', borderRadius: object.type === 'ellipse' ? '50%' : object.type === 'note' ? 8 : 0, display: 'grid', placeItems: 'center', padding: 8, textAlign: 'center', userSelect: 'none', ...(isLine ? { background: 'transparent', border: 'none', borderBottom: selected ? '3px solid #4f46e5' : '2px solid #334155', transform: 'skewY(24deg)' } : { background: object.type === 'note' ? '#fef3c7' : '#fff', border: selected ? '3px solid #4f46e5' : '2px solid #334155' }) }}
                >
                  {imageAssetId
                  && assetSourceState.workspaceId === props.artifact.workspaceId
                  && assetSourceState.sources[imageAssetId] ? (
                    <img
                      src={assetSourceState.sources[imageAssetId]}
                      alt={`Local asset ${imageAssetId}`}
                      draggable={false}
                      style={{ width: '100%', height: '100%', objectFit: 'contain', pointerEvents: 'none' }}
                    />
                  ) : <span>{imageAssetId ? `Local asset: ${imageAssetId}` : object.text ?? object.type}</span>}
                  {editable && selected && selectedIds.length === 1 ? <button type="button" aria-label={`Resize ${object.id}`} onPointerDown={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    operation.current = { kind: 'resize', objectId: object.id, originX: event.clientX, originY: event.clientY, width: object.width, height: object.height };
                  }} style={{ position: 'absolute', right: -8, bottom: -8, width: 16, height: 16, padding: 0, border: '1px solid #312e81', background: '#c7d2fe', cursor: 'nwse-resize' }}><span className="sr-only">Resize</span></button> : null}
                </div>
              );
            })}
          </div>
          <div style={{ position: 'absolute', right: 8, bottom: 8, display: 'flex', gap: 4 }}>
            <button type="button" aria-label="Zoom out" onClick={() => setZoom((current) => Math.max(0.25, current - 0.1))}>−</button>
            <output aria-label="Canvas zoom">{Math.round(zoom * 100)}%</output>
            <button type="button" aria-label="Zoom in" onClick={() => setZoom((current) => Math.min(4, current + 0.1))}>+</button>
            <button type="button" aria-label="Reset view" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>Reset</button>
          </div>
        </div>

        <aside style={{ display: 'grid', alignContent: 'start', gap: 12 }}>
          <nav aria-label="Canvas outline">
            <strong>Canvas outline</strong>
            <ol>
              {outline.map((item) => <li key={item.id}><button type="button" aria-label={`Select ${item.id} from outline`} aria-pressed={selectedIds.includes(item.id)} onClick={(event) => {
                select(event.shiftKey ? [...selectedIds, item.id] : [item.id]);
              }}>{item.label} <small>({item.type}; x {canvas.snapshot.objects.find((object) => object.id === item.id)?.x ?? 0}, y {canvas.snapshot.objects.find((object) => object.id === item.id)?.y ?? 0})</small></button></li>)}
            </ol>
          </nav>
          <div aria-label="Canvas inspector">
            <strong>Inspector</strong>
            {selectedObject?.text !== undefined ? <label style={{ display: 'grid', gap: 4 }}>Text
              <textarea aria-label="Canvas text" disabled={!editable} value={selectedObject.text ?? ''} maxLength={10_000} onChange={(event) => {
                const next = parseCanvasArtifactContent({ ...canvasRef.current, snapshot: { objects: canvasRef.current.snapshot.objects.map((object) => object.id === selectedObject.id ? { ...object, text: event.target.value } : object) } });
                persist(next, [selectedObject.id]);
              }} />
            </label> : <p>{selectedIds.length ? 'Select one text or note object to edit its text.' : 'Select an object.'}</p>}
          </div>
        </aside>
      </div>
      {assetLoadFailures.length ? <p role="alert">One or more governed local images could not be loaded.</p> : null}
      {deferredAssetCount ? <p role="status">{deferredAssetCount} visible image(s) were deferred to keep local display memory bounded.</p> : null}
    </section>
  );
}
