export type SuiteStatus = 'passed' | 'failed' | 'skipped';

export function frontendQaE2eBlockers(
  status: SuiteStatus,
  required: boolean,
): string[] {
  if (!required) {
    return [];
  }
  if (status === 'skipped') {
    return ['Playwright E2E did not run'];
  }
  if (status === 'failed') {
    return ['Playwright E2E failed'];
  }
  return [];
}
