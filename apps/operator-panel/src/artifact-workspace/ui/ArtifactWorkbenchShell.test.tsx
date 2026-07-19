import { fireEvent, screen } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderOperatorPanel } from '../../test/render';
import { ArtifactEditorErrorBoundary, ArtifactWorkbenchShell } from './ArtifactWorkbenchShell';
import { artifactUiMetricSnapshot, resetArtifactUiMetricsForTest } from '../artifactUiMetrics';

function setCompact(matches: boolean): void {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockImplementation(() => ({
      matches,
      media: '(max-width: 900px)',
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

function BrokenEditor(): never {
  throw new Error('editor mount failed');
}

function CompactHarness({ onClose }: { onClose: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>Workbench trigger</button>
      <ArtifactWorkbenchShell
        workbench={open ? <div>Document editor</div> : null}
        onCloseWorkbench={() => {
          setOpen(false);
          onClose();
        }}
      >
        <main>Assistant chat</main>
      </ArtifactWorkbenchShell>
    </div>
  );
}

describe('ArtifactWorkbenchShell', () => {
  beforeEach(() => {
    resetArtifactUiMetricsForTest();
    setCompact(false);
    class ResizeObserverStub {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    }
    Object.defineProperty(globalThis, 'ResizeObserver', {
      configurable: true,
      value: ResizeObserverStub,
    });
  });

  it('renders a keyboard-resizable desktop split', () => {
    renderOperatorPanel(
      <ArtifactWorkbenchShell workbench={<div>Document editor</div>} onCloseWorkbench={vi.fn()}>
        <main>Assistant chat</main>
      </ArtifactWorkbenchShell>,
    );

    expect(screen.getByText('Assistant chat')).toBeInTheDocument();
    expect(screen.getByText('Document editor')).toBeInTheDocument();
    expect(screen.getByRole('separator', { name: 'Resize artifact workbench' })).toHaveAttribute(
      'aria-orientation',
      'vertical',
    );
  });

  it('uses a compact dialog, closes with Escape, and restores focus', async () => {
    setCompact(true);
    const onClose = vi.fn();
    const { user } = renderOperatorPanel(<CompactHarness onClose={onClose} />);
    const trigger = screen.getByRole('button', { name: 'Workbench trigger' });
    await user.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Artifact workbench' });
    expect(dialog).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(trigger).toHaveFocus();
  });

  it('isolates only the editor and exposes real read-only content after a crash', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { user } = renderOperatorPanel(<div>
      <nav>Revision history remains available</nav>
      <ArtifactEditorErrorBoundary artifactKind="document" readOnlyFallback={<section>Bounded artifact content</section>}>
        <BrokenEditor />
      </ArtifactEditorErrorBoundary>
      <button type="button">Export</button>
    </div>);

    expect(screen.getByRole('alert')).toHaveTextContent('The artifact editor could not be displayed.');
    expect(screen.getByRole('button', { name: 'Retry editor' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open artifact read-only' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy support reference' })).toBeInTheDocument();
    expect(screen.getByText(/support reference:/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Open artifact read-only' }));
    expect(screen.getByText('Bounded artifact content')).toBeInTheDocument();
    expect(screen.getByText('Revision history remains available')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export' })).toBeEnabled();
    expect(artifactUiMetricSnapshot()).toContainEqual({
      name: 'imperaos_artifact_editor_load_failure_total',
      labels: { kind: 'document' },
      value: 1,
    });
    consoleError.mockRestore();
  });
});
