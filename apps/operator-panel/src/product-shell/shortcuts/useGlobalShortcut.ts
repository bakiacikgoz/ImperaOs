import { useEffect } from 'react';

import {
  PRODUCT_SHELL_SHORTCUTS,
  type ProductShellShortcutId,
} from './shortcutRegistry';

export function useGlobalShortcut(id: ProductShellShortcutId, action: () => void) {
  useEffect(() => {
    const shortcut = PRODUCT_SHELL_SHORTCUTS[id];
    const listener = (event: KeyboardEvent) => {
      if (!shortcut.matches(event)) return;
      event.preventDefault();
      action();
    };
    window.addEventListener('keydown', listener);
    return () => window.removeEventListener('keydown', listener);
  }, [action, id]);
}
