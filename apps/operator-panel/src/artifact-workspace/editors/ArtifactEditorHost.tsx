import { lazy, Suspense, useState } from 'react';

import type {
  ArtifactContent,
  ArtifactAssetDescriptor,
  ArtifactAssetReadResult,
  ArtifactDescriptor,
  ArtifactFormSubmissionRequest,
  ArtifactFormSubmissionResult,
  ArtifactLicenseCapability,
  ArtifactRevision,
} from '../artifactContracts';
import type { ArtifactSaveState } from '../workspaceController';
import { resolveArtifactFeatureFlags } from '../artifactFeatureFlags';
import type { ArtifactContextSelection } from '../selectionContext';
import { FormSessionRuntime } from './form/formSessionRuntime';
import { ArtifactLicenseBlocked } from '../ui/ArtifactLicenseBlocked';

export type ArtifactSelection = ArtifactContextSelection;
export type ArtifactExportFormat = 'json' | 'submission-json' | 'markdown' | 'html' | 'txt' | 'source' | 'svg' | 'png' | 'csv' | 'xlsx' | 'pptx';

export interface ArtifactEditorProps {
  artifact: ArtifactDescriptor;
  revision: ArtifactRevision;
  content: ArtifactContent;
  mode: 'view' | 'edit' | 'suggest';
  saveState: ArtifactSaveState;
  onChange(next: ArtifactContent, selection?: ArtifactSelection): void;
  onSelectionChange(selection: ArtifactSelection | null): void;
  onRequestExport(format: ArtifactExportFormat): void;
  onImportAsset?(): Promise<ArtifactAssetDescriptor | null>;
  onResolveAsset?(assetId: string): Promise<ArtifactAssetReadResult | null>;
}

export interface ArtifactEditorHostProps extends ArtifactEditorProps {
  formRuntime?: FormSessionRuntime;
  onSubmitForm?(request: ArtifactFormSubmissionRequest): Promise<ArtifactFormSubmissionResult>;
  workspaceEnabled?: boolean;
  documentEnabled?: boolean;
  formEnabled?: boolean;
  codeEnabled?: boolean;
  flowEnabled?: boolean;
  spreadsheetEnabled?: boolean;
  canvasEnabled?: boolean;
  slidesEnabled?: boolean;
  licenseCapability?: ArtifactLicenseCapability;
  locale?: 'en' | 'tr';
}

const DocumentArtifactEditor = lazy(() =>
  import('./document/DocumentArtifactEditor').then((module) => ({
    default: module.DocumentArtifactEditor,
  })),
);

const FormArtifactEditor = lazy(() =>
  import('./form/FormArtifactEditor').then((module) => ({
    default: module.FormArtifactEditor,
  })),
);

const CodeArtifactEditor = lazy(() =>
  import('./code/CodeArtifactEditor').then((module) => ({
    default: module.CodeArtifactEditor,
  })),
);

const FlowArtifactEditor = lazy(() =>
  import('./flow/FlowArtifactEditor').then((module) => ({
    default: module.FlowArtifactEditor,
  })),
);

const SlidesArtifactEditor = lazy(() =>
  import('./slides/SlidesArtifactEditor').then((module) => ({
    default: module.SlidesArtifactEditor,
  })),
);

const SpreadsheetArtifactEditor = lazy(() =>
  import('./spreadsheet/SpreadsheetArtifactEditor').then((module) => ({
    default: module.SpreadsheetArtifactEditor,
  })),
);

const CanvasArtifactEditor = lazy(() =>
  import('./canvas/CanvasArtifactEditor').then((module) => ({
    default: module.CanvasArtifactEditor,
  })),
);

export function ArtifactEditorHost(props: ArtifactEditorHostProps) {
  const [ownedFormRuntime] = useState(() => new FormSessionRuntime());
  const resolvedFlags = resolveArtifactFeatureFlags(import.meta.env, {
    spreadsheet: props.licenseCapability?.kind === 'spreadsheet' && props.licenseCapability.enabled,
    canvas: props.licenseCapability?.kind === 'canvas' && props.licenseCapability.enabled,
  });
  const explicitlyEnabled = [
    props.documentEnabled,
    props.formEnabled,
    props.codeEnabled,
    props.flowEnabled,
    props.spreadsheetEnabled,
    props.canvasEnabled,
    props.slidesEnabled,
  ].some((value) => value === true);
  const workspaceEnabled = props.workspaceEnabled ?? (explicitlyEnabled || resolvedFlags.workspace);
  if (!workspaceEnabled) {
    return <div className="artifact-editor-placeholder" role="status">The artifact workspace is disabled by policy.</div>;
  }
  if (props.artifact.kind === 'form') {
    const enabled = props.formEnabled
      ?? resolvedFlags.form;
    if (!enabled) {
      return <div className="artifact-editor-placeholder" role="status">The form editor is disabled by policy.</div>;
    }
    return (
      <Suspense fallback={<div className="artifact-editor-loading" role="status">Loading form editor…</div>}>
        <FormArtifactEditor
          artifact={props.artifact}
          revision={props.revision}
          content={props.content}
          mode={props.mode === 'view' ? 'readonly' : 'edit'}
          runtime={props.formRuntime ?? ownedFormRuntime}
          locale={props.locale}
          onSubmit={props.onSubmitForm ? (response, idempotencyKey) => props.onSubmitForm?.({
            artifactId: props.artifact.artifactId,
            schemaRevisionId: props.revision.revisionId,
            response,
            persistencePolicy: 'none',
            idempotencyKey,
          }) as Promise<ArtifactFormSubmissionResult> : undefined}
        />
      </Suspense>
    );
  }
  if (props.artifact.kind === 'code') {
    const enabled = props.codeEnabled
      ?? resolvedFlags.code;
    if (!enabled) {
      return <div className="artifact-editor-placeholder" role="status">The code editor is disabled by policy.</div>;
    }
    return (
      <Suspense fallback={<div className="artifact-editor-loading" role="status">Loading code editor…</div>}>
        <CodeArtifactEditor {...props} />
      </Suspense>
    );
  }
  if (props.artifact.kind === 'flow') {
    const enabled = props.flowEnabled
      ?? resolvedFlags.flow;
    if (!enabled) {
      return <div className="artifact-editor-placeholder" role="status">The flow editor is disabled by policy.</div>;
    }
    return (
      <Suspense fallback={<div className="artifact-editor-loading" role="status">Loading flow editor…</div>}>
        <FlowArtifactEditor {...props} />
      </Suspense>
    );
  }
  if (props.artifact.kind === 'spreadsheet' || props.artifact.kind === 'canvas') {
    const kindEnabled = props.artifact.kind === 'spreadsheet'
      ? props.spreadsheetEnabled ?? resolvedFlags.spreadsheet
      : props.canvasEnabled ?? resolvedFlags.canvas;
    if (kindEnabled) {
      const Editor = props.artifact.kind === 'spreadsheet' ? SpreadsheetArtifactEditor : CanvasArtifactEditor;
      return (
        <Suspense fallback={<div className="artifact-editor-loading" role="status">Loading {props.artifact.kind} editor…</div>}>
          <Editor {...props} />
        </Suspense>
      );
    }
    const capability = {
      contractVersion: 'artifact-license-capability/v1' as const,
      kind: props.artifact.kind,
      enabled: false,
      reasonCode: 'ARTIFACT_LICENSE_FEATURE_DISABLED',
    };
    return <ArtifactLicenseBlocked
      artifact={props.artifact}
      content={props.content}
      capability={capability}
      onExport={props.onRequestExport}
    />;
  }
  if (props.artifact.kind === 'slides') {
    const enabled = props.slidesEnabled
      ?? resolvedFlags.slides;
    if (!enabled) {
      return <div className="artifact-editor-placeholder" role="status">The slides editor is disabled by policy.</div>;
    }
    return (
      <Suspense fallback={<div className="artifact-editor-loading" role="status">Loading slides editor…</div>}>
        <SlidesArtifactEditor key={props.artifact.artifactId} {...props} />
      </Suspense>
    );
  }
  if (props.artifact.kind !== 'document') {
    return (
      <div className="artifact-editor-placeholder" role="status">
        The {props.artifact.kind} editor will load in its governed implementation phase.
      </div>
    );
  }
  const documentEnabled = props.documentEnabled ?? resolvedFlags.document;
  if (!documentEnabled) {
    return <div className="artifact-editor-placeholder" role="status">The document editor is disabled by policy.</div>;
  }
  return (
    <Suspense fallback={<div className="artifact-editor-loading" role="status">Loading document editor…</div>}>
      <DocumentArtifactEditor {...props} />
    </Suspense>
  );
}
