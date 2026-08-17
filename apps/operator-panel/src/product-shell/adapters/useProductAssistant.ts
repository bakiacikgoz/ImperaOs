import { useCallback } from 'react';

import { useAssistantRuntimeSession } from '../../assistant/useAssistantRuntimeSession';
import { loadSettings } from '../../settings';
import type { ProductTask } from '../state/productShellStore';

/** Connects the new visual shell to the governed, existing assistant transport. */
export function useProductAssistant(task: ProductTask | undefined) {
  const settings = loadSettings();
  const getContext = useCallback(() => ({
    selectedRunId: '',
    selectedRunStatus: null,
    selectedRunEvents: [],
    selectedArtifacts: {},
    artifactContextRequest: task ? { taskId: task.id, taskTitle: task.title } : null,
    pendingApproval: null,
    systemHealth: null,
  }), [task]);
  return useAssistantRuntimeSession(settings, getContext, {
    initialSessionId: task?.assistantSessionId,
  });
}
