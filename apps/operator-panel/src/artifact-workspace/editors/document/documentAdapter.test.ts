import { describe, expect, it } from 'vitest';

import {
  parseDocumentArtifactContent,
  selectionFromBlockIds,
  serializeDocumentBlocks,
  serializeDocumentToHtml,
  serializeDocumentToMarkdown,
} from './documentAdapter';

describe('document artifact adapter', () => {
  it('preserves stable native BlockNote IDs through parse and serialize', () => {
    const content = parseDocumentArtifactContent({
      kind: 'document',
      schemaVersion: 1,
      language: 'en',
      pageMode: 'document',
      blocks: [
        {
          id: 'block-stable-1',
          type: 'paragraph',
          props: { textAlignment: 'left', textColor: 'default', backgroundColor: 'default' },
          content: [{ type: 'text', text: 'Governed draft', styles: {} }],
          children: [],
        },
      ],
    });

    const serialized = serializeDocumentBlocks(content, content.blocks);

    expect(serialized.blocks[0]).toMatchObject({ id: 'block-stable-1', type: 'paragraph' });
    expect(serialized.language).toBe('en');
    expect(serialized.pageMode).toBe('document');
  });

  it.each([
    ['remote link', [{ id: 'block-1', type: 'paragraph', content: [{ type: 'link', href: 'https://example.com', content: [] }] }]],
    ['remote embed', [{ id: 'block-1', type: 'image', props: { url: 'https://example.com/a.png' }, content: [] }]],
    ['missing stable id', [{ type: 'paragraph', content: [] }]],
  ])('rejects unsafe or unstable %s before editor mount', (_label, blocks) => {
    expect(() =>
      parseDocumentArtifactContent({
        kind: 'document',
        schemaVersion: 1,
        language: 'en',
        pageMode: 'document',
        blocks,
      }),
    ).toThrow();
  });

  it('projects bounded block selections without raw text', () => {
    expect(selectionFromBlockIds(['block-1', 'block-2', 'block-2'])).toEqual({
      kind: 'document',
      blockIds: ['block-1', 'block-2'],
    });
    expect(selectionFromBlockIds([])).toBeNull();
  });

  it.each([
    [
      'top-level',
      [
        { id: 'duplicate', type: 'paragraph', content: [], children: [] },
        { id: 'duplicate', type: 'paragraph', content: [], children: [] },
      ],
    ],
    [
      'nested',
      [
        {
          id: 'duplicate',
          type: 'paragraph',
          content: [],
          children: [{ id: 'duplicate', type: 'paragraph', content: [], children: [] }],
        },
      ],
    ],
  ])('rejects duplicate stable block IDs across the %s tree', (_label, blocks) => {
    expect(() => parseDocumentArtifactContent({
      kind: 'document', schemaVersion: 1, language: 'en', pageMode: 'document', blocks,
    })).toThrow('Document block IDs must be unique.');
  });

  it('serializes governed native blocks to deterministic Markdown and HTML', () => {
    const content = parseDocumentArtifactContent({
      kind: 'document',
      schemaVersion: 1,
      language: 'en',
      pageMode: 'document',
      blocks: [
        {
          id: 'heading-1',
          type: 'heading',
          props: { level: 2 },
          content: [{ type: 'text', text: 'Launch & safety', styles: { bold: true } }],
          children: [],
        },
        {
          id: 'bullet-1',
          type: 'bulletListItem',
          props: {},
          content: [{ type: 'text', text: 'Validate <policy>', styles: { italic: true } }],
          children: [
            {
              id: 'check-1',
              type: 'checkListItem',
              props: { checked: true },
              content: [{ type: 'text', text: 'Approved', styles: {} }],
              children: [],
            },
          ],
        },
      ],
    });

    expect(serializeDocumentToMarkdown(content)).toBe(
      '## **Launch & safety**\n\n- *Validate \\<policy\\>*\n  - [x] Approved\n',
    );
    expect(serializeDocumentToHtml(content)).toBe(
      '<!doctype html>\n<html lang="en">\n<head><meta charset="utf-8"><title>Document artifact</title></head>\n<body>\n<h2><strong>Launch &amp; safety</strong></h2>\n<ul><li><em>Validate &lt;policy&gt;</em>\n<ul class="check-list"><li data-checked="true">Approved</li></ul></li></ul>\n</body>\n</html>\n',
    );
  });

  it('keeps literal Markdown syntax inert and uses a collision-safe code fence', () => {
    const content = parseDocumentArtifactContent({
      kind: 'document',
      schemaVersion: 1,
      language: 'en',
      pageMode: 'document',
      blocks: [
        {
          id: 'paragraph-1',
          type: 'paragraph',
          props: {},
          content: [{ type: 'text', text: '# title\n- item\n~~literal~~\n[remote](https://example.test)', styles: {} }],
          children: [],
        },
        {
          id: 'code-1',
          type: 'codeBlock',
          props: { language: 'ts\n# forged' },
          content: [{ type: 'text', text: 'const fence = ```;\\path', styles: { bold: true } }],
          children: [],
        },
      ],
    });

    expect(serializeDocumentToMarkdown(content)).toBe(
      '\\# title\n\\- item\n\\~\\~literal\\~\\~\n\\[remote\\]\\(https://example\\.test\\)\n\n~~~\nconst fence = ```;\\path\n~~~\n',
    );
  });

  it('allows URL text as inert content but rejects remote references in block metadata', () => {
    expect(() =>
      parseDocumentArtifactContent({
        kind: 'document', schemaVersion: 1, language: 'en', pageMode: 'document',
        blocks: [{
          id: 'paragraph-1', type: 'paragraph', props: {},
          content: [{ type: 'text', text: 'https://example.test is plain text', styles: {} }], children: [],
        }],
      }),
    ).not.toThrow();
    expect(() =>
      parseDocumentArtifactContent({
        kind: 'document', schemaVersion: 1, language: 'en', pageMode: 'document',
        blocks: [{
          id: 'paragraph-1', type: 'paragraph',
          props: { backgroundImage: 'url(https://example.test/a.png)' }, content: [], children: [],
        }],
      }),
    ).toThrow('Remote document content is forbidden.');
  });
});
