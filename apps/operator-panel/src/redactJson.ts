const SENSITIVE_KEY_PATTERN =
  /(secret|token|password|credential|authorization|cookie|api[_-]?key|private[_-]?key|(?:^|[_-])path$)/i;

export function redactJson(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => redactJson(item));
  }
  if (typeof value === 'object' && value !== null) {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, entry]) => [
        key,
        SENSITIVE_KEY_PATTERN.test(key) ? '[redacted]' : redactJson(entry),
      ]),
    );
  }
  return value;
}
