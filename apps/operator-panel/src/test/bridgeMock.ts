import { vi, type Mock } from 'vitest';

import type { BridgeErrorCode, BridgeErrorPayload, BridgeResult } from '../bridge';

export type MockBridgeScenario =
  | 'happy_path'
  | 'preview_mode'
  | 'cli_not_found'
  | 'timeout'
  | 'schema_failed'
  | 'parse_failed'
  | 'path_violation'
  | 'contract_mismatch'
  | 'approval_empty'
  | 'approval_pending'
  | 'approval_stale'
  | 'run_empty'
  | 'run_active'
  | 'run_failed'
  | 'computer_use_blocked'
  | 'computer_use_start_allowed'
  | 'raw_debug_disabled'
  | 'raw_debug_enabled';

export function bridgeErrorFixture(
  code: BridgeErrorCode = 'CLI_FAILED',
  overrides: Partial<BridgeErrorPayload> = {},
): BridgeResult<never> {
  return {
    ok: false,
    data: null,
    error: {
      code,
      message: 'Command failed',
      stderrPreview: 'redacted stderr preview',
      command: 'imperaos ...',
      retryable: true,
      ...overrides,
    },
  };
}

export function bridgeSuccessFixture<T>(data: T): BridgeResult<T> {
  return {
    ok: true,
    data,
    error: null,
  };
}

export function installTauriInvokeMock(
  implementation: (command: string, args: Record<string, unknown>) => unknown = () => bridgeSuccessFixture({}),
): Mock {
  const invoke = vi.fn(implementation);
  vi.stubGlobal('__TAURI_INTERNALS__', {});
  vi.mock('@tauri-apps/api/core', () => ({ invoke }));
  return invoke;
}

export function resetBridgeMocks(): void {
  vi.unstubAllGlobals();
  vi.resetModules();
  vi.clearAllMocks();
}
