import type {
  ErrorSchema,
  RJSFSchema,
  RJSFValidationError,
  ValidatorType,
} from '@rjsf/utils';

type JsonRecord = Record<string, unknown>;

interface ValidationIssue {
  name: string;
  message: string;
  path: string[];
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function sameJson(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left) && Array.isArray(right)
      && left.length === right.length
      && left.every((item, index) => sameJson(item, right[index]));
  }
  if (!isRecord(left) || !isRecord(right)) return false;
  const leftKeys = Object.keys(left).sort();
  const rightKeys = Object.keys(right).sort();
  return leftKeys.length === rightKeys.length
    && leftKeys.every((key, index) => key === rightKeys[index] && sameJson(left[key], right[key]));
}

function hasOwn(value: JsonRecord, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function resolveLocalRef(root: JsonRecord, ref: string): JsonRecord | undefined {
  if (!ref.startsWith('#/')) return undefined;
  let current: unknown = root;
  for (const encodedPart of ref.slice(2).split('/')) {
    const part = encodedPart.replaceAll('~1', '/').replaceAll('~0', '~');
    if (!isRecord(current) || !hasOwn(current, part)) return undefined;
    current = current[part];
  }
  return isRecord(current) ? current : undefined;
}

function valueMatchesType(value: unknown, type: string): boolean {
  if (type === 'null') return value === null;
  if (type === 'array') return Array.isArray(value);
  if (type === 'object') return isRecord(value);
  if (type === 'integer') return typeof value === 'number' && Number.isInteger(value);
  return typeof value === type;
}

function addIssue(issues: ValidationIssue[], path: string[], name: string, message: string): void {
  if (issues.length >= 100) return;
  issues.push({ name, message: message.slice(0, 256), path });
}

function validateNode(
  schemaValue: unknown,
  value: unknown,
  root: JsonRecord,
  path: string[],
  issues: ValidationIssue[],
  refStack: Set<string>,
): void {
  if (!isRecord(schemaValue)) return;
  if (typeof schemaValue.$ref === 'string') {
    if (refStack.has(schemaValue.$ref)) {
      addIssue(issues, path, '$ref', 'contains a cyclic local reference');
      return;
    }
    const resolved = resolveLocalRef(root, schemaValue.$ref);
    if (!resolved) {
      addIssue(issues, path, '$ref', 'contains an unresolved local reference');
      return;
    }
    const nextStack = new Set(refStack).add(schemaValue.$ref);
    validateNode(resolved, value, root, path, issues, nextStack);
    return;
  }

  if (schemaValue.const !== undefined && !sameJson(schemaValue.const, value)) {
    addIssue(issues, path, 'const', 'must equal the allowed constant');
  }
  if (Array.isArray(schemaValue.enum) && !schemaValue.enum.some((entry) => sameJson(entry, value))) {
    addIssue(issues, path, 'enum', 'must be one of the allowed values');
  }
  if (Array.isArray(schemaValue.oneOf)) {
    const matches = schemaValue.oneOf.filter((option) => {
      const branchIssues: ValidationIssue[] = [];
      validateNode(option, value, root, path, branchIssues, new Set(refStack));
      return branchIssues.length === 0;
    }).length;
    if (matches !== 1) addIssue(issues, path, 'oneOf', 'must match exactly one allowed shape');
  }

  if (typeof schemaValue.type === 'string' && !valueMatchesType(value, schemaValue.type)) {
    addIssue(issues, path, 'type', `must be ${schemaValue.type}`);
    return;
  }

  if (isRecord(value)) {
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      addIssue(issues, path, 'prototype', 'contains an unsafe object prototype');
      return;
    }
    const properties = isRecord(schemaValue.properties) ? schemaValue.properties : {};
    if (Array.isArray(schemaValue.required)) {
      for (const key of schemaValue.required) {
        if (typeof key === 'string' && !hasOwn(value, key)) {
          addIssue(issues, [...path, key], 'required', 'is required');
        }
      }
    }
    for (const [key, child] of Object.entries(value)) {
      if (hasOwn(properties, key)) {
        validateNode(properties[key], child, root, [...path, key], issues, refStack);
      } else if (schemaValue.additionalProperties === false) {
        addIssue(issues, [...path, key], 'additionalProperties', 'is not an allowed field');
      }
    }
  }

  if (Array.isArray(value)) {
    if (typeof schemaValue.minItems === 'number' && value.length < schemaValue.minItems) {
      addIssue(issues, path, 'minItems', `must contain at least ${schemaValue.minItems} items`);
    }
    if (typeof schemaValue.maxItems === 'number' && value.length > schemaValue.maxItems) {
      addIssue(issues, path, 'maxItems', `must contain at most ${schemaValue.maxItems} items`);
    }
    if (schemaValue.uniqueItems === true && value.some(
      (item, index) => value.slice(0, index).some((candidate) => sameJson(item, candidate)),
    )) {
      addIssue(issues, path, 'uniqueItems', 'must contain unique items');
    }
    if (schemaValue.items !== undefined) {
      value.forEach((item, index) => validateNode(schemaValue.items, item, root, [...path, String(index)], issues, refStack));
    }
  }

  if (typeof value === 'string') {
    const codePointLength = Array.from(value).length;
    if (typeof schemaValue.minLength === 'number' && codePointLength < schemaValue.minLength) {
      addIssue(issues, path, 'minLength', `must have a minimum length of ${schemaValue.minLength}`);
    }
    if (typeof schemaValue.maxLength === 'number' && codePointLength > schemaValue.maxLength) {
      addIssue(issues, path, 'maxLength', `must have a maximum length of ${schemaValue.maxLength}`);
    }
    if (typeof schemaValue.pattern === 'string' && !new RegExp(schemaValue.pattern, 'u').test(value)) {
      addIssue(issues, path, 'pattern', 'must match the required pattern');
    }
    if (schemaValue.format === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
      addIssue(issues, path, 'format', 'must be a valid email address');
    }
    if (schemaValue.format === 'uuid' && !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)) {
      addIssue(issues, path, 'format', 'must be a valid UUID');
    }
    if (schemaValue.format === 'date' && !validDate(value)) addIssue(issues, path, 'format', 'must be a valid date');
    if (schemaValue.format === 'date-time' && !validDateTime(value)) addIssue(issues, path, 'format', 'must be a valid date-time');
    if (schemaValue.format === 'hostname' && !validHostname(value)) addIssue(issues, path, 'format', 'must be a valid hostname');
    if (schemaValue.format === 'ipv4' && !validIpv4(value)) addIssue(issues, path, 'format', 'must be a valid IPv4 address');
    if (schemaValue.format === 'ipv6' && !validIpv6(value)) addIssue(issues, path, 'format', 'must be a valid IPv6 address');
    if (schemaValue.format === 'uri-reference' && !validUriReference(value)) addIssue(issues, path, 'format', 'must be a valid URI reference');
  }

  if (typeof value === 'number') {
    if (typeof schemaValue.minimum === 'number' && value < schemaValue.minimum) {
      addIssue(issues, path, 'minimum', `must be at least ${schemaValue.minimum}`);
    }
    if (typeof schemaValue.maximum === 'number' && value > schemaValue.maximum) {
      addIssue(issues, path, 'maximum', `must be at most ${schemaValue.maximum}`);
    }
    if (typeof schemaValue.exclusiveMinimum === 'number' && value <= schemaValue.exclusiveMinimum) {
      addIssue(issues, path, 'exclusiveMinimum', `must be greater than ${schemaValue.exclusiveMinimum}`);
    }
    if (typeof schemaValue.exclusiveMaximum === 'number' && value >= schemaValue.exclusiveMaximum) {
      addIssue(issues, path, 'exclusiveMaximum', `must be less than ${schemaValue.exclusiveMaximum}`);
    }
    if (typeof schemaValue.multipleOf === 'number' && schemaValue.multipleOf > 0) {
      const quotient = value / schemaValue.multipleOf;
      if (Math.abs(quotient - Math.round(quotient)) > 1e-9) {
        addIssue(issues, path, 'multipleOf', `must be a multiple of ${schemaValue.multipleOf}`);
      }
    }
  }
}

function propertyPath(path: string[]): string {
  return path.map((part) => /^[A-Za-z_$][\w$]*$/.test(part) ? `.${part}` : `[${JSON.stringify(part)}]`).join('');
}

function toErrors(issues: ValidationIssue[]): RJSFValidationError[] {
  return issues.map((issue) => {
    const property = propertyPath(issue.path);
    return {
      name: issue.name,
      message: issue.message,
      params: {},
      property,
      schemaPath: '#',
      stack: `${property || 'form'} ${issue.message}`.slice(0, 512),
    };
  });
}

function toErrorSchema(issues: ValidationIssue[]): ErrorSchema<Record<string, unknown>> {
  const root: Record<string, unknown> = Object.create(null) as Record<string, unknown>;
  for (const issue of issues) {
    let current = root;
    for (const part of issue.path) {
      const child = current[part];
      if (!hasOwn(current, part) || !isRecord(child)) {
        current[part] = Object.create(null) as Record<string, unknown>;
      }
      current = current[part] as Record<string, unknown>;
    }
    const messages = Array.isArray(current.__errors) ? current.__errors as string[] : [];
    current.__errors = [...messages, issue.message];
  }
  return root as ErrorSchema<Record<string, unknown>>;
}

function collect(schema: RJSFSchema, formData: Record<string, unknown> | undefined): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  try {
    const serialized = JSON.stringify(formData ?? {});
    if (new TextEncoder().encode(serialized).byteLength > 512 * 1024) {
      addIssue(issues, [], 'maxBytes', 'exceeds the maximum response size');
      return issues;
    }
  } catch {
    addIssue(issues, [], 'serialization', 'cannot be serialized safely');
    return issues;
  }
  validateNode(schema, formData ?? {}, schema as JsonRecord, [], issues, new Set());
  return issues;
}

function validDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime())
    && date.getUTCFullYear() === Number(match[1])
    && date.getUTCMonth() + 1 === Number(match[2])
    && date.getUTCDate() === Number(match[3]);
}

function validDateTime(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    && !Number.isNaN(Date.parse(value));
}

function validHostname(value: string): boolean {
  const normalized = value.endsWith('.') ? value.slice(0, -1) : value;
  return normalized.length > 0 && normalized.length <= 253 && normalized.split('.').every((label) => (
    label.length >= 1 && label.length <= 63 && /^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/.test(label)
  ));
}

function validIpv4(value: string): boolean {
  const parts = value.split('.');
  return parts.length === 4 && parts.every((part) => /^(?:0|[1-9]\d{0,2})$/.test(part) && Number(part) <= 255);
}

function validIpv6(value: string): boolean {
  if (!/^[0-9A-Fa-f:]+$/.test(value) || (value.match(/::/g)?.length ?? 0) > 1) return false;
  const sides = value.split('::');
  const left = sides[0] ? sides[0].split(':') : [];
  const right = sides[1] ? sides[1].split(':') : [];
  if (![...left, ...right].every((part) => /^[0-9A-Fa-f]{1,4}$/.test(part))) return false;
  return sides.length === 2 ? left.length + right.length < 8 : left.length === 8;
}

function validUriReference(value: string): boolean {
  if (!value || Array.from(value).some((character) => character === '\\' || character.codePointAt(0)! <= 0x20)) return false;
  try {
    new URL(value, 'https://local.invalid/');
    return true;
  } catch {
    return false;
  }
}

export const safeRjsfValidator: ValidatorType<Record<string, unknown>, RJSFSchema> = {
  validateFormData(formData, schema, _customValidate, transformErrors, uiSchema) {
    const issues = collect(schema, formData);
    const rawErrors = toErrors(issues);
    const errors = transformErrors ? transformErrors(rawErrors, uiSchema) : rawErrors;
    return { errors, errorSchema: toErrorSchema(issues) };
  },
  isValid(schema, formData) {
    return collect(schema, formData).length === 0;
  },
  rawValidation<Result = RJSFValidationError>(schema: RJSFSchema, formData?: Record<string, unknown>) {
    return { errors: toErrors(collect(schema, formData)) as unknown as Result[] };
  },
};
