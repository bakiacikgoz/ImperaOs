import { invoke } from '@tauri-apps/api/core';
import { z } from 'zod';

import {
  ArtifactAssetImportResultSchema,
  ArtifactAssetReadResultSchema,
  ArtifactAssetSelectResultSchema,
  ArtifactExportBeginResultSchema,
  ArtifactExportCancelResultSchema,
  ArtifactExportResultSchema,
  ArtifactFormSubmissionResultSchema,
  ArtifactHistoryWireSchema,
  ArtifactListWireSchema,
  ArtifactMutationProposalResultSchema,
  ArtifactOperationResultSchema,
  ArtifactReadResultSchema,
  ArtifactRpcHandshakeCapabilitySnapshotSchema,
  type ArtifactArchiveRequest,
  type ArtifactAssetImportRequest,
  type ArtifactAssetImportResult,
  type ArtifactAssetReadResult,
  type ArtifactAssetSelectResult,
  type ArtifactCreateRequest,
  type ArtifactDuplicateRequest,
  type ArtifactExportBeginRequest,
  type ArtifactExportBeginResult,
  type ArtifactExportResult,
  type ArtifactEvidenceImportRequest,
  type ArtifactFormSubmissionRequest,
  type ArtifactFormSubmissionResult,
  type ArtifactGetRequest,
  type ArtifactHistoryRequest,
  type ArtifactHistoryResult,
  type ArtifactListRequest,
  type ArtifactListResult,
  type ArtifactMutationProposalResult,
  type ArtifactMutationProposalRequest,
  type ArtifactMutationRequest,
  type ArtifactOperationResult,
  type ArtifactReadResult,
  type ArtifactRuntimeCapabilitySnapshot,
  type ArtifactRestoreRequest,
  type SpreadsheetCellPatchRequest,
  type SlidePatchRequest,
} from './artifactContracts';


const DEFAULT_TIMEOUT_MS = 15_000;

const NativeErrorSchema = z
  .object({
    code: z.string().min(1).max(100),
    message: z.string().min(1).max(500),
    stderrPreview: z.string(),
    command: z.string(),
    retryable: z.boolean(),
  })
  .strict();

const NativeResultSchema = z.discriminatedUnion('ok', [
  z.object({ ok: z.literal(true), data: z.unknown(), error: z.null() }).strict(),
  z.object({ ok: z.literal(false), data: z.null(), error: NativeErrorSchema }).strict(),
]);

export class ArtifactBridgeError extends Error {
  readonly code: string;
  readonly retryable: boolean;
  readonly command: string;

  constructor(code: string, message: string, retryable: boolean, command: string) {
    super(message);
    this.name = 'ArtifactBridgeError';
    this.code = code;
    this.retryable = retryable;
    this.command = command;
  }
}

export class ArtifactContractError extends ArtifactBridgeError {
  constructor(command: string) {
    super(
      'ARTIFACT_RPC_PROTOCOL_MISMATCH',
      'Artifact bridge response did not match the versioned runtime contract.',
      false,
      command,
    );
    this.name = 'ArtifactContractError';
  }
}

type ArtifactParams = Record<string, unknown>;

function compactParams(value: ArtifactParams): ArtifactParams {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined));
}

async function callArtifact<T>(
  command: string,
  params: ArtifactParams,
  schema: z.ZodType<T>,
  idempotencyKey: string | null = null,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const envelope = NativeResultSchema.safeParse(
    await invoke<unknown>(command, {
      payload: {
        params: compactParams(params),
        idempotencyKey,
        timeoutMs,
      },
    }),
  );
  if (!envelope.success) {
    throw new ArtifactContractError(command);
  }
  if (!envelope.data.ok) {
    const { code, message, retryable } = envelope.data.error;
    throw new ArtifactBridgeError(code, message, retryable, command);
  }
  const parsed = schema.safeParse(envelope.data.data);
  if (!parsed.success) {
    throw new ArtifactContractError(command);
  }
  return parsed.data;
}

async function callNativeExport<T>(
  command: string,
  request: ArtifactParams,
  schema: z.ZodType<T>,
): Promise<T> {
  const envelope = NativeResultSchema.safeParse(await invoke<unknown>(command, { request }));
  if (!envelope.success) {
    throw new ArtifactContractError(command);
  }
  if (!envelope.data.ok) {
    const { code, message, retryable } = envelope.data.error;
    throw new ArtifactBridgeError(code, message, retryable, command);
  }
  const parsed = schema.safeParse(envelope.data.data);
  if (!parsed.success) {
    throw new ArtifactContractError(command);
  }
  return parsed.data;
}

async function callNativeAsset<T>(
  command: string,
  request: ArtifactParams,
  schema: z.ZodType<T>,
): Promise<T> {
  const response = NativeResultSchema.safeParse(await invoke(command, request));
  if (!response.success) throw new ArtifactContractError(command);
  if (!response.data.ok) {
    throw new ArtifactBridgeError(
      response.data.error.code,
      response.data.error.message,
      response.data.error.retryable,
      response.data.error.command,
    );
  }
  const parsed = schema.safeParse(response.data.data);
  if (!parsed.success) throw new ArtifactContractError(command);
  return parsed.data;
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const source = Uint8Array.from(bytes);
  const digest = await globalThis.crypto.subtle.digest('SHA-256', source.buffer);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export const artifactBridge = {
  getRuntimeCapabilitySnapshot(): Promise<ArtifactRuntimeCapabilitySnapshot> {
    return callArtifact(
      'bridge_artifact_handshake',
      {},
      ArtifactRpcHandshakeCapabilitySnapshotSchema,
    );
  },

  list(request: ArtifactListRequest = {}): Promise<ArtifactListResult> {
    return callArtifact('bridge_artifact_list', { ...request }, ArtifactListWireSchema);
  },

  get(request: ArtifactGetRequest): Promise<ArtifactReadResult> {
    return callArtifact('bridge_artifact_get', { ...request }, ArtifactReadResultSchema);
  },

  create(request: ArtifactCreateRequest): Promise<ArtifactOperationResult> {
    return callArtifact(
      'bridge_artifact_create',
      { ...request },
      ArtifactOperationResultSchema,
      request.idempotencyKey,
    );
  },

  mutate(request: ArtifactMutationRequest): Promise<ArtifactOperationResult> {
    return callArtifact(
      'bridge_artifact_mutate',
      { ...request },
      ArtifactOperationResultSchema,
      request.idempotencyKey,
    );
  },

  patchSpreadsheetCells(request: SpreadsheetCellPatchRequest): Promise<ArtifactOperationResult> {
    return callArtifact(
      'bridge_artifact_spreadsheet_patch',
      { ...request },
      ArtifactOperationResultSchema,
      request.idempotencyKey,
    );
  },

  patchSlide(request: SlidePatchRequest): Promise<ArtifactOperationResult> {
    return callArtifact(
      'bridge_artifact_slides_patch',
      { ...request },
      ArtifactOperationResultSchema,
      request.idempotencyKey,
    );
  },

  proposeMutation(request: ArtifactMutationProposalRequest): Promise<ArtifactMutationProposalResult> {
    return callArtifact(
      'bridge_artifact_propose_mutation',
      { ...request },
      ArtifactMutationProposalResultSchema,
      request.idempotencyKey,
    );
  },

  applyProposal(request: {
    proposalId: string;
    expectedRevisionNumber: number;
    approvalId: string;
  }): Promise<ArtifactOperationResult> {
    return callArtifact(
      'bridge_artifact_apply_proposal',
      { ...request },
      ArtifactOperationResultSchema,
    );
  },

  history(request: ArtifactHistoryRequest): Promise<ArtifactHistoryResult> {
    return callArtifact('bridge_artifact_history', { ...request }, ArtifactHistoryWireSchema);
  },

  restore(request: ArtifactRestoreRequest): Promise<ArtifactOperationResult> {
    return callArtifact(
      'bridge_artifact_restore',
      { ...request },
      ArtifactOperationResultSchema,
      request.idempotencyKey,
    );
  },

  archive(request: ArtifactArchiveRequest): Promise<ArtifactOperationResult> {
    return callArtifact('bridge_artifact_archive', { ...request }, ArtifactOperationResultSchema);
  },

  duplicate(request: ArtifactDuplicateRequest): Promise<ArtifactOperationResult> {
    return callArtifact(
      'bridge_artifact_duplicate',
      { ...request },
      ArtifactOperationResultSchema,
      request.idempotencyKey,
    );
  },

  selectAsset(): Promise<ArtifactAssetSelectResult> {
    return callNativeAsset('bridge_artifact_asset_select', {}, ArtifactAssetSelectResultSchema);
  },

  importAsset(request: ArtifactAssetImportRequest): Promise<ArtifactAssetImportResult> {
    return callNativeAsset(
      'bridge_artifact_asset_import',
      { request: { ...request } },
      ArtifactAssetImportResultSchema,
    );
  },

  getAsset(assetId: string): Promise<ArtifactAssetReadResult> {
    return callArtifact(
      'bridge_artifact_asset_get',
      { assetId },
      ArtifactAssetReadResultSchema,
    );
  },

  importEvidence(request: ArtifactEvidenceImportRequest): Promise<ArtifactOperationResult> {
    return callArtifact(
      'bridge_artifact_import_evidence',
      { ...request },
      ArtifactOperationResultSchema,
      request.idempotencyKey,
    );
  },

  submitForm(request: ArtifactFormSubmissionRequest): Promise<ArtifactFormSubmissionResult> {
    return callArtifact(
      'bridge_artifact_form_submit',
      { ...request },
      ArtifactFormSubmissionResultSchema,
      request.idempotencyKey,
    );
  },

  beginExport(request: ArtifactExportBeginRequest): Promise<ArtifactExportBeginResult> {
    return callNativeExport('bridge_artifact_export_begin', { ...request }, ArtifactExportBeginResultSchema);
  },

  async commitExport(ticket: string, bytes: Uint8Array): Promise<ArtifactExportResult> {
    return callNativeExport(
      'bridge_artifact_export_commit',
      { ticket, bytes: Array.from(bytes), sha256: await sha256Hex(bytes) },
      ArtifactExportResultSchema,
    );
  },

  async cancelExport(ticket: string): Promise<void> {
    await callNativeExport(
      'bridge_artifact_export_cancel',
      { ticket },
      ArtifactExportCancelResultSchema,
    );
  },
};

export type ArtifactBridge = typeof artifactBridge;
