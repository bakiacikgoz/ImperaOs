type JsonRecord = Record<string, unknown>;

const ALLOWED_SCHEMA_KEYS = new Set([
  '$schema', '$ref', 'definitions', 'title', 'description', 'type',
  'properties', 'required', 'enum', 'const', 'oneOf', 'items',
  'additionalProperties', 'minLength', 'maxLength', 'minimum', 'maximum',
  'exclusiveMinimum', 'exclusiveMaximum', 'multipleOf', 'minItems', 'maxItems',
  'uniqueItems', 'pattern', 'format', 'default', 'examples',
]);
const ALLOWED_TYPES = new Set(['object', 'array', 'string', 'number', 'integer', 'boolean', 'null']);
const ALLOWED_FORMATS = new Set(['date', 'date-time', 'email', 'hostname', 'ipv4', 'ipv6', 'uri-reference', 'uuid']);
const ALLOWED_UI_KEYS = new Set(['ui:widget', 'ui:options', 'ui:placeholder', 'ui:help', 'ui:title', 'ui:description']);
const ALLOWED_WIDGETS = new Set(['text', 'textarea', 'select', 'checkbox', 'radio', 'date', 'hidden']);
const FORBIDDEN_KEYS = new Set(['__proto__', 'prototype', 'constructor']);
const FORBIDDEN_UI_KEYS = new Set(['src', 'url', 'href', 'html', 'dangerouslysetinnerhtml', 'script']);
const FIELD_KEY = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const DRAFT7_SCHEMA_URI = 'http://json-schema.org/draft-07/schema#';
const MAX_FIELDS = 100;
const MAX_DEPTH = 6;
const MAX_BYTES = 512 * 1024;

export class SafeFormSchemaError extends Error {
  readonly code = 'FORM_SCHEMA_UNSAFE';

  constructor(message: string) {
    super(message);
    this.name = 'SafeFormSchemaError';
  }
}

export interface SafeFormContent {
  kind: 'form';
  schemaVersion: 1;
  schema: JsonRecord;
  uiSchema?: JsonRecord;
  behavior?: { submitMode?: 'explicit'; externalContinuation?: 'deny' | 'approval_required' };
  sensitivePaths?: string[];
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function fail(message: string): never {
  throw new SafeFormSchemaError(message);
}

function hasOwn(value: JsonRecord, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function isSafePattern(pattern: string): boolean {
  let operators = '';
  for (let index = 0; index < pattern.length; index += 1) {
    if (pattern[index] === '\\') {
      index += 1;
      continue;
    }
    if (pattern[index] === '[') {
      index += 1;
      while (index < pattern.length && pattern[index] !== ']') {
        if (pattern[index] === '\\') index += 1;
        index += 1;
      }
      continue;
    }
    operators += pattern[index];
  }
  return !/[()|*+]/.test(operators) && !/\{\d+,\}/.test(operators);
}

function ensureSafeRecord(value: JsonRecord): void {
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    fail('form schema contains an unsafe object prototype');
  }
}

function validateFieldKey(value: string): void {
  if (!FIELD_KEY.test(value) || FORBIDDEN_KEYS.has(value)) {
    fail('form schema contains an unsafe field key');
  }
}

function containsRemoteUrl(value: unknown): boolean {
  if (typeof value === 'string') return /^(?:https?:)?\/\//i.test(value.trim());
  if (Array.isArray(value)) return value.some(containsRemoteUrl);
  return isRecord(value) && Object.values(value).some(containsRemoteUrl);
}

function validateUiSchema(value: unknown): void {
  if (typeof value === 'string') {
    if (containsRemoteUrl(value)) fail('uiSchema contains a remote URL');
    return;
  }
  if (Array.isArray(value)) {
    value.forEach(validateUiSchema);
    return;
  }
  if (!isRecord(value)) return;
  ensureSafeRecord(value);
  for (const [key, item] of Object.entries(value)) {
    const lowered = key.toLowerCase();
    if (key.startsWith('ui:') && !ALLOWED_UI_KEYS.has(key)) fail('uiSchema contains an unsupported directive');
    if (FORBIDDEN_UI_KEYS.has(lowered) || lowered.startsWith('on')) fail('uiSchema contains a forbidden key');
    if (key === 'ui:widget' && (typeof item !== 'string' || !ALLOWED_WIDGETS.has(item))) {
      fail('uiSchema contains an unsupported widget');
    }
    validateUiSchema(item);
  }
}

function validateSchema(schema: JsonRecord): void {
  if (schema.type !== 'object') fail('form schema root must be an object');
  let fieldCount = 0;
  const localRefs: Array<[string, string]> = [];

  const visit = (node: unknown, depth: number): void => {
    if (depth > MAX_DEPTH) fail(`form schema depth exceeds ${MAX_DEPTH}`);
    if (!isRecord(node)) return;
    ensureSafeRecord(node);
    const unknown = Object.keys(node).filter((key) => !ALLOWED_SCHEMA_KEYS.has(key));
    if (unknown.length > 0) fail('form schema contains unsupported keys');
    if (typeof node.$ref === 'string') {
      const match = /^#\/definitions\/([^/]+)$/.exec(node.$ref);
      if (!match) fail('remote refs are forbidden');
      validateFieldKey(match[1]);
      localRefs.push(['definitions', match[1]]);
    }
    if (hasOwn(node, 'type') && (typeof node.type !== 'string' || !ALLOWED_TYPES.has(node.type))) fail('unsupported form type');
    if (hasOwn(node, 'format') && (typeof node.format !== 'string' || !ALLOWED_FORMATS.has(node.format))) fail('unsupported form format');
    if (hasOwn(node, 'pattern')) {
      if (typeof node.pattern !== 'string') fail('invalid pattern in form schema');
      if (node.pattern.length > 256 || !isSafePattern(node.pattern)) fail('unsafe pattern in form schema');
      try { new RegExp(node.pattern); } catch { fail('invalid pattern in form schema'); }
    }
    if (hasOwn(node, 'required') && (!Array.isArray(node.required) || node.required.some((item) => typeof item !== 'string'))) {
      fail('form required must be a string array');
    }
    if (hasOwn(node, 'enum') && !Array.isArray(node.enum)) fail('form enum must be an array');
    if (hasOwn(node, 'oneOf') && (!Array.isArray(node.oneOf) || node.oneOf.some((item) => !isRecord(item)))) {
      fail('form oneOf must contain schemas');
    }
    if (Array.isArray(node.oneOf)) {
      if (node.oneOf.length > 20) fail('form oneOf exceeds 20 branches');
      node.oneOf.forEach((item) => visit(item, depth + 1));
    }
    if (isRecord(node.properties)) {
      ensureSafeRecord(node.properties);
      Object.keys(node.properties).forEach(validateFieldKey);
      fieldCount += Object.keys(node.properties).length;
      if (fieldCount > MAX_FIELDS) fail(`form schema exceeds ${MAX_FIELDS} fields`);
      Object.values(node.properties).forEach((item) => visit(item, depth + 1));
    }
    const definitions = node.definitions;
    if (isRecord(definitions)) {
      ensureSafeRecord(definitions);
      Object.keys(definitions).forEach(validateFieldKey);
      Object.values(definitions).forEach((item) => visit(item, depth + 1));
    }
    if (isRecord(node.items)) visit(node.items, depth + 1);
    if (isRecord(node.additionalProperties)) fail('schema-valued additionalProperties is not allowed');
  };

  const serialized = JSON.stringify(schema);
  if (new TextEncoder().encode(serialized).byteLength > MAX_BYTES) fail(`form schema exceeds ${MAX_BYTES} bytes`);
  if (hasOwn(schema, '$schema') && schema.$schema !== DRAFT7_SCHEMA_URI) fail('unsupported form schema dialect');
  visit(schema, 1);
  for (const [definitionsKey, definitionName] of localRefs) {
    const definitions = schema[definitionsKey];
    if (!isRecord(definitions) || !hasOwn(definitions, definitionName)) fail('form schema contains an unresolved local ref');
  }
  rejectCyclicRefs(schema);
}

function rejectCyclicRefs(schema: JsonRecord): void {
  const definitions = schema.definitions;
  if (!isRecord(definitions)) return;
  const refs = (value: unknown): string[] => {
    if (Array.isArray(value)) return value.flatMap(refs);
    if (!isRecord(value)) return [];
    const own = typeof value.$ref === 'string' && value.$ref.startsWith('#/definitions/')
      ? [value.$ref.slice('#/definitions/'.length)]
      : [];
    return [...own, ...Object.values(value).flatMap(refs)];
  };
  const graph = new Map(Object.entries(definitions).map(([key, value]) => [key, refs(value)]));
  const visiting = new Set<string>();
  const visited = new Set<string>();
  const visit = (key: string): void => {
    if (visiting.has(key)) fail('form schema contains cyclic local refs');
    if (visited.has(key)) return;
    visiting.add(key);
    graph.get(key)?.forEach(visit);
    visiting.delete(key);
    visited.add(key);
  };
  graph.forEach((_value, key) => visit(key));
}

export function validateSafeFormContent(value: unknown): SafeFormContent {
  if (!isRecord(value) || value.kind !== 'form' || value.schemaVersion !== 1 || !isRecord(value.schema)) {
    fail('form content does not match schema version 1');
  }
  ensureSafeRecord(value);
  ensureSafeRecord(value.schema);
  const allowedContentKeys = new Set(['kind', 'schemaVersion', 'schema', 'uiSchema', 'behavior', 'sensitivePaths']);
  if (Object.keys(value).some((key) => !allowedContentKeys.has(key))) fail('form content contains unsupported keys');
  validateSchema(value.schema);
  if (value.uiSchema !== undefined) {
    if (!isRecord(value.uiSchema)) fail('uiSchema must be an object');
    validateUiSchema(value.uiSchema);
  }
  if (value.behavior !== undefined) {
    if (!isRecord(value.behavior)
      || Object.keys(value.behavior).some((key) => !['submitMode', 'externalContinuation'].includes(key))
      || (value.behavior.submitMode !== undefined && value.behavior.submitMode !== 'explicit')
      || (value.behavior.externalContinuation !== undefined
        && !['deny', 'approval_required'].includes(String(value.behavior.externalContinuation)))) {
      fail('form behavior is invalid');
    }
  }
  if (value.sensitivePaths !== undefined) {
    if (!Array.isArray(value.sensitivePaths) || value.sensitivePaths.length > 100
      || value.sensitivePaths.some((path) => typeof path !== 'string' || !/^\/(?:[^/~]|~[01])+(?:\/(?:[^/~]|~[01])+)*$/.test(path))) {
      fail('sensitive paths are invalid');
    }
  }
  return value as unknown as SafeFormContent;
}

function encodeIdPart(value: string): string {
  return Array.from(value, (character) => (
    /[A-Za-z0-9]/.test(character) ? character : `_${character.codePointAt(0)?.toString(16)}_`
  )).join('');
}

export function deriveFormFieldId(artifactId: string, path: string[]): string {
  if (!FIELD_KEY.test(artifactId) || path.length > MAX_DEPTH || path.some((part) => !FIELD_KEY.test(part) || FORBIDDEN_KEYS.has(part))) {
    fail('form field identity is unsafe');
  }
  return ['form', `${artifactId.length}_${encodeIdPart(artifactId)}`, ...path.map((part) => `${part.length}_${encodeIdPart(part)}`)].join('__');
}
