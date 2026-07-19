import type { Page } from '@playwright/test';

const ARTIFACT_E2E_CAPABILITY_SNAPSHOT = {
  contractVersion: 'artifact-runtime-capability-snapshot/v1',
  rolloutStage: 'all_noncommercial',
  globalEnabled: true,
  enabledArtifactKinds: ['document', 'form', 'code', 'flow', 'spreadsheet', 'canvas', 'slides'],
  features: {
    'artifact_workspace.enabled': true,
    'artifact_workspace.document.enabled': true,
    'artifact_workspace.form.enabled': true,
    'artifact_workspace.code.enabled': true,
    'artifact_workspace.flow.enabled': true,
    'artifact_workspace.spreadsheet.enabled': true,
    'artifact_workspace.canvas.enabled': true,
    'artifact_workspace.slides.enabled': true,
    'artifact_workspace.export.enabled': true,
    'assistant_ui_runtime.enabled': false,
    'ai_sdk_tauri_transport.enabled': false,
  },
  licenses: { spreadsheet: false, canvas: false },
  kindCapabilities: Object.fromEntries(['document', 'form', 'code', 'flow', 'spreadsheet', 'canvas', 'slides'].map((kind) => [kind, {
    enabled: true,
    editable: true,
    exportable: true,
    reasonCode: null,
    requiresLicense: false,
    adapter: kind === 'spreadsheet' || kind === 'canvas' ? 'bundled_fallback' : 'built_in',
  }])),
};

async function installTauriCallbackHarness(page: Page): Promise<void> {
  await page.evaluate(() => {
    const internals = (window as unknown as { __TAURI_INTERNALS__: Record<string, unknown> }).__TAURI_INTERNALS__;
    const invoke = internals.invoke as (command: string, args: Record<string, unknown>) => Promise<unknown>;
    const callbacks = new Map<number, (data: unknown) => void>();
    let callbackId = 1;
    internals.callbacks = callbacks;
    internals.transformCallback = (callback?: (data: unknown) => void, once = false) => {
      const id = callbackId++;
      callbacks.set(id, (data) => {
        if (once) callbacks.delete(id);
        callback?.(data);
      });
      return id;
    };
    internals.unregisterCallback = (id: number) => callbacks.delete(id);
    internals.runCallback = (id: number, data: unknown) => callbacks.get(id)?.(data);
    internals.invoke = async (command: string, args: Record<string, unknown>) => {
      if (command === 'plugin:event|listen') return callbackId++;
      if (command === 'plugin:event|unlisten') return null;
      return invoke(command, args);
    };
  });
}

export async function installArtifactBridgeStub(page: Page): Promise<void> {
  await page.evaluate((capabilitySnapshot) => {
    const now = '2026-07-16T09:00:00Z';
    const contents = new Map<string, unknown>();
    let descriptor = {
      artifactId: 'artifact-preview-document',
      workspaceId: 'workspace-preview',
      kind: 'document',
      title: 'Launch plan',
      status: 'active',
      schemaVersion: 1,
      dataClass: 'internal',
      currentRevisionId: 'revision-1',
      currentRevisionNumber: 1,
      sourceSessionId: 'assistant-preview-session',
      sourceTurnId: 'assistant-preview-turn',
      createdByType: 'assistant',
      createdById: 'assistant-preview',
      updatedById: 'assistant-preview',
      createdAtUtc: now,
      updatedAtUtc: now,
      archivedAtUtc: null,
      etag: 'etag-1',
      metadata: { policyStatus: 'governed' },
    };
    let revision = {
      revisionId: 'revision-1',
      artifactId: descriptor.artifactId,
      parentRevisionId: null,
      baseRevisionId: null,
      revisionNumber: 1,
      schemaVersion: 1,
      mutationType: 'create',
      contentRelpath: 'workspace-preview/artifact-preview-document/revision-1.json',
      contentSha256: 'a'.repeat(64),
      contentSizeBytes: 64,
      contentEncoding: 'json',
      changeSummary: 'Created by assistant',
      authorType: 'assistant',
      authorId: 'assistant-preview',
      idempotencyKey: 'create-preview-document',
      createdAtUtc: now,
    };
    let content = {
      kind: 'document',
      schemaVersion: 1,
      language: 'en',
      pageMode: 'document',
      blocks: [
        {
          id: 'block-1',
          type: 'paragraph',
          props: {},
          content: [{ type: 'text', text: 'Initial governed draft', styles: {} }],
          children: [],
        },
      ],
    };
    const history = [revision];
    contents.set(revision.revisionId, content);
    const forks = new Map<string, {
      descriptor: typeof descriptor;
      revision: typeof revision;
      content: typeof content;
      history: Array<typeof revision>;
      contents: Map<string, typeof content>;
    }>();
    const mutationRequests: Array<Record<string, unknown>> = [];
    const exportRequests: Array<{ command: string; request: Record<string, unknown> }> = [];
    let pendingExportFormat = 'markdown';
    let mutationGate: Promise<void> | null = null;
    let releaseMutationGate: (() => void) | null = null;
    let failNextGet = false;

    const ok = (data: unknown) => ({ ok: true, data, error: null });
    const operation = () => ({ artifact: descriptor, revision, created: false, disposition: 'updated' });
    const nextRevision = (nextContent: typeof content, mutationType: string, changeSummary: string) => {
      const previous = revision;
      const revisionNumber = previous.revisionNumber + 1;
      descriptor = {
        ...descriptor,
        currentRevisionId: `revision-${revisionNumber}`,
        currentRevisionNumber: revisionNumber,
        updatedById: 'e2e-operator',
        etag: `etag-${revisionNumber}`,
      };
      revision = {
        ...previous,
        revisionId: `revision-${revisionNumber}`,
        parentRevisionId: previous.revisionId,
        revisionNumber,
        mutationType,
        changeSummary,
        authorType: 'user',
        authorId: 'e2e-operator',
        idempotencyKey: `${mutationType}-${revisionNumber}`,
      };
      content = nextContent;
      contents.set(revision.revisionId, content);
      history.unshift(revision);
    };

    (window as unknown as { __artifactE2eState: unknown }).__artifactE2eState = {
      exportRequests,
      snapshot: () => ({
        descriptor,
        revision,
        content,
        history: [...history],
        forks: Array.from(forks.values()).map((item) => ({
          descriptor: item.descriptor,
          revision: item.revision,
          content: item.content,
          history: [...item.history],
        })),
        mutationRequests: [...mutationRequests],
      }),
      holdMutations: () => {
        if (mutationGate) return;
        mutationGate = new Promise<void>((resolve) => { releaseMutationGate = resolve; });
      },
      releaseMutations: () => {
        releaseMutationGate?.();
        releaseMutationGate = null;
        mutationGate = null;
      },
      failNextGet: () => { failNextGet = true; },
      seedBulkRevision: (addedBlocks: number) => {
        nextRevision({
          ...content,
          blocks: [
            ...content.blocks,
            ...Array.from({ length: addedBlocks }, (_, index) => ({
              id: `bulk-${String(index).padStart(4, '0')}`,
              type: 'paragraph',
              props: {},
              content: [{ type: 'text', text: `Bulk block ${index}`, styles: {} }],
              children: [],
            })),
          ],
        }, 'replace_content', 'Seed bounded diff fixture');
      },
      seedRemoteConflict: () => {
        nextRevision({
          ...content,
          blocks: content.blocks.map((block) => ({ ...block })),
        }, 'replace_content', 'Remote concurrent edit');
      },
    };
    (window as unknown as { __TAURI_INTERNALS__: unknown }).__TAURI_INTERNALS__ = {
      invoke: async (command: string, args: Record<string, unknown>) => {
        if (command === 'bridge_artifact_handshake') return ok({ capabilitySnapshot });
        if (command === 'bridge_artifact_list') {
          return ok({ items: [descriptor, ...Array.from(forks.values(), (item) => item.descriptor)], next_cursor: null });
        }
        if (command === 'bridge_artifact_get') {
          if (failNextGet) {
            failNextGet = false;
            throw new Error('Controlled artifact reload failure');
          }
          const params = (args.payload as { params: Record<string, unknown> }).params;
          const artifactId = String(params.artifactId);
          const record = artifactId === descriptor.artifactId ? null : forks.get(artifactId);
          if (artifactId !== descriptor.artifactId && !record) throw new Error('Unknown artifact');
          const activeDescriptor = record?.descriptor ?? descriptor;
          const activeRevision = record?.revision ?? revision;
          const activeHistory = record?.history ?? history;
          const activeContents = record?.contents ?? contents;
          const requestedRevisionId = typeof params.revisionId === 'string' ? params.revisionId : activeRevision.revisionId;
          const requestedRevision = activeHistory.find((item) => item.revisionId === requestedRevisionId);
          const requestedContent = activeContents.get(requestedRevisionId);
          if (!requestedRevision || !requestedContent) throw new Error('Unknown artifact revision');
          return ok({ artifact: activeDescriptor, revision: requestedRevision, content: requestedContent });
        }
        if (command === 'bridge_artifact_history') {
          const params = (args.payload as { params: Record<string, unknown> }).params;
          const artifactId = String(params.artifactId);
          const record = artifactId === descriptor.artifactId ? null : forks.get(artifactId);
          if (artifactId !== descriptor.artifactId && !record) throw new Error('Unknown artifact');
          return ok({ items: record?.history ?? history, next_cursor: null });
        }
        if (command === 'bridge_artifact_mutate') {
          const params = (args.payload as { params: Record<string, unknown> }).params;
          mutationRequests.push(params);
          if (mutationGate) await mutationGate;
          if (
            params.artifactId !== descriptor.artifactId
            || params.expectedRevisionNumber !== descriptor.currentRevisionNumber
          ) {
            return {
              ok: false,
              data: null,
              error: {
                code: 'ARTIFACT_REVISION_CONFLICT',
                message: 'The artifact changed remotely.',
                stderrPreview: '',
                command,
                retryable: false,
              },
            };
          }
          nextRevision(params.content as typeof content, 'replace_content', String(params.changeSummary ?? 'Autosave'));
          return ok(operation());
        }
        if (command === 'bridge_artifact_duplicate') {
          const params = (args.payload as { params: Record<string, unknown> }).params;
          if (params.sourceArtifactId !== descriptor.artifactId) throw new Error('Unknown duplicate source');
          const sourceRevisionId = String(params.sourceRevisionId);
          if (!contents.has(sourceRevisionId)) throw new Error('Unknown duplicate source revision');
          const forkArtifact = {
            ...descriptor,
            artifactId: 'artifact-conflict-fork',
            title: String(params.title),
            currentRevisionId: 'fork-revision-1',
            currentRevisionNumber: 1,
            etag: 'fork-etag-1',
          };
          const forkRevision = {
            ...revision,
            revisionId: 'fork-revision-1',
            artifactId: forkArtifact.artifactId,
            parentRevisionId: null,
            baseRevisionId: sourceRevisionId,
            revisionNumber: 1,
            mutationType: 'duplicate',
            idempotencyKey: String(params.idempotencyKey),
            changeSummary: 'Created conflict fork',
            contentRelpath: `workspace-preview/${forkArtifact.artifactId}/fork-revision-1.json`,
          };
          const forkContent = (params.contentOverride ?? contents.get(sourceRevisionId)) as typeof content;
          const forkContents = new Map<string, typeof content>();
          forkContents.set(forkRevision.revisionId, forkContent);
          forkArtifact.metadata = {
            ...descriptor.metadata,
            forkedFromArtifactId: descriptor.artifactId,
            forkedFromRevisionId: sourceRevisionId,
          };
          forks.set(forkArtifact.artifactId, {
            descriptor: forkArtifact,
            revision: forkRevision,
            content: forkContent,
            history: [forkRevision],
            contents: forkContents,
          });
          return ok({ artifact: forkArtifact, revision: forkRevision, created: true, disposition: 'created' });
        }
        if (command === 'bridge_artifact_restore') {
          const params = (args.payload as { params: Record<string, unknown> }).params;
          const restored = contents.get(String(params.sourceRevisionId));
          if (!restored) throw new Error('Unknown source revision');
          nextRevision(restored as typeof content, 'restore', 'Revision restored');
          return ok(operation());
        }
        if (command === 'bridge_artifact_export_begin') {
          const request = args.request as Record<string, unknown>;
          pendingExportFormat = String(request.format);
          exportRequests.push({ command, request });
          return ok({ cancelled: false, exportId: `document-export-${exportRequests.length}`, ticket: `ticket-${exportRequests.length}`, expiresInMs: 60_000, maxBytes: 1_000_000 });
        }
        if (command === 'bridge_artifact_export_commit') {
          const request = args.request as { bytes: number[]; sha256: string } & Record<string, unknown>;
          exportRequests.push({ command, request });
          return ok({
            basename: pendingExportFormat === 'html' ? 'launch-plan.html' : 'launch-plan.md',
            sha256: request.sha256,
            sizeBytes: request.bytes.length,
          });
        }
        if (command === 'bridge_artifact_export_cancel') return ok({ cancelled: true });
        throw new Error(`Unexpected artifact E2E command: ${command}`);
      },
    };
  }, ARTIFACT_E2E_CAPABILITY_SNAPSHOT);
  await installTauriCallbackHarness(page);
}

export async function artifactExportCommands(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const state = (window as unknown as {
      __artifactE2eState: { exportRequests: Array<{ command: string }> };
    }).__artifactE2eState;
    return state.exportRequests.map((item) => item.command);
  });
}

export async function installFormArtifactBridgeStub(page: Page): Promise<void> {
  await page.addInitScript((capabilitySnapshot) => {
    window.addEventListener('keydown', (event) => {
      if (event.key !== 'F8') return;
    const now = '2026-07-16T09:00:00Z';
    const descriptor = {
      artifactId: 'artifact-preview-form', workspaceId: 'workspace-preview', kind: 'form', title: 'Intake form',
      status: 'active', schemaVersion: 1, dataClass: 'confidential', currentRevisionId: 'form-revision-1',
      currentRevisionNumber: 1, sourceSessionId: 'assistant-preview-session', sourceTurnId: 'assistant-preview-turn',
      createdByType: 'assistant', createdById: 'assistant-preview', updatedById: 'assistant-preview',
      createdAtUtc: now, updatedAtUtc: now, archivedAtUtc: null, etag: 'form-etag-1',
      metadata: { policyStatus: 'governed' },
    };
    const revision = {
      revisionId: 'form-revision-1', artifactId: descriptor.artifactId, parentRevisionId: null, baseRevisionId: null,
      revisionNumber: 1, schemaVersion: 1, mutationType: 'create', contentRelpath: 'workspace-preview/artifact-preview-form/form-revision-1.json',
      contentSha256: 'a'.repeat(64), contentSizeBytes: 256, contentEncoding: 'json', changeSummary: 'Created form',
      authorType: 'assistant', authorId: 'assistant-preview', idempotencyKey: 'create-preview-form', createdAtUtc: now,
    };
    const content = {
      kind: 'form', schemaVersion: 1,
      schema: {
        type: 'object', title: 'Private intake',
        properties: { name: { type: 'string', title: 'Name', minLength: 2 } },
        required: ['name'], additionalProperties: false,
      },
      uiSchema: {}, behavior: { submitMode: 'explicit', externalContinuation: 'approval_required' },
      sensitivePaths: ['/name'],
    };
    const submissions: Array<Record<string, unknown>> = [];
    const ok = (data: unknown) => ({ ok: true, data, error: null });
    (window as unknown as { __artifactFormE2eState: unknown }).__artifactFormE2eState = {
      snapshot: () => ({ submissions: [...submissions] }),
    };
    (window as unknown as { __TAURI_INTERNALS__: unknown }).__TAURI_INTERNALS__ = {
      invoke: async (command: string, args: Record<string, unknown>) => {
        if (command === 'bridge_artifact_handshake') return ok({ capabilitySnapshot });
        if (command === 'bridge_artifact_list') return ok({ items: [descriptor], next_cursor: null });
        if (command === 'bridge_artifact_get') return ok({ artifact: descriptor, revision, content });
        if (command === 'bridge_artifact_history') return ok({ items: [revision], next_cursor: null });
        if (command === 'bridge_artifact_form_submit') {
          const params = (args.payload as { params: Record<string, unknown> }).params;
          submissions.push(params);
          const evidence = document.createElement('meta');
          evidence.setAttribute('name', 'artifact-form-submission');
          evidence.setAttribute('content', JSON.stringify(params));
          document.head.append(evidence);
          return ok({
            submissionId: 'submission-preview-1', artifactId: descriptor.artifactId,
            schemaRevisionId: revision.revisionId, status: 'pending_continuation',
            responseSha256: 'b'.repeat(64), continuationAction: 'require_approval',
            approvalId: 'approval-preview-1', reasonCode: 'FORM_CONTINUATION_APPROVAL_REQUIRED',
            actionHash: 'c'.repeat(64), disposition: submissions.length === 1 ? 'created' : 'idempotent_replay',
          });
        }
        throw new Error(`Unexpected form artifact E2E command: ${command}`);
      },
    };
    const internals = (window as unknown as { __TAURI_INTERNALS__: Record<string, unknown> }).__TAURI_INTERNALS__;
    const invoke = internals.invoke as (command: string, args: Record<string, unknown>) => Promise<unknown>;
    const callbacks = new Map<number, (data: unknown) => void>();
    let callbackId = 1;
    internals.callbacks = callbacks;
    internals.transformCallback = (callback?: (data: unknown) => void, once = false) => {
      const id = callbackId++;
      callbacks.set(id, (data) => { if (once) callbacks.delete(id); callback?.(data); });
      return id;
    };
    internals.unregisterCallback = (id: number) => callbacks.delete(id);
    internals.runCallback = (id: number, data: unknown) => callbacks.get(id)?.(data);
    internals.invoke = async (command: string, args: Record<string, unknown>) => {
      if (command === 'plugin:event|listen') return callbackId++;
      if (command === 'plugin:event|unlisten') return null;
      return invoke(command, args);
    };
    });
  }, ARTIFACT_E2E_CAPABILITY_SNAPSHOT);
}

export async function installCodeArtifactBridgeStub(page: Page): Promise<void> {
  await page.evaluate((capabilitySnapshot) => {
    const now = '2026-07-16T09:00:00Z';
    let descriptor = {
      artifactId: 'artifact-preview-document', workspaceId: 'workspace-preview', kind: 'code', title: 'Safe code',
      status: 'active', schemaVersion: 2, dataClass: 'internal', currentRevisionId: 'code-revision-1',
      currentRevisionNumber: 1, sourceSessionId: 'assistant-preview-session', sourceTurnId: 'assistant-preview-turn',
      createdByType: 'assistant', createdById: 'assistant-preview', updatedById: 'assistant-preview',
      createdAtUtc: now, updatedAtUtc: now, archivedAtUtc: null, etag: 'code-etag-1',
      metadata: { policyStatus: 'governed' },
    };
    let revision = {
      revisionId: 'code-revision-1', artifactId: descriptor.artifactId, parentRevisionId: null as string | null,
      baseRevisionId: null as string | null, revisionNumber: 1, schemaVersion: 2, mutationType: 'create',
      contentRelpath: 'workspace-preview/artifact-preview-document/code-revision-1.json',
      contentSha256: 'a'.repeat(64), contentSizeBytes: 128, contentEncoding: 'json',
      changeSummary: 'Created safe code', authorType: 'assistant', authorId: 'assistant-preview',
      idempotencyKey: 'create-preview-code', createdAtUtc: now,
    };
    let content = {
      kind: 'code', schemaVersion: 2, filename: 'main.py', language: 'python',
      text: "print('display only')\n", lineEnding: 'lf', executionPolicy: 'deny',
    };
    const history = [revision];
    const commands: string[] = [];
    let exportedBytes: number[] | null = null;
    const ok = (data: unknown) => ({ ok: true, data, error: null });
    (window as unknown as { __codeArtifactE2eState: unknown }).__codeArtifactE2eState = {
      commands,
      snapshot: () => ({ descriptor, revision, content, history: [...history], exportedBytes }),
    };
    (window as unknown as { __TAURI_INTERNALS__: unknown }).__TAURI_INTERNALS__ = {
      invoke: async (command: string, args: Record<string, unknown>) => {
        commands.push(command);
        if (command === 'bridge_artifact_handshake') return ok({ capabilitySnapshot });
        if (command === 'bridge_artifact_list') return ok({ items: [descriptor], next_cursor: null });
        if (command === 'bridge_artifact_get') return ok({ artifact: descriptor, revision, content });
        if (command === 'bridge_artifact_history') return ok({ items: history, next_cursor: null });
        if (command === 'bridge_artifact_mutate') {
          const params = (args.payload as { params: Record<string, unknown> }).params;
          const previous = revision;
          const revisionNumber = previous.revisionNumber + 1;
          content = params.content as typeof content;
          revision = {
            ...previous, revisionId: `code-revision-${revisionNumber}`, parentRevisionId: previous.revisionId,
            revisionNumber, mutationType: 'replace_content', authorType: 'user', authorId: 'code-operator',
            idempotencyKey: String(params.idempotencyKey), changeSummary: String(params.changeSummary),
          };
          descriptor = {
            ...descriptor, currentRevisionId: revision.revisionId, currentRevisionNumber: revisionNumber,
            updatedById: 'code-operator', etag: `code-etag-${revisionNumber}`,
          };
          history.unshift(revision);
          return ok({ artifact: descriptor, revision, created: false, disposition: 'updated' });
        }
        if (command === 'bridge_artifact_export_begin') {
          return ok({ cancelled: false, exportId: 'code-export-1', ticket: 'code-ticket-1', expiresInMs: 60_000, maxBytes: 1_000_000 });
        }
        if (command === 'bridge_artifact_export_commit') {
          const request = args.request as { bytes: number[]; sha256: string };
          exportedBytes = [...request.bytes];
          return ok({ basename: 'main.py', sha256: request.sha256, sizeBytes: request.bytes.length });
        }
        if (command === 'bridge_artifact_export_cancel') return ok({ cancelled: true });
        throw new Error(`Unexpected code artifact E2E command: ${command}`);
      },
    };
  }, ARTIFACT_E2E_CAPABILITY_SNAPSHOT);
  await installTauriCallbackHarness(page);
}

export async function codeArtifactCommands(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const state = (window as unknown as { __codeArtifactE2eState: { commands: string[] } }).__codeArtifactE2eState;
    return [...state.commands];
  });
}

export async function installStructuredArtifactBridgeStub(
  page: Page,
  kind: 'spreadsheet' | 'canvas' | 'slides',
): Promise<void> {
  await page.evaluate(({ artifactKind, capabilitySnapshot }) => {
    const now = '2026-07-17T09:00:00Z';
    const spreadsheetCells = Object.fromEntries(
      Array.from({ length: 10_000 }, (_, index) => [
        `A${index + 1}`,
        { value: index === 0 ? '=1+1' : index + 1 },
      ]),
    );
    const contents = {
      spreadsheet: {
        kind: 'spreadsheet', schemaVersion: 2, calculationMode: 'disabled',
        sheets: [{
          id: 'sheet-1', name: 'Budget', columns: [],
          cells: spreadsheetCells,
        }],
      },
      canvas: {
        kind: 'canvas', schemaVersion: 2,
        snapshot: { objects: [
          {
            id: 'note-1', type: 'note', x: 1, y: 2, width: 200, height: 100,
            text: '<script>local text only</script>',
          },
          {
            id: 'image-1', type: 'image', x: 20, y: 2, width: 160, height: 100,
            assetId: 'asset-local-1',
          },
        ] },
        assetIds: ['asset-local-1'], embeds: 'deny', remoteAssets: 'deny',
      },
      slides: {
        kind: 'slides', schemaVersion: 2,
        theme: { name: 'ImperaOS', backgroundColor: 'FFFFFF', foregroundColor: '172033', accentColor: '6E57FF' },
        slides: [{ id: 'slide-1', title: 'Overview', elements: [{
          id: 'text-1', type: 'text', x: 0.5, y: 0.5, width: 8, height: 1,
          text: 'Governed deck', fontSize: 30, bold: false,
        }] }],
        assetIds: [],
      },
    } as const;
    let content: Record<string, unknown> = structuredClone(contents[artifactKind]);
    let descriptor = {
      artifactId: 'artifact-preview-document', workspaceId: 'workspace-preview', kind: artifactKind,
      title: artifactKind === 'slides' ? 'Deck' : artifactKind === 'canvas' ? 'Board' : 'Budget',
      status: 'active', schemaVersion: 2, dataClass: 'internal', currentRevisionId: `${artifactKind}-revision-1`,
      currentRevisionNumber: 1, sourceSessionId: 'assistant-preview-session', sourceTurnId: 'assistant-preview-turn',
      createdByType: 'assistant', createdById: 'assistant-preview', updatedById: 'assistant-preview',
      createdAtUtc: now, updatedAtUtc: now, archivedAtUtc: null, etag: `${artifactKind}-etag-1`,
      metadata: { policyStatus: 'governed', licenseStatus: 'forced_off' },
    };
    let revision = {
      revisionId: `${artifactKind}-revision-1`, artifactId: descriptor.artifactId,
      parentRevisionId: null as string | null, baseRevisionId: null as string | null,
      revisionNumber: 1, schemaVersion: 2, mutationType: 'create',
      contentRelpath: `workspace-preview/${descriptor.artifactId}/revision-1.json`,
      contentSha256: 'a'.repeat(64), contentSizeBytes: 256, contentEncoding: 'json',
      changeSummary: 'Created governed artifact', authorType: 'assistant', authorId: 'assistant-preview',
      idempotencyKey: `create-${artifactKind}`, createdAtUtc: now,
    };
    const history = [revision];
    const commands: string[] = [];
    let exportedBytes: number[] = [];
    const ok = (data: unknown) => ({ ok: true, data, error: null });
    (window as unknown as { __structuredArtifactE2eState: unknown }).__structuredArtifactE2eState = {
      commands,
      snapshot: () => ({ descriptor, revision, content, exportedBytes: [...exportedBytes] }),
    };
    (window as unknown as { __TAURI_INTERNALS__: unknown }).__TAURI_INTERNALS__ = {
      invoke: async (command: string, args: Record<string, unknown>) => {
        commands.push(command);
        if (command === 'bridge_artifact_handshake') return ok({ capabilitySnapshot });
        if (command === 'bridge_artifact_list') return ok({ items: [descriptor], next_cursor: null });
        if (command === 'bridge_artifact_get') return ok({ artifact: descriptor, revision, content });
        if (command === 'bridge_artifact_history') return ok({ items: history, next_cursor: null });
        if (command === 'bridge_artifact_asset_get' && artifactKind === 'canvas') {
          const params = (args.payload as { params: Record<string, unknown> }).params;
          const assetId = String(params.assetId);
          if (assetId !== 'asset-local-1') throw new Error('Unknown canvas asset');
          return ok({
            asset: {
              assetId, workspaceId: descriptor.workspaceId, sha256: 'b'.repeat(64), mediaType: 'image/png',
              sizeBytes: 68, relativePath: 'assets/asset-local-1.png', width: 1, height: 1,
              originalName: 'asset-local-1.png', dataClass: descriptor.dataClass,
              createdById: 'assistant-preview', createdAtUtc: now,
            },
            contentBase64: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
          });
        }
        if (command === 'bridge_artifact_mutate' || command === 'bridge_artifact_slides_patch') {
          const params = (args.payload as { params: Record<string, unknown> }).params;
          if (command === 'bridge_artifact_mutate') content = params.content as Record<string, unknown>;
          const previous = revision;
          const revisionNumber = previous.revisionNumber + 1;
          revision = {
            ...previous, revisionId: `${artifactKind}-revision-${revisionNumber}`,
            parentRevisionId: previous.revisionId, revisionNumber,
            mutationType: command === 'bridge_artifact_slides_patch' ? 'slide_patch' : 'replace_content',
            idempotencyKey: String(params.idempotencyKey), changeSummary: 'Structured edit',
          };
          descriptor = {
            ...descriptor, currentRevisionId: revision.revisionId,
            currentRevisionNumber: revisionNumber, etag: `${artifactKind}-etag-${revisionNumber}`,
          };
          history.unshift(revision);
          return ok({ artifact: descriptor, revision, created: false, disposition: 'updated' });
        }
        if (command === 'bridge_artifact_export_begin') {
          return ok({ cancelled: false, exportId: `${artifactKind}-export-1`, ticket: `${artifactKind}-ticket-1`, expiresInMs: 60_000, maxBytes: 5_000_000 });
        }
        if (command === 'bridge_artifact_export_commit') {
          const request = args.request as { bytes: number[]; sha256: string };
          exportedBytes = [...request.bytes];
          return ok({ basename: `${artifactKind}.export`, sha256: request.sha256, sizeBytes: request.bytes.length });
        }
        if (command === 'bridge_artifact_export_cancel') return ok({ cancelled: true });
        throw new Error(`Unexpected structured artifact E2E command: ${command}`);
      },
    };
  }, { artifactKind: kind, capabilitySnapshot: ARTIFACT_E2E_CAPABILITY_SNAPSHOT });
  await installTauriCallbackHarness(page);
}

export async function structuredArtifactCommands(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const state = (window as unknown as {
      __structuredArtifactE2eState: { commands: string[] };
    }).__structuredArtifactE2eState;
    return [...state.commands];
  });
}

export async function codeArtifactExportedText(page: Page): Promise<string | null> {
  return page.evaluate(() => {
    const state = (window as unknown as {
      __codeArtifactE2eState: { snapshot(): { exportedBytes: number[] | null } };
    }).__codeArtifactE2eState;
    const bytes = state.snapshot().exportedBytes;
    return bytes ? new TextDecoder().decode(new Uint8Array(bytes)) : null;
  });
}

export async function installFlowArtifactBridgeStub(page: Page): Promise<void> {
  await page.evaluate((capabilitySnapshot) => {
    const now = '2026-07-16T10:00:00Z';
    let descriptor = {
      artifactId: 'artifact-preview-document', workspaceId: 'workspace-preview', kind: 'flow', title: 'Approval flow',
      status: 'active', schemaVersion: 2, dataClass: 'internal', currentRevisionId: 'flow-revision-1',
      currentRevisionNumber: 1, sourceSessionId: 'assistant-preview-session', sourceTurnId: 'assistant-preview-turn',
      createdByType: 'assistant', createdById: 'assistant-preview', updatedById: 'assistant-preview',
      createdAtUtc: now, updatedAtUtc: now, archivedAtUtc: null, etag: 'flow-etag-1', metadata: { policyStatus: 'governed' },
    };
    let revision = {
      revisionId: 'flow-revision-1', artifactId: descriptor.artifactId, parentRevisionId: null as string | null,
      baseRevisionId: null as string | null, revisionNumber: 1, schemaVersion: 2, mutationType: 'create',
      contentRelpath: 'workspace-preview/artifact-preview-document/flow-revision-1.json',
      contentSha256: 'a'.repeat(64), contentSizeBytes: 256, contentEncoding: 'json',
      changeSummary: 'Created approval flow', authorType: 'assistant', authorId: 'assistant-preview',
      idempotencyKey: 'create-preview-flow', createdAtUtc: now,
    };
    let content = {
      kind: 'flow', schemaVersion: 2,
      nodes: [
        { id: 'start', type: 'input', position: { x: 0, y: 0 }, data: { label: '<Start>' } },
        { id: 'review', type: 'process', position: { x: 240, y: 0 }, data: { label: 'Review' } },
      ],
      edges: [{ id: 'edge-1', source: 'start', target: 'review', label: 'submit' }],
      viewport: { x: 0, y: 0, zoom: 1 },
    };
    const history = [revision];
    const commands: string[] = [];
    let exportedBytes: number[] | null = null;
    const ok = (data: unknown) => ({ ok: true, data, error: null });
    (window as unknown as { __flowArtifactE2eState: unknown }).__flowArtifactE2eState = {
      commands,
      snapshot: () => ({ descriptor, revision, content, exportedBytes }),
    };
    (window as unknown as { __TAURI_INTERNALS__: unknown }).__TAURI_INTERNALS__ = {
      invoke: async (command: string, args: Record<string, unknown>) => {
        commands.push(command);
        if (command === 'bridge_artifact_handshake') return ok({ capabilitySnapshot });
        if (command === 'bridge_artifact_list') return ok({ items: [descriptor], next_cursor: null });
        if (command === 'bridge_artifact_get') return ok({ artifact: descriptor, revision, content });
        if (command === 'bridge_artifact_history') return ok({ items: history, next_cursor: null });
        if (command === 'bridge_artifact_mutate') {
          const params = (args.payload as { params: Record<string, unknown> }).params;
          const previous = revision;
          const revisionNumber = previous.revisionNumber + 1;
          content = params.content as typeof content;
          revision = {
            ...previous, revisionId: `flow-revision-${revisionNumber}`, parentRevisionId: previous.revisionId,
            revisionNumber, mutationType: 'replace_content', authorType: 'user', authorId: 'flow-operator',
            idempotencyKey: String(params.idempotencyKey), changeSummary: String(params.changeSummary),
          };
          descriptor = {
            ...descriptor, currentRevisionId: revision.revisionId, currentRevisionNumber: revisionNumber,
            updatedById: 'flow-operator', etag: `flow-etag-${revisionNumber}`,
          };
          history.unshift(revision);
          return ok({ artifact: descriptor, revision, created: false, disposition: 'updated' });
        }
        if (command === 'bridge_artifact_export_begin') {
          return ok({ cancelled: false, exportId: 'flow-export-1', ticket: 'flow-ticket-1', expiresInMs: 60_000, maxBytes: 1_000_000 });
        }
        if (command === 'bridge_artifact_export_commit') {
          const request = args.request as { bytes: number[]; sha256: string };
          exportedBytes = [...request.bytes];
          return ok({ basename: 'approval-flow.svg', sha256: request.sha256, sizeBytes: request.bytes.length });
        }
        if (command === 'bridge_artifact_export_cancel') return ok({ cancelled: true });
        throw new Error(`Unexpected flow artifact E2E command: ${command}`);
      },
    };
  }, ARTIFACT_E2E_CAPABILITY_SNAPSHOT);
  await installTauriCallbackHarness(page);
}

export async function flowArtifactEvidence(page: Page): Promise<{ commands: string[]; exportedText: string | null }> {
  return page.evaluate(() => {
    const state = (window as unknown as {
      __flowArtifactE2eState: { commands: string[]; snapshot(): { exportedBytes: number[] | null } };
    }).__flowArtifactE2eState;
    const bytes = state.snapshot().exportedBytes;
    return {
      commands: [...state.commands],
      exportedText: bytes ? new TextDecoder().decode(new Uint8Array(bytes)) : null,
    };
  });
}
