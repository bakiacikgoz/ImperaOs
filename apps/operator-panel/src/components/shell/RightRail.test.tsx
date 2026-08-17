import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { RightRail, type SystemHealthSummary } from './RightRail';

const emptyHealth: SystemHealthSummary = {
  coreMode: 'auto',
  contractVersion: '3.0',
  health: 'Healthy',
  memoryUsagePct: null,
  cpuUsagePct: null,
  diskUsagePct: null,
  networkStatus: null,
};

const noop = () => undefined;

describe('RightRail', () => {
  it('renders honest empty states instead of fake metric bars', () => {
    const html = renderToStaticMarkup(
      <RightRail
        notifications={[]}
        selectedRunId="run_1"
        sessionId="session_1"
        mode="auto"
        profile="balanced"
        startedAt="-"
        duration="-"
        systemHealth={emptyHealth}
        pendingApprovals={[]}
        onDismissNotification={noop}
        onRefreshContext={noop}
        onResume={noop}
        onOpenTerminal={noop}
        onExport={noop}
        onCancel={noop}
        onViewDetails={noop}
        onViewApprovals={noop}
      />,
    );

    expect(html).toContain('Ölçüm yok');
    expect(html).toContain('Bekleyen onay yok');
    expect(html).not.toContain('42%');
    expect(html).not.toContain('18%');
    expect(html).not.toContain('27%');
  });

  it('renders progress bars only for real metric values and explains unavailable quick actions', () => {
    const html = renderToStaticMarkup(
      <RightRail
        notifications={[]}
        selectedRunId="run_1"
        sessionId="session_1"
        mode="auto"
        profile="balanced"
        startedAt="-"
        duration="-"
        systemHealth={{ ...emptyHealth, memoryUsagePct: 55 }}
        pendingApprovals={[{ id: 'apr_1', title: 'device_action', subtitle: 'run_1', time: '-' }]}
        resumeDisabled
        resumeDisabledReason="Resume unavailable"
        cancelDisabled
        cancelDisabledReason="Durdurulamaz"
        onDismissNotification={noop}
        onRefreshContext={noop}
        onResume={noop}
        onOpenTerminal={noop}
        onExport={noop}
        onCancel={noop}
        onViewDetails={noop}
        onViewApprovals={noop}
      />,
    );

    expect(html).toContain('aria-valuenow="55"');
    expect(html).toContain('Terminal Aç');
    expect(html).toContain('Resume unavailable');
    expect(html).toContain('Durdurulamaz');
    expect(html).toContain('data-disabled-reason="Resume unavailable"');
    expect(html).toContain('disabled=""');
  });
});
