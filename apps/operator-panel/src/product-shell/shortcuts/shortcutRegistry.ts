export type ProductShellShortcutId = 'global-search';

export type ProductShellShortcut = {
  id: ProductShellShortcutId;
  ariaKeyShortcuts: string;
  matches(event: KeyboardEvent): boolean;
};

/**
 * Product-shell keyboard commands live in one registry so a route cannot
 * silently claim a global shortcut. Commands remain UI-only: they never
 * perform a governed action without its normal explicit control.
 */
export const PRODUCT_SHELL_SHORTCUTS: Record<ProductShellShortcutId, ProductShellShortcut> = {
  'global-search': {
    id: 'global-search',
    ariaKeyShortcuts: 'Control+K Meta+K',
    matches: (event) => (event.metaKey || event.ctrlKey)
      && !event.altKey
      && event.key.toLowerCase() === 'k',
  },
};
