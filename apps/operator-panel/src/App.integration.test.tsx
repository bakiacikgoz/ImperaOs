import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import * as bridge from './bridge';
import { renderOperatorPanel } from './test/render';
import { DEFAULT_SETTINGS, SETTINGS_KEY, type PanelSettings } from './settings';

type NavigationCase = {
  nav: string | RegExp;
  heading: string;
};

const NAVIGATION_TEST_TIMEOUT_MS = 15_000;
const WORKSPACE_NAVIGATION_CASES: NavigationCase[] = [
  { nav: 'Görevler', heading: 'Tasks' },
  { nav: 'Onaylar', heading: 'Approvals' },
  { nav: 'Çalıştırmalar', heading: 'Runs' },
];
const SYSTEM_NAVIGATION_CASES: NavigationCase[] = [
  { nav: 'Sistem Sağlığı', heading: 'System' },
  { nav: 'Yürütmeler', heading: 'Operations' },
  { nav: 'Ayarlar', heading: 'Settings' },
];
const GOVERNANCE_NAVIGATION_CASES: NavigationCase[] = [
  { nav: 'Loglar', heading: 'Logs' },
  { nav: 'Raporlar', heading: 'Reports' },
  { nav: 'Uyarılar', heading: 'Alerts' },
  { nav: 'Planlamalar', heading: 'Plans' },
  { nav: 'Kullanıcılar', heading: 'Users' },
  { nav: 'Roller', heading: 'Roles' },
  { nav: 'Politikalar', heading: 'Policy Packs' },
];

vi.mock('./bridge', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./bridge')>();
  return {
    ...actual,
    checkPermission: vi.fn(actual.checkPermission),
    decideApproval: vi.fn(actual.decideApproval),
    executeApproval: vi.fn(actual.executeApproval),
    exportRunArtifacts: vi.fn(actual.exportRunArtifacts),
    fetchIdentity: vi.fn(actual.fetchIdentity),
    generateSecurityReview: vi.fn(actual.generateSecurityReview),
    resolveConfig: vi.fn(actual.resolveConfig),
    runInstallRehearsal: vi.fn(actual.runInstallRehearsal),
    submitComputerUseRun: vi.fn(actual.submitComputerUseRun),
    submitTeamRun: vi.fn(actual.submitTeamRun),
    verifyControlPlaneEvidence: vi.fn(actual.verifyControlPlaneEvidence),
  };
});

function seedSettings(overrides: Partial<PanelSettings> = {}) {
  localStorage.setItem(
    SETTINGS_KEY,
    JSON.stringify({
      ...DEFAULT_SETTINGS,
      locale: 'en',
      rootDir: '.imperaos/test-ui/jobs',
      ...overrides,
    }),
  );
}

function renderApp(overrides: Partial<PanelSettings> = {}) {
  seedSettings(overrides);
  return renderOperatorPanel(<App />);
}

async function openView(user: ReturnType<typeof renderOperatorPanel>['user'], navName: string | RegExp) {
  await user.click(screen.getByRole('button', { name: navName }));
}

async function assertNavigationGroup(cases: NavigationCase[]) {
  const { user } = renderApp();

  expect(await screen.findByRole('heading', { name: 'Mission Control' })).toBeInTheDocument();
  expect(screen.getByText('Preview')).toBeInTheDocument();

  for (const item of cases) {
    await openView(user, item.nav);
    expect(await screen.findByRole('heading', { name: item.heading, level: 2 })).toBeInTheDocument();
  }
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  vi.spyOn(window, 'prompt').mockReturnValue('./exports/run-preview');
});

describe('App integration flows', () => {
  it(
    'navigates workspace operator views in browser preview mode',
    async () => {
      await assertNavigationGroup(WORKSPACE_NAVIGATION_CASES);
    },
    NAVIGATION_TEST_TIMEOUT_MS,
  );

  it(
    'navigates system operator views in browser preview mode',
    async () => {
      await assertNavigationGroup(SYSTEM_NAVIGATION_CASES);
    },
    NAVIGATION_TEST_TIMEOUT_MS,
  );

  it(
    'navigates governance operator views in browser preview mode',
    async () => {
      await assertNavigationGroup(GOVERNANCE_NAVIGATION_CASES);
    },
    NAVIGATION_TEST_TIMEOUT_MS,
  );

  it(
    'submits a team run through the preview bridge and returns to workspace',
    async () => {
    const { user } = renderApp({ operatorId: 'qa-operator' });

    await openView(user, 'Görevler');
    await user.type(screen.getByLabelText('Spec path'), 'examples/team/restricted_pilot.yaml');
    await user.type(screen.getByLabelText('Request'), 'Inspect the queue safely.');
    await user.click(screen.getAllByRole('button', { name: 'Submit run' })[0]);

    await waitFor(() => {
      expect(bridge.submitTeamRun).toHaveBeenCalledWith(
        expect.objectContaining({ operatorId: 'qa-operator' }),
        expect.objectContaining({
          specPath: 'examples/team/restricted_pilot.yaml',
          request: 'Inspect the queue safely.',
        }),
      );
    });
    expect(await screen.findByText('Submit run OK')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Mission Control' })).toBeInTheDocument();
    },
    NAVIGATION_TEST_TIMEOUT_MS,
  );

  it('keeps computer-use start fail-closed when the vision runtime is not qualified', async () => {
    const { user } = renderApp({ operatorId: 'qa-operator' });

    await openView(user, 'Görevler');
    const startButton = screen.getByRole('button', { name: 'Start session' });

    expect(startButton).toBeDisabled();
    expect(startButton.getAttribute('title') ?? '').toContain('Computer-use vision runtime blocked');
    await user.click(startButton);
    expect(bridge.submitComputerUseRun).not.toHaveBeenCalled();
  });

  it('executes the Mission Control approval CTA through explicit bridge args', async () => {
    const { user } = renderApp({ operatorId: 'qa-operator' });

    expect(await screen.findByRole('heading', { name: 'Mission Control' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Onayla ve Devam Et/i }));

    await waitFor(() => {
      expect(bridge.decideApproval).toHaveBeenCalledWith(
        expect.any(Object),
        'apr_20260308_device_action',
        true,
        'qa-operator',
        'mission control approval',
      );
      expect(bridge.executeApproval).toHaveBeenCalledWith(
        expect.any(Object),
        'apr_20260308_device_action',
        'qa-operator',
      );
    });
    expect(await screen.findByText('Onay akışı tamamlandı')).toBeInTheDocument();
  });

  it('disables approval mutations with an invalid operator id and approves with explicit confirmation when configured', async () => {
    const invalidOperator = renderApp({ operatorId: 'ab' });
    await openView(invalidOperator.user, 'Onaylar');
    expect(await screen.findByRole('button', { name: 'Approve' })).toBeDisabled();
    invalidOperator.unmount();

    const { user } = renderApp({ operatorId: 'qa-operator' });
    await openView(user, 'Onaylar');
    const approve = await screen.findByRole('button', { name: 'Approve' });

    await waitFor(() => expect(approve).not.toBeDisabled());
    await user.click(approve);

    await waitFor(() => {
      expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('ui:qa-operator'));
      expect(bridge.decideApproval).toHaveBeenCalledWith(
        expect.any(Object),
        'apr_20260308_device_action',
        true,
        'qa-operator',
        'operator workspace action',
      );
    });
    expect(await screen.findByText('Approve OK')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Execute' }));
    await waitFor(() => {
      expect(bridge.executeApproval).toHaveBeenCalledWith(
        expect.any(Object),
        'apr_20260308_device_action',
        'qa-operator',
      );
    });
    expect(await screen.findByText('Execute OK')).toBeInTheDocument();
  });

  it('requires debug raw and confirmation before exposing full artifact payloads', async () => {
    vi.mocked(window.confirm).mockReturnValue(false);
    const { user } = renderApp({ debugRaw: true });

    await openView(user, 'Çalıştırmalar');
    await user.click(await screen.findByRole('button', { name: 'Artifacts' }));
    const showRaw = await screen.findByRole('button', { name: 'Show raw' });

    await user.click(showRaw);
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('status.json'));
    expect(screen.getByRole('button', { name: 'Show raw' })).toBeInTheDocument();

    vi.mocked(window.confirm).mockReturnValue(true);
    await user.click(screen.getByRole('button', { name: 'Show raw' }));
    expect(await screen.findByRole('button', { name: 'Hide raw' })).toBeInTheDocument();
  });

  it('exports selected run artifacts with the modal target passed to the bridge', async () => {
    const { user } = renderApp({ operatorId: 'qa-operator' });

    await openView(user, 'Çalıştırmalar');
    const exportButton = await screen.findByRole('button', { name: 'Export' });
    await waitFor(() => expect(exportButton).not.toBeDisabled());
    await user.click(exportButton);
    const pathInput = await screen.findByLabelText('Export path');
    await user.clear(pathInput);
    await user.type(pathInput, './exports/run-preview');
    const exportButtons = screen.getAllByRole('button', { name: 'Export' });
    await user.click(exportButtons[exportButtons.length - 1]);

    await waitFor(() => {
      expect(bridge.exportRunArtifacts).toHaveBeenCalledWith(
        expect.any(Object),
        'run_20260308_0910',
        './exports/run-preview',
      );
    });
    expect(await screen.findByText('Export completed')).toBeInTheDocument();
  });

  it('verifies the latest evidence pack from the control-plane snapshot', async () => {
    const { user } = renderApp({ operatorId: 'qa-operator' });

    await openView(user, 'Evidence');
    expect(await screen.findByText('evp-preview-run')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Verify latest' }));

    await waitFor(() => {
      expect(bridge.verifyControlPlaneEvidence).toHaveBeenCalledWith(
        expect.any(Object),
        'artifacts/control-plane/evidence/evp-preview-run/manifest.json',
      );
    });
    expect(await screen.findByText('Evidence verification completed')).toBeInTheDocument();
    expect(screen.getByText('pass')).toBeInTheDocument();
    expect(screen.getAllByText('passed').length).toBeGreaterThanOrEqual(3);
  });

  it('refreshes system config with assistant runtime override args', async () => {
    const { user } = renderApp({
      assistantProvider: 'ollama',
      assistantFallbackProvider: 'transformers',
      assistantModel: 'qwen3.5:4b',
    });

    await openView(user, 'Sistem Sağlığı');
    await user.click(screen.getByRole('button', { name: 'Refresh config' }));

    await waitFor(() => {
      expect(bridge.resolveConfig).toHaveBeenCalledWith(
        expect.objectContaining({ assistantProvider: 'ollama', assistantModel: 'qwen3.5:4b' }),
        expect.objectContaining({
          provider: 'ollama',
          fallbackProvider: 'transformers',
          model: 'qwen3.5:4b',
        }),
      );
    });
  });

  it('runs operations through preview bridge fixtures and persists settings changes', async () => {
    const { user } = renderApp({ operatorId: 'qa-operator' });

    await openView(user, 'Yürütmeler');
    await user.click(screen.getByRole('button', { name: 'Who am I' }));

    await waitFor(() => expect(bridge.fetchIdentity).toHaveBeenCalledWith(expect.any(Object)));
    expect((await screen.findAllByText(/qa-operator/)).length).toBeGreaterThan(0);
    await user.clear(screen.getByLabelText('Permission'));
    await user.type(screen.getByLabelText('Permission'), 'runtime.audit');
    await user.click(screen.getByRole('button', { name: 'Check permission' }));
    await waitFor(() => expect(bridge.checkPermission).toHaveBeenCalledWith(expect.any(Object), 'runtime.audit'));

    await user.click(screen.getByRole('button', { name: 'Qualification' }));
    await user.click(screen.getByRole('button', { name: 'Install rehearsal' }));
    await waitFor(() => expect(bridge.runInstallRehearsal).toHaveBeenCalledWith(expect.any(Object), expect.any(Object)));

    await user.click(screen.getByRole('button', { name: 'Security' }));
    await user.click(screen.getByRole('button', { name: 'Security review' }));
    await waitFor(() => expect(bridge.generateSecurityReview).toHaveBeenCalledWith(expect.any(Object), expect.any(Object)));

    await openView(user, 'Ayarlar');
    const operatorInput = screen.getByLabelText('Operator ID');
    await user.clear(operatorInput);
    await user.type(operatorInput, 'ops-ui-qa');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    const stored = JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? '{}') as Partial<PanelSettings>;
    expect(stored.operatorId).toBe('ops-ui-qa');
    expect(await screen.findByText('Settings saved')).toBeInTheDocument();
  });
});
