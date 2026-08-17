import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  invoke: vi.fn(),
  listen: vi.fn(),
  receive: null as ((event: { payload: unknown }) => void) | null,
}));

vi.mock('@tauri-apps/api/core', () => ({ invoke: mocks.invoke, isTauri: () => true }));
vi.mock('@tauri-apps/api/event', () => ({
  listen: mocks.listen.mockImplementation(async (_name: string, callback: (event: { payload: unknown }) => void) => {
    mocks.receive = callback;
    return () => undefined;
  }),
}));

import { renderOperatorPanel } from '../../test/render';
import { BrowserApprovalInbox } from './BrowserApprovalInbox';

describe('BrowserApprovalInbox', () => {
  it('requires explicit user confirmation before navigating the governed source tab to a popup URL', async () => {
    mocks.invoke.mockResolvedValue(undefined);
    const { user } = renderOperatorPanel(<BrowserApprovalInbox />);
    await vi.waitFor(() => expect(mocks.receive).not.toBeNull());
    mocks.receive?.({ payload: { kind: 'new_window', url: 'https://docs.example.com/', mode: 'user', taskId: null, sourceSessionLabel: 'imperaos-browser-user' } });

    expect(await screen.findByText('A new browser window needs your approval.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Approve and open' }));

    expect(mocks.invoke).toHaveBeenCalledWith('browser_navigate', {
      request: { label: 'imperaos-browser-user', url: 'https://docs.example.com/' },
    });
    expect(mocks.invoke).toHaveBeenCalledWith('browser_show', { request: { label: 'imperaos-browser-user' } });
  });
});
