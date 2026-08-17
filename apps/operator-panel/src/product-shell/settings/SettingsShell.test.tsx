import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { SETTINGS_KEY } from '../../settings';
import { renderOperatorPanel } from '../../test/render';
import { useProductShellStore } from '../state/productShellStore';
import { SettingsShell } from './SettingsShell';

describe('SettingsShell', () => {
  beforeEach(() => {
    localStorage.removeItem(SETTINGS_KEY);
    useProductShellStore.setState({ theme: 'dark' });
  });

  it('persists operator settings and applies the selected product theme', async () => {
    const { user, container } = renderOperatorPanel(<SettingsShell />);

    expect(container.querySelector('.settings-shell .settings-sidebar')).toBeInTheDocument();
    expect(container.querySelector('.settings-content .settings-page')).toBeInTheDocument();
    expect(container.querySelector('.settings-block .settings-row')).toBeInTheDocument();
    await user.clear(screen.getByRole('textbox', { name: 'Operator identity' }));
    await user.type(screen.getByRole('textbox', { name: 'Operator identity' }), 'release-operator');
    await user.click(screen.getByRole('button', { name: 'Görünüm' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Theme' }), 'light');
    await user.click(screen.getByRole('button', { name: 'Save settings' }));

    expect(JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? '{}')).toMatchObject({ operatorId: 'release-operator', theme: 'light' });
    expect(useProductShellStore.getState().theme).toBe('light');
  });

  it('maps every enabled settings section to real content and leaves Cmd-K to global search', async () => {
    const { user } = renderOperatorPanel(<SettingsShell />);
    const settingsSearch = screen.getByRole('textbox', { name: 'Ayarlarda ara' });

    await user.click(screen.getByRole('button', { name: 'Asistan' }));
    expect(screen.getByRole('textbox', { name: 'Assistant profile' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Default approval profile' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Kısayollar' }));
    expect(screen.getByText('⌘/Ctrl K')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'AI Sağlayıcıları' })).toHaveAttribute('href', '#/system/settings');
    expect(screen.getByRole('link', { name: 'Güvenlik' })).toHaveAttribute('href', '#/system/settings');

    await user.keyboard('{Meta>}k{/Meta}');
    expect(settingsSearch).not.toHaveFocus();
  });
});
