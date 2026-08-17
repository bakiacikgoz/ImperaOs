import { invoke } from '@tauri-apps/api/core';
import { z } from 'zod';

const envelope = z.discriminatedUnion('ok', [
  z.object({ ok: z.literal(true), data: z.unknown(), error: z.null() }).strict(),
  z.object({ ok: z.literal(false), data: z.null(), error: z.object({ code: z.string(), message: z.string(), retryable: z.boolean() }).passthrough() }).strict(),
]);
const project = z.object({
  projectId: z.string(), workspaceId: z.string(), title: z.string(),
  rootRef: z.string().default(''), rootDisplayName: z.string().default(''),
  status: z.enum(['active', 'archived']), pinned: z.boolean().default(false),
  manualOrder: z.number().int().nonnegative().default(0),
  createdAtUtc: z.string(), updatedAtUtc: z.string(), archivedAtUtc: z.string().nullable().default(null),
}).strict();
const taskRuntime = z.object({
  reasoningEffort: z.enum(['low', 'medium', 'high', 'very_high']).default('medium'),
  speedProfile: z.enum(['standard', 'fast']).default('standard'),
  approvalProfile: z.enum(['always_ask', 'risk_based', 'policy_automatic']).default('risk_based'),
}).strict();
const task = z.object({ taskId: z.string(), workspaceId: z.string(), projectId: z.string(), title: z.string(), status: z.enum(['draft', 'active', 'awaiting_approval', 'completed', 'failed', 'cancelled', 'archived']), priority: z.number().int().nonnegative().default(0), pinned: z.boolean().default(false), manualOrder: z.number().int().nonnegative().default(0), ...taskRuntime.shape, assistantSessionId: z.string().nullable(), assistantTurnId: z.string().nullable(), teamJobId: z.string().nullable(), createdAtUtc: z.string(), updatedAtUtc: z.string(), archivedAtUtc: z.string().nullable().default(null) }).strict();
const taskLink = z.object({ linkId: z.string(), workspaceId: z.string(), taskId: z.string(), targetType: z.enum(['artifact', 'approval', 'team_job', 'run']), targetId: z.string(), createdAtUtc: z.string() }).strict();
const folderSelection = z.object({
  cancelled: z.boolean(), folderTicket: z.string().nullable(), displayName: z.string().nullable(),
}).strict();

export type ProductWorkspaceTask = z.infer<typeof task>;
export type ProductWorkspaceProject = z.infer<typeof project>;
export type ProductTaskRuntimeOptions = z.infer<typeof taskRuntime>;
export type ProductTaskLink = z.infer<typeof taskLink>;

export class ProductWorkspaceError extends Error {
  readonly code: string;
  readonly retryable: boolean;

  constructor(code: string, message: string, retryable: boolean, options?: ErrorOptions) {
    super(message, options);
    this.name = 'ProductWorkspaceError';
    this.code = code;
    this.retryable = retryable;
  }
}

async function invokeWorkspace(command: string, args: Record<string, unknown>): Promise<unknown> {
  try {
    return await invoke<unknown>(command, args);
  } catch (cause) {
    if (
      cause instanceof TypeError
      && /undefined.*invoke|invoke.*undefined/i.test(cause.message)
    ) {
      throw new ProductWorkspaceError(
        'PRODUCT_RUNTIME_UNAVAILABLE',
        'Workspace data requires the ImperaOS desktop runtime. Open this screen in the desktop app.',
        false,
        { cause },
      );
    }
    throw cause;
  }
}

export class ProductWorkspaceClient {
  private async call<T>(command: string, params: Record<string, unknown>, schema: z.ZodType<T>, idempotencyKey: string | null = null): Promise<T> {
    const boundParams = idempotencyKey ? { ...params, idempotencyKey } : params;
    const raw = await invokeWorkspace(command, { payload: { params: boundParams, idempotencyKey, timeoutMs: 15_000 } });
    const parsed = envelope.parse(raw);
    if (!parsed.ok) throw new ProductWorkspaceError(
      parsed.error.code,
      parsed.error.message,
      parsed.error.retryable,
    );
    return schema.parse(parsed.data);
  }

  private async nativeCall<T>(command: string, args: Record<string, unknown>, schema: z.ZodType<T>): Promise<T> {
    const raw = await invokeWorkspace(command, args);
    const parsed = envelope.parse(raw);
    if (!parsed.ok) throw new ProductWorkspaceError(
      parsed.error.code,
      parsed.error.message,
      parsed.error.retryable,
    );
    return schema.parse(parsed.data);
  }

  listProjects(options: { cursor?: string; limit?: number; status?: 'active' | 'archived'; sort?: 'updated_desc' | 'manual' | 'priority' } = {}) {
    return this.call('bridge_product_project_list', options, z.object({ projects: z.array(project), nextCursor: z.string().nullable().default(null) }).strict());
  }
  createProject(title: string) { return this.call('bridge_product_project_create', { title }, project, `project-${crypto.randomUUID()}`); }
  updateProject(projectId: string, changes: { pinned?: boolean; manualOrder?: number; name?: string }) {
    return this.call('bridge_product_project_update', { projectId, ...changes }, project, `project-update-${crypto.randomUUID()}`);
  }
  archiveProject(projectId: string, reason: string) {
    return this.call('bridge_product_project_archive', { projectId, reason }, project, `project-archive-${crypto.randomUUID()}`);
  }
  selectProjectFolder() {
    return this.nativeCall('bridge_product_project_folder_select', {}, folderSelection);
  }
  async registerProjectFromFolder(name?: string) {
    const selection = await this.selectProjectFolder();
    if (selection.cancelled || !selection.folderTicket || !selection.displayName) return null;
    const idempotencyKey = `project-register-${crypto.randomUUID()}`;
    return this.nativeCall('bridge_product_project_register', {
      request: {
        folderTicket: selection.folderTicket,
        name: name?.trim() || selection.displayName,
        idempotencyKey,
      },
    }, project);
  }
  async getOrCreateProject(title: string) {
    const { projects } = await this.listProjects();
    return projects.find((project) => project.title === title && project.status !== 'archived')
      ?? this.createProject(title);
  }
  getTask(taskId: string) { return this.call('bridge_product_task_get', { taskId }, task); }
  listTasks(projectId: string) {
    return this.call('bridge_product_task_list', { projectId }, z.object({ tasks: z.array(task) }).strict());
  }
  createTask(projectId: string, title: string, assistantSessionId?: string, runtime?: ProductTaskRuntimeOptions) { return this.call('bridge_product_task_create', { projectId, title, assistantSessionId, runtime }, task, `task-${crypto.randomUUID()}`); }
  updateTask(taskId: string, changes: { status?: ProductWorkspaceTask['status']; priority?: number; pinned?: boolean; manualOrder?: number; runtime?: Partial<ProductTaskRuntimeOptions> }) {
    return this.call('bridge_product_task_update', { taskId, ...changes }, task, `task-update-${crypto.randomUUID()}`);
  }
  archiveTask(taskId: string, reason: string) {
    return this.call('bridge_product_task_archive', { taskId, reason }, task, `task-archive-${crypto.randomUUID()}`);
  }
  addMessage(taskId: string, role: 'user' | 'assistant' | 'system', body: string) {
    return this.call('bridge_product_task_message_add', { taskId, role, body }, z.object({ messageId: z.string(), workspaceId: z.string(), taskId: z.string(), role: z.string(), body: z.string(), createdAtUtc: z.string() }).strict(), `message-${crypto.randomUUID()}`);
  }
  addLink(taskId: string, targetType: ProductTaskLink['targetType'], targetId: string) {
    return this.call('bridge_product_task_link_add', { taskId, targetType, targetId }, taskLink, `task-link-${crypto.randomUUID()}`);
  }
  listLinks(taskId: string) {
    return this.call('bridge_product_task_link_list', { taskId }, z.object({ links: z.array(taskLink) }).strict());
  }
  listMessages(taskId: string) {
    const message = z.object({ messageId: z.string(), workspaceId: z.string(), taskId: z.string(), role: z.enum(['user', 'assistant', 'system']), body: z.string(), createdAtUtc: z.string() }).strict();
    return this.call('bridge_product_task_message_list', { taskId }, z.object({ messages: z.array(message) }).strict());
  }
}

export const productWorkspaceClient = new ProductWorkspaceClient();
