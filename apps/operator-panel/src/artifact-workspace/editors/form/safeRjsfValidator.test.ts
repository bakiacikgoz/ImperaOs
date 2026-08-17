import { describe, expect, it, vi } from 'vitest';
import type { RJSFSchema } from '@rjsf/utils';
import responseFixtureRaw from '../../../../../../contracts/artifacts/fixtures/form-response-parity.v1.json?raw';

import { safeRjsfValidator } from './safeRjsfValidator';

const responseFixture = JSON.parse(responseFixtureRaw) as {
  cases: Array<{ name: string; allowed: boolean; schema: unknown; response: unknown }>;
};

const schema = {
  type: 'object',
  properties: {
    name: { type: 'string', minLength: 2 },
    count: { type: 'integer', minimum: 1, maximum: 10 },
  },
  required: ['name'],
  additionalProperties: false,
} satisfies RJSFSchema;

describe('CSP-safe RJSF validator', () => {
  it('matches the authoritative backend response parity fixture', () => {
    for (const testCase of responseFixture.cases) {
      expect(
        safeRjsfValidator.isValid(
          testCase.schema as RJSFSchema,
          testCase.response as Record<string, unknown>,
          testCase.schema as RJSFSchema,
        ),
        testCase.name,
      ).toBe(testCase.allowed);
    }
  });

  it('validates the bounded subset without eval or Function', () => {
    const originalFunction = globalThis.Function;
    const evalSpy = vi.spyOn(globalThis, 'eval').mockImplementation(() => {
      throw new Error('eval forbidden');
    });
    globalThis.Function = vi.fn(() => { throw new Error('Function forbidden'); }) as unknown as FunctionConstructor;
    try {
      expect(safeRjsfValidator.isValid(schema, { name: 'Ada', count: 2 }, schema)).toBe(true);
      expect(safeRjsfValidator.isValid(schema, { count: 999 }, schema)).toBe(false);
    } finally {
      globalThis.Function = originalFunction;
      evalSpy.mockRestore();
    }
  });

  it('returns bounded field errors without echoing sensitive values', () => {
    const secret = 'private-form-validator-canary';
    const result = safeRjsfValidator.validateFormData(
      { name: secret, count: 999 },
      { ...schema, properties: { ...schema.properties, name: { type: 'string', maxLength: 3 } } },
    );

    expect(result.errors.length).toBeGreaterThan(0);
    expect(JSON.stringify(result)).not.toContain(secret);
    expect(result.errors.every((error) => error.stack.length <= 512)).toBe(true);
  });

  it('rejects responses above the 512 KiB byte ceiling', () => {
    expect(safeRjsfValidator.isValid({ type: 'object' }, { value: 'a'.repeat(512 * 1024) }, { type: 'object' })).toBe(false);
  });

  it('never mutates Object.prototype while building adversarial error paths', () => {
    const adversarial = JSON.parse('{"__proto__":{"selected source text":"secret"}}') as Record<string, unknown>;
    const strictSchema = { type: 'object', additionalProperties: false } satisfies RJSFSchema;

    try {
      const result = safeRjsfValidator.validateFormData(adversarial, strictSchema);

      expect(result.errors.length).toBeGreaterThan(0);
      expect(Object.prototype).not.toHaveProperty('__errors');
      expect(JSON.stringify(result)).not.toContain('selected source text');
    } finally {
      delete (Object.prototype as Record<string, unknown>).__errors;
    }
  });
});
