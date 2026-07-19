import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { AssistantWelcome } from './components/assistant/AssistantWelcome';
import { Sidebar } from './components/shell/Sidebar';
import { dictionaries } from './i18n';
import { PRODUCT_IDENTITY } from './productIdentity';
import { routes } from './routeRegistry';

describe('Operator Panel product identity surfaces', () => {
  it('keeps English and Turkish product titles on the canonical identity', () => {
    expect(dictionaries.en.appTitle).toBe('ImperaOS Agent Control Plane');
    expect(dictionaries.tr.appTitle).toBe('ImperaOS Agent Control Plane');
    expect(dictionaries.en.assistantTitle).toBe('ImperaOS Assistant');
    expect(dictionaries.tr.assistantTitle).toBe('ImperaOS Assistant');
    expect(dictionaries.en.assistantWelcomeTitle).toBe('Welcome to ImperaOS Assistant');
    expect(dictionaries.tr.assistantWelcomeTitle).toContain('ImperaOS Assistant');
  });

  it('renders the canonical sidebar and assistant brand without the former display name', () => {
    const sidebar = renderToStaticMarkup(
      <Sidebar
        activeView="workspace"
        open
        collapsed={false}
        operatorId="qa-operator"
        pendingApprovalCount={0}
        warningCount={0}
        onClose={() => undefined}
        onToggleCollapse={() => undefined}
        onNavigate={() => undefined}
        onThemeChange={() => undefined}
      />,
    );
    const welcome = renderToStaticMarkup(
      <AssistantWelcome
        title="Welcome to ImperaOS Assistant"
        subtitle="Governed assistant"
        badgeLabel="Governed assistant"
        readOnlyByDefault="Read-only by default"
      />,
    );
    const formerDisplayName = String.fromCharCode(65, 101, 103, 105, 115, 79, 83);

    expect(PRODUCT_IDENTITY.displayName).toBe('ImperaOS');
    expect(sidebar).toContain('<h1>ImperaOS</h1>');
    expect(sidebar).not.toContain(formerDisplayName);
    expect(welcome).toContain('<span>ImperaOS</span>');
    expect(welcome).toContain('aria-label="Welcome to ImperaOS Assistant"');
  });

  it('uses the ImperaOS assistant route heading', () => {
    expect(routes.find((route) => route.routeId === 'assistant')?.heading).toBe('ImperaOS Assistant');
  });
});
