import {
  Component,
  useEffect,
  useRef,
  useState,
  type ErrorInfo,
  type PropsWithChildren,
  type ReactNode,
} from 'react';
import { Group, Panel, Separator } from 'react-resizable-panels';
import type { ArtifactKind } from '../artifactContracts';
import { recordArtifactEditorLoadFailure } from '../artifactUiMetrics';

type ErrorBoundaryProps = PropsWithChildren<{ artifactKind?: ArtifactKind; readOnlyFallback?: ReactNode }>;

export class ArtifactEditorErrorBoundary extends Component<ErrorBoundaryProps, { failed: boolean; readOnly: boolean }> {
  state = { failed: false, readOnly: false };

  static getDerivedStateFromError(): { failed: boolean; readOnly: boolean } {
    return { failed: true, readOnly: false };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // React reports the component stack. Raw artifact content is intentionally not logged here.
    recordArtifactEditorLoadFailure(this.props.artifactKind ?? 'unknown');
  }

  render(): ReactNode {
    const supportReference = `artifact-editor-${this.props.artifactKind ?? 'unknown'}-load-failure`;
    if (this.state.readOnly) {
      return <section className="artifact-workbench-error" aria-label="Read-only artifact fallback">
        <strong>Artifact opened read-only.</strong>
        <p>The editor is isolated. The surrounding navigator, revision history, and governed export remain available.</p>
        {this.props.readOnlyFallback}
        <p>Support reference: <code>{supportReference}</code></p>
        <button type="button" onClick={() => this.setState({ failed: false, readOnly: false })}>Retry editor</button>
      </section>;
    }
    if (this.state.failed) {
      return (
        <div className="artifact-workbench-error" role="alert">
          <strong>The artifact editor could not be displayed.</strong>
          <p>The assistant remains available. Retry the editor or close the workbench.</p>
          <button type="button" onClick={() => this.setState({ failed: false })}>
            Retry editor
          </button>
          <button type="button" onClick={() => this.setState({ readOnly: true })}>
            Open artifact read-only
          </button>
          <button type="button" onClick={() => void navigator.clipboard?.writeText?.(supportReference)}>
            Copy support reference
          </button>
          <p>Support reference: <code>{supportReference}</code></p>
        </div>
      );
    }
    return this.props.children;
  }
}

function useCompactWorkbench(): boolean {
  const [compact, setCompact] = useState(
    () =>
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(max-width: 900px)').matches,
  );

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const query = window.matchMedia('(max-width: 900px)');
    const update = () => setCompact(query.matches);
    query.addEventListener('change', update);
    update();
    return () => query.removeEventListener('change', update);
  }, []);

  return compact;
}

export function ArtifactWorkbenchShell({
  children,
  workbench,
  onCloseWorkbench,
}: PropsWithChildren<{
  workbench: ReactNode;
  onCloseWorkbench: () => void;
  activeArtifactKind?: ArtifactKind;
}>) {
  const compact = useCompactWorkbench();
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!compact || !workbench) return;
    restoreFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButtonRef.current?.focus();
    const close = () => {
      onCloseWorkbench();
      restoreFocusRef.current?.focus();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      close();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      restoreFocusRef.current?.focus();
    };
  }, [compact, onCloseWorkbench, workbench]);

  if (!workbench) return children;

  const guardedWorkbench = workbench;
  if (compact) {
    return (
      <>
        {children}
        <div className="artifact-workbench-drawer">
          <button
            type="button"
            className="artifact-workbench-drawer-backdrop"
            aria-label="Close artifact workbench"
            onClick={onCloseWorkbench}
          />
          <section className="artifact-workbench-drawer-panel" role="dialog" aria-modal="true" aria-label="Artifact workbench">
            <header>
              <strong>Artifact workbench</strong>
              <button ref={closeButtonRef} type="button" onClick={onCloseWorkbench}>
                Close
              </button>
            </header>
            <div className="assistant-workbench-slot">{guardedWorkbench}</div>
          </section>
        </div>
      </>
    );
  }

  return (
    <Group
      className="artifact-workbench-shell"
      id="assistant-artifact-workbench"
      orientation="horizontal"
      defaultLayout={{ assistant: 64, workbench: 36 }}
    >
      <Panel id="assistant" minSize="420px" groupResizeBehavior="preserve-relative-size">
        {children}
      </Panel>
      <Separator className="artifact-workbench-resize-handle" aria-label="Resize artifact workbench" />
      <Panel id="workbench" minSize="300px" maxSize="55%">
        <div className="assistant-workbench-slot">{guardedWorkbench}</div>
      </Panel>
    </Group>
  );
}
