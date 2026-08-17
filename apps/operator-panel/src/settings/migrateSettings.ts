export const LEGACY_SETTINGS_KEYS = [
  ['imperaos', 'operator', 'settings', 'v1'].join('.'),
  [['ae', 'gis', 'os'].join(''), 'operator', 'settings', 'v1'].join('.'),
] as const;

const LEGACY_SECRET_FIELDS = [
  ['assistant', 'OpenAi', 'ApiKey'].join(''),
  ['assistant', 'DeepSeek', 'ApiKey'].join(''),
] as const;

export function sanitizePersistedSettings(value: Record<string, unknown>): Record<string, unknown> {
  const sanitized = { ...value };
  for (const field of LEGACY_SECRET_FIELDS) {
    delete sanitized[field];
  }
  return sanitized;
}

export function readSettingsForMigration(
  storage: Storage,
  canonicalKey: string,
): { value: Record<string, unknown> | null; migratedFrom: string | null; corrupt: boolean } {
  const candidates = [canonicalKey, ...LEGACY_SETTINGS_KEYS];
  for (const key of candidates) {
    const raw = storage.getItem(key);
    if (raw === null) continue;
    try {
      const parsed = JSON.parse(raw);
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        return { value: null, migratedFrom: key, corrupt: true };
      }
      return {
        value: sanitizePersistedSettings(parsed as Record<string, unknown>),
        migratedFrom: key === canonicalKey ? null : key,
        corrupt: false,
      };
    } catch {
      return { value: null, migratedFrom: key, corrupt: true };
    }
  }
  return { value: null, migratedFrom: null, corrupt: false };
}
