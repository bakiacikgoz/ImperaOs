import { useMemo, useState } from 'react';

import type { ArtifactEditorProps } from '../ArtifactEditorHost';
import {
  nextSlideElementId,
  nextSlideId,
  parseSlidesArtifactContent,
  type SlidesArtifactSelection,
} from './slidesAdapter';
import './slides-artifact-editor.css';

export function SlidesArtifactEditor(props: ArtifactEditorProps) {
  const content = useMemo(() => parseSlidesArtifactContent(props.content), [props.content]);
  const [slideId, setSlideId] = useState(content.slides[0].id);
  const [elementId, setElementId] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const slide = content.slides.find((candidate) => candidate.id === slideId) ?? content.slides[0];
  const element = slide.elements.find((candidate) => candidate.id === elementId) ?? null;
  const readOnly = props.mode === 'view' || props.artifact.status === 'archived';

  const select = (nextSlideId: string, nextElementId: string | null) => {
    setSlideId(nextSlideId);
    setElementId(nextElementId);
    props.onSelectionChange({ kind: 'slides', slideId: nextSlideId, elementId: nextElementId });
  };
  const emit = (next: typeof content, selection: SlidesArtifactSelection) => {
    props.onChange(parseSlidesArtifactContent(next), selection);
  };

  return (
    <section className="slides-artifact-editor" aria-label="Structured slides editor">
      <header>
        <strong>{props.artifact.title}</strong>
        <span role="status">{props.saveState === 'saving' ? 'Saving slides…' : 'Slides ready'}</span>
        <button type="button" onClick={() => props.onRequestExport('pptx')}>Export PPTX</button>
      </header>
      <div className="slides-artifact-layout">
        <nav aria-label="Slide navigator">
          <ol>
            {content.slides.map((candidate, index) => (
              <li key={candidate.id}>
                <button
                  type="button"
                  aria-current={candidate.id === slide.id ? 'page' : undefined}
                  onClick={() => select(candidate.id, null)}
                >
                  {index + 1}. {candidate.title ?? candidate.id}
                </button>
              </li>
            ))}
          </ol>
          <button
            type="button"
            disabled={readOnly || content.slides.length >= 200}
            onClick={() => {
              const id = nextSlideId(content);
              const next = { ...content, slides: [...content.slides, { id, title: `Slide ${content.slides.length + 1}`, elements: [] }] };
              select(id, null);
              emit(next, { kind: 'slides', slideId: id, elementId: null });
            }}
          >Add slide</button>
        </nav>
        <div
          className="slides-artifact-stage"
          aria-label={`Slide ${slide.title ?? slide.id} canvas`}
          style={{ backgroundColor: `#${content.theme.backgroundColor}` }}
        >
          {slide.elements.map((candidate) => (
            <button
              type="button"
              key={candidate.id}
              className="slides-artifact-element"
              aria-pressed={candidate.id === elementId}
              aria-label={`${candidate.type} element ${candidate.id}`}
              style={{
                left: `${candidate.x / 13.333 * 100}%`, top: `${candidate.y / 7.5 * 100}%`,
                width: `${candidate.width / 13.333 * 100}%`, height: `${candidate.height / 7.5 * 100}%`,
              }}
              onClick={() => select(slide.id, candidate.id)}
            >
              {candidate.type === 'text' ? candidate.text : candidate.type}
            </button>
          ))}
        </div>
        <aside aria-label="Slide inspector">
          <h3>Inspector</h3>
          {element?.type === 'text' ? (
            <label>
              Text
              <textarea
                value={element.text}
                readOnly={readOnly}
                maxLength={20_000}
                onChange={(event) => {
                  const next = {
                    ...content,
                    slides: content.slides.map((candidate) => candidate.id === slide.id
                      ? { ...candidate, elements: candidate.elements.map((item) => item.id === element.id ? { ...item, text: event.target.value } : item) }
                      : candidate),
                  };
                  emit(next, { kind: 'slides', slideId: slide.id, elementId: element.id });
                }}
              />
            </label>
          ) : <p>{element ? `${element.type} selected` : 'Select an element.'}</p>}
          <button
            type="button"
            disabled={readOnly || slide.elements.length >= 500}
            onClick={() => {
              const id = nextSlideElementId(content, slide.id, 'text');
              const nextElement = {
                id, type: 'text' as const, x: 1, y: 1, width: 5, height: 1,
                text: 'New text', fontSize: 18, color: null, bold: false,
              };
              const next = {
                ...content,
                slides: content.slides.map((candidate) => candidate.id === slide.id
                  ? { ...candidate, elements: [...candidate.elements, nextElement] }
                  : candidate),
              };
              select(slide.id, id);
              emit(next, { kind: 'slides', slideId: slide.id, elementId: id });
            }}
          >Add text</button>
          <button
            type="button"
            disabled={readOnly || importing || !props.onImportAsset || slide.elements.length >= 500}
            onClick={async () => {
              if (!props.onImportAsset) return;
              setImporting(true);
              try {
                const asset = await props.onImportAsset();
                if (!asset) return;
                const id = nextSlideElementId(content, slide.id, 'image');
                const nextElement = {
                  id, type: 'image' as const, x: 1, y: 2.25, width: 4, height: 3,
                  assetId: asset.assetId, altText: asset.originalName ?? 'Imported local image',
                };
                const next = {
                  ...content,
                  assetIds: content.assetIds.includes(asset.assetId)
                    ? content.assetIds
                    : [...content.assetIds, asset.assetId],
                  slides: content.slides.map((candidate) => candidate.id === slide.id
                    ? { ...candidate, elements: [...candidate.elements, nextElement] }
                    : candidate),
                };
                select(slide.id, id);
                emit(next, { kind: 'slides', slideId: slide.id, elementId: id });
              } finally {
                setImporting(false);
              }
            }}
          >{importing ? 'Importing image…' : 'Import local image'}</button>
        </aside>
      </div>
    </section>
  );
}
