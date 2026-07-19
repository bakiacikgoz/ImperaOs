import {
  BlockNoteSchema,
  defaultBlockSpecs,
  defaultInlineContentSpecs,
  defaultStyleSpecs,
  type PartialBlock,
} from '@blocknote/core';
import { BlockNoteDefaultUI, BlockNoteViewRaw, useCreateBlockNote } from '@blocknote/react';
import { useMemo } from 'react';

import '@blocknote/core/style.css';
import '@blocknote/react/style.css';

import type { ArtifactEditorProps } from '../ArtifactEditorHost';
import {
  parseDocumentArtifactContent,
  selectionFromBlockIds,
  serializeDocumentBlocks,
} from './documentAdapter';

const documentSchema = BlockNoteSchema.create({
  blockSpecs: {
    paragraph: defaultBlockSpecs.paragraph,
    heading: defaultBlockSpecs.heading,
    bulletListItem: defaultBlockSpecs.bulletListItem,
    numberedListItem: defaultBlockSpecs.numberedListItem,
    checkListItem: defaultBlockSpecs.checkListItem,
    quote: defaultBlockSpecs.quote,
    codeBlock: defaultBlockSpecs.codeBlock,
    divider: defaultBlockSpecs.divider,
  },
  inlineContentSpecs: {
    text: defaultInlineContentSpecs.text,
    link: defaultInlineContentSpecs.link,
  },
  styleSpecs: defaultStyleSpecs,
});

export function DocumentArtifactEditor({
  artifact,
  revision,
  content,
  mode,
  saveState,
  onChange,
  onSelectionChange,
}: ArtifactEditorProps) {
  const document = useMemo(() => parseDocumentArtifactContent(content), [content]);
  const editor = useCreateBlockNote(
    {
      schema: documentSchema,
      initialContent: document.blocks as PartialBlock<typeof documentSchema.blockSchema>[],
      links: {
        isValidLink: () => false,
        onClick: () => true,
      },
    },
    [artifact.artifactId, revision.revisionId],
  );
  const editable = mode !== 'view' && artifact.status !== 'archived';

  const emitSelection = () => {
    const selected = editor.getSelection()?.blocks ?? [editor.getTextCursorPosition().block];
    onSelectionChange(selectionFromBlockIds(selected.map((block) => block.id)));
  };

  const updateCurrentBlock = (type: 'paragraph' | 'heading' | 'bulletListItem' | 'quote') => {
    const block = editor.getTextCursorPosition().block;
    if (type === 'heading') {
      editor.updateBlock(block, { type, props: { level: 1 } });
    } else {
      editor.updateBlock(block, { type });
    }
    editor.focus();
  };

  return (
    <section className="document-artifact-editor" aria-label={`Document editor: ${artifact.title}`}>
      <div className="document-artifact-toolbar" role="toolbar" aria-label="Document formatting">
        <button type="button" disabled={!editable} onClick={() => updateCurrentBlock('paragraph')}>Text</button>
        <button type="button" disabled={!editable} onClick={() => updateCurrentBlock('heading')}>Heading 1</button>
        <button type="button" disabled={!editable} onClick={() => updateCurrentBlock('bulletListItem')}>Bullet list</button>
        <button type="button" disabled={!editable} onClick={() => updateCurrentBlock('quote')}>Quote</button>
        <button type="button" disabled={!editable} onClick={() => editor.undo()}>Undo</button>
        <button type="button" disabled={!editable} onClick={() => editor.redo()}>Redo</button>
        <span role="status" aria-live="polite">{saveState}</span>
      </div>
      {!editable ? <p className="artifact-workspace-banner">This revision is read-only.</p> : null}
      <BlockNoteViewRaw
        editor={editor}
        editable={editable}
        className="document-artifact-blocknote"
        onSelectionChange={emitSelection}
        onChange={(currentEditor) => {
          onChange(serializeDocumentBlocks(document, currentEditor.document));
        }}
      >
        <BlockNoteDefaultUI
          formattingToolbar={false}
          linkToolbar={false}
          slashMenu={false}
          sideMenu={editable}
          filePanel={false}
          tableHandles={false}
          emojiPicker={false}
          comments={false}
        />
      </BlockNoteViewRaw>
    </section>
  );
}
