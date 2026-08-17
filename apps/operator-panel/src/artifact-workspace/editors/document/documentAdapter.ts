import type { ArtifactContent } from '../../artifactContracts';

const ALLOWED_BLOCK_TYPES = new Set([
  'paragraph',
  'heading',
  'bulletListItem',
  'numberedListItem',
  'checkListItem',
  'quote',
  'codeBlock',
  'divider',
]);
const BOUNDED_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const LANGUAGE = /^[a-z]{2,3}(?:-[A-Z]{2})?$/;
const MAX_BLOCKS = 10_000;
const MAX_DEPTH = 20;
const MAX_BYTES = 5 * 1024 * 1024;

export type DocumentTextNode = {
  type: 'text';
  text: string;
  styles: Record<string, boolean | string>;
};

export type DocumentBlock = {
  id: string;
  type: string;
  props: Record<string, boolean | number | string>;
  content: DocumentTextNode[];
  children: DocumentBlock[];
};

export type DocumentArtifactContent = ArtifactContent & {
  kind: 'document';
  schemaVersion: 1;
  language: string;
  pageMode: 'document' | 'paginated';
  blocks: DocumentBlock[];
};

export type DocumentArtifactSelection = {
  kind: 'document';
  blockIds: string[];
};

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object.`);
  }
  return value as Record<string, unknown>;
}

function assertKeys(value: Record<string, unknown>, allowed: string[], label: string): void {
  const unknown = Object.keys(value).filter((key) => !allowed.includes(key));
  if (unknown.length > 0) throw new Error(`${label} contains unsupported fields.`);
}

function containsRemoteReference(value: string): boolean {
  return /(?:https?:)?\/\/|url\s*\(/i.test(value);
}

function parseStyles(value: unknown): Record<string, boolean | string> {
  if (value === undefined) return {};
  const source = record(value, 'Text styles');
  const result: Record<string, boolean | string> = {};
  for (const [key, item] of Object.entries(source)) {
    if (typeof item !== 'boolean' && typeof item !== 'string') throw new Error('Text style value is invalid.');
    if (typeof item === 'string' && containsRemoteReference(item)) {
      throw new Error('Remote document content is forbidden.');
    }
    result[key] = item;
  }
  return result;
}

function parseTextNode(value: unknown): DocumentTextNode {
  const source = record(value, 'Inline content');
  assertKeys(source, ['type', 'text', 'styles'], 'Inline content');
  if (source.type !== 'text' || typeof source.text !== 'string') {
    throw new Error('Only native text inline content is allowed.');
  }
  return { type: 'text', text: source.text, styles: parseStyles(source.styles) };
}

function parseProps(value: unknown): Record<string, boolean | number | string> {
  if (value === undefined) return {};
  const source = record(value, 'Block props');
  const result: Record<string, boolean | number | string> = {};
  for (const [key, item] of Object.entries(source)) {
    if (item === undefined) continue;
    if (!['boolean', 'number', 'string'].includes(typeof item)) throw new Error('Block prop is invalid.');
    if (typeof item === 'string' && containsRemoteReference(item)) {
      throw new Error('Remote document content is forbidden.');
    }
    result[key] = item as boolean | number | string;
  }
  return result;
}

function parseBlock(
  value: unknown,
  depth: number,
  count: { value: number },
  blockIds: Set<string>,
): DocumentBlock {
  if (depth > MAX_DEPTH) throw new Error('Document block depth exceeded.');
  count.value += 1;
  if (count.value > MAX_BLOCKS) throw new Error('Document block count exceeded.');
  const source = record(value, 'Document block');
  assertKeys(source, ['id', 'type', 'props', 'content', 'children'], 'Document block');
  if (typeof source.id !== 'string' || !BOUNDED_ID.test(source.id)) {
    throw new Error('Document block requires a stable bounded ID.');
  }
  if (blockIds.has(source.id)) throw new Error('Document block IDs must be unique.');
  blockIds.add(source.id);
  if (typeof source.type !== 'string' || !ALLOWED_BLOCK_TYPES.has(source.type)) {
    throw new Error('Document block type is not allowed.');
  }
  const rawContent = source.content ?? [];
  if (!Array.isArray(rawContent)) throw new Error('Document block content must be an array.');
  const rawChildren = source.children ?? [];
  if (!Array.isArray(rawChildren)) throw new Error('Document block children must be an array.');
  return {
    id: source.id,
    type: source.type,
    props: parseProps(source.props),
    content: rawContent.map(parseTextNode),
    children: rawChildren.map((child) => parseBlock(child, depth + 1, count, blockIds)),
  };
}

export function parseDocumentArtifactContent(value: unknown): DocumentArtifactContent {
  const serialized = JSON.stringify(value);
  if (new TextEncoder().encode(serialized).byteLength > MAX_BYTES) throw new Error('Document content is too large.');
  const source = record(value, 'Document content');
  assertKeys(source, ['kind', 'schemaVersion', 'language', 'pageMode', 'blocks'], 'Document content');
  if (source.kind !== 'document' || source.schemaVersion !== 1) throw new Error('Document contract version is invalid.');
  if (typeof source.language !== 'string' || !LANGUAGE.test(source.language)) throw new Error('Document language is invalid.');
  if (source.pageMode !== 'document' && source.pageMode !== 'paginated') throw new Error('Document page mode is invalid.');
  if (!Array.isArray(source.blocks)) throw new Error('Document blocks must be an array.');
  const count = { value: 0 };
  const blockIds = new Set<string>();
  return {
    kind: 'document',
    schemaVersion: 1,
    language: source.language,
    pageMode: source.pageMode,
    blocks: source.blocks.map((block) => parseBlock(block, 1, count, blockIds)),
  };
}

export function serializeDocumentBlocks(
  base: DocumentArtifactContent,
  blocks: unknown,
): DocumentArtifactContent {
  return parseDocumentArtifactContent({ ...base, blocks });
}

export function selectionFromBlockIds(blockIds: string[]): DocumentArtifactSelection | null {
  const unique = Array.from(new Set(blockIds.filter((id) => BOUNDED_ID.test(id)))).slice(0, 100);
  if (unique.length === 0) return null;
  return {
    kind: 'document',
    blockIds: unique,
  };
}

function markdownCodeSpan(text: string): string {
  const runs = text.match(/`+/g) ?? [];
  const fence = '`'.repeat(Math.max(1, ...runs.map((run) => run.length + 1)));
  const normalized = text.replace(/\r?\n/g, ' ');
  const padded = /^\s|\s$|^`|`$/.test(normalized) ? ` ${normalized} ` : normalized;
  return `${fence}${padded}${fence}`;
}

function markdownText(node: DocumentTextNode): string {
  let value = node.styles.code
    ? markdownCodeSpan(node.text)
    : node.text.replace(/([\\`*_{}[\]()<>#+\-.!|~])/g, '\\$1');
  if (node.styles.bold) value = `**${value}**`;
  if (node.styles.italic) value = `*${value}*`;
  if (node.styles.strike) value = `~~${value}~~`;
  return value;
}

function markdownLine(block: DocumentBlock): string {
  const text = block.content.map(markdownText).join('');
  switch (block.type) {
    case 'heading': {
      const level = Math.min(6, Math.max(1, Number(block.props.level) || 1));
      return `${'#'.repeat(level)} ${text}`;
    }
    case 'bulletListItem':
      return `- ${text}`;
    case 'numberedListItem':
      return `1. ${text}`;
    case 'checkListItem':
      return `- [${block.props.checked === true ? 'x' : ' '}] ${text}`;
    case 'quote':
      return `> ${text}`;
    case 'codeBlock': {
      const raw = block.content.map((node) => node.text).join('');
      const runs = raw.match(/~+/g) ?? [];
      const fence = '~'.repeat(Math.max(3, ...runs.map((run) => run.length + 1)));
      const language = typeof block.props.language === 'string' && /^[A-Za-z0-9_+-]{1,32}$/.test(block.props.language)
        ? block.props.language
        : '';
      return `${fence}${language}\n${raw}\n${fence}`;
    }
    case 'divider':
      return '---';
    default:
      return text;
  }
}

function markdownBlocks(blocks: DocumentBlock[], depth = 0): string[] {
  const lines: string[] = [];
  for (const block of blocks) {
    const isList = ['bulletListItem', 'numberedListItem', 'checkListItem'].includes(block.type);
    const prefix = '  '.repeat(depth);
    lines.push(`${prefix}${markdownLine(block)}`);
    if (block.children.length > 0) lines.push(...markdownBlocks(block.children, isList ? depth + 1 : depth));
    if (!isList && depth === 0) lines.push('');
  }
  return lines;
}

export function serializeDocumentToMarkdown(content: DocumentArtifactContent): string {
  const parsed = parseDocumentArtifactContent(content);
  const lines = markdownBlocks(parsed.blocks);
  while (lines.at(-1) === '') lines.pop();
  const grouped: string[] = [];
  for (const line of lines) {
    if (line === '' && grouped.at(-1) === '') continue;
    const previous = grouped.at(-1) ?? '';
    const currentList = /^\s*(?:-|1\.) /.test(line);
    const previousList = /^\s*(?:-|1\.) /.test(previous);
    if (grouped.length > 0 && line !== '' && !currentList && previousList) grouped.push('');
    grouped.push(line);
    if (line !== '' && !currentList) grouped.push('');
  }
  while (grouped.at(-1) === '') grouped.pop();
  return `${grouped.join('\n')}\n`;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function htmlText(node: DocumentTextNode): string {
  let value = escapeHtml(node.text);
  if (node.styles.code) value = `<code>${value}</code>`;
  if (node.styles.bold) value = `<strong>${value}</strong>`;
  if (node.styles.italic) value = `<em>${value}</em>`;
  if (node.styles.strike) value = `<s>${value}</s>`;
  return value;
}

function htmlBlocks(blocks: DocumentBlock[]): string {
  const output: string[] = [];
  for (let index = 0; index < blocks.length;) {
    const block = blocks[index];
    const listTag = block.type === 'numberedListItem' ? 'ol' :
      block.type === 'bulletListItem' || block.type === 'checkListItem' ? 'ul' : null;
    if (listTag) {
      const checkList = block.type === 'checkListItem';
      const items: string[] = [];
      while (index < blocks.length) {
        const item = blocks[index];
        const sameList = checkList
          ? item.type === 'checkListItem'
          : listTag === 'ol'
            ? item.type === 'numberedListItem'
            : item.type === 'bulletListItem';
        if (!sameList) break;
        const checked = checkList ? ` data-checked="${item.props.checked === true ? 'true' : 'false'}"` : '';
        items.push(`<li${checked}>${item.content.map(htmlText).join('')}${
          item.children.length > 0 ? `\n${htmlBlocks(item.children)}` : ''
        }</li>`);
        index += 1;
      }
      output.push(`<${listTag}${checkList ? ' class="check-list"' : ''}>${items.join('\n')}</${listTag}>`);
      continue;
    }

    const text = block.content.map(htmlText).join('');
    const children = block.children.length > 0 ? `\n${htmlBlocks(block.children)}` : '';
    switch (block.type) {
      case 'heading': {
        const level = Math.min(6, Math.max(1, Number(block.props.level) || 1));
        output.push(`<h${level}>${text}</h${level}>${children}`);
        break;
      }
      case 'quote': output.push(`<blockquote>${text}${children}</blockquote>`); break;
      case 'codeBlock': output.push(`<pre><code>${text}</code></pre>${children}`); break;
      case 'divider': output.push(`<hr>${children}`); break;
      default: output.push(`<p>${text}</p>${children}`); break;
    }
    index += 1;
  }
  return output.join('\n');
}

export function serializeDocumentToHtml(content: DocumentArtifactContent): string {
  const parsed = parseDocumentArtifactContent(content);
  return `<!doctype html>\n<html lang="${escapeHtml(parsed.language)}">\n<head><meta charset="utf-8"><title>Document artifact</title></head>\n<body>\n${htmlBlocks(parsed.blocks)}\n</body>\n</html>\n`;
}
