import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import App from './App';

describe('App', () => {
  it('renders the operator shell without client effects', () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain('ImperaOS');
    expect(html).toContain('Mission Control');
    expect(html).toContain('AI Assistant');
    expect(html).toContain('SİSTEM SAĞLIĞI');
  });
});
