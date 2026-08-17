import { describe, expect, it } from 'vitest';

import fixture from '../../../../../../contracts/artifacts/fixtures/form-schema-parity.v1.json';
import {
  SafeFormSchemaError,
  deriveFormFieldId,
  validateSafeFormContent,
} from './formAdapter';

function nestedSchema(levels: number): Record<string, unknown> {
  let node: Record<string, unknown> = { type: 'string' };
  for (let index = levels - 1; index >= 0; index -= 1) {
    node = { type: 'object', properties: { [`level_${index}`]: node } };
  }
  return node;
}

describe('safe form adapter', () => {
  it('matches the authoritative backend parity fixture', () => {
    for (const testCase of fixture.cases) {
      if (testCase.allowed) {
        expect(() => validateSafeFormContent(testCase.content)).not.toThrow();
      } else {
        let caught: unknown;
        try {
          validateSafeFormContent(testCase.content);
        } catch (error) {
          caught = error;
        }
        expect(caught, testCase.name).toBeInstanceOf(SafeFormSchemaError);
      }
    }
  });

  it('enforces field and depth limits without runtime code generation', () => {
    const fields = Object.fromEntries(
      Array.from({ length: 100 }, (_, index) => [`field_${index}`, { type: 'string' }]),
    );
    expect(() => validateSafeFormContent({
      kind: 'form', schemaVersion: 1, schema: { type: 'object', properties: fields },
    })).not.toThrow();
    expect(() => validateSafeFormContent({
      kind: 'form', schemaVersion: 1,
      schema: { type: 'object', properties: { ...fields, overflow: { type: 'string' } } },
    })).toThrow('100 fields');
    expect(() => validateSafeFormContent({ kind: 'form', schemaVersion: 1, schema: nestedSchema(5) })).not.toThrow();
    expect(() => validateSafeFormContent({ kind: 'form', schemaVersion: 1, schema: nestedSchema(6) })).toThrow('depth exceeds 6');
    expect(validateSafeFormContent.toString()).not.toMatch(/\beval\b|new Function|Ajv/);
  });

  it('derives stable artifact-scoped field ids and rejects unsafe paths', () => {
    expect(deriveFormFieldId('artifact-1', ['contact', 'email']))
      .toBe(deriveFormFieldId('artifact-1', ['contact', 'email']));
    expect(deriveFormFieldId('artifact-1', ['contact.email']))
      .not.toBe(deriveFormFieldId('artifact-1', ['contact', 'email']));
    expect(deriveFormFieldId('artifact-1', ['contact', 'email']))
      .not.toBe(deriveFormFieldId('artifact-2', ['contact', 'email']));
    expect(() => deriveFormFieldId('artifact-1', ['__proto__'])).toThrow(SafeFormSchemaError);
  });
});
