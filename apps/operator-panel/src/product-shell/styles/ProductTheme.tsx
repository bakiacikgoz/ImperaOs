import { useLayoutEffect } from 'react';

import tokens from './ui-lab/tokens.css?inline';
import globals from './ui-lab/globals.css?inline';
import surfaces from './ui-lab/surfaces.css?inline';
import adapters from './shell.css?inline';

const runtimeGlobals = globals.replace(/^@import\s+['"].+?['"];\s*$/gm, '');
const uiLabTheme = `${tokens}\n${runtimeGlobals}\n${surfaces}`;

export function ProductTheme({ theme }: { theme: 'dark' | 'light' }) {
  useLayoutEffect(() => {
    const previousTheme = document.documentElement.dataset.theme;
    document.documentElement.dataset.theme = theme;
    return () => {
      if (previousTheme) {
        document.documentElement.dataset.theme = previousTheme;
      } else {
        delete document.documentElement.dataset.theme;
      }
    };
  }, [theme]);

  return <>
    <style data-ui-lab-theme>{uiLabTheme}</style>
    <style data-product-shell-adapters>{adapters}</style>
  </>;
}
