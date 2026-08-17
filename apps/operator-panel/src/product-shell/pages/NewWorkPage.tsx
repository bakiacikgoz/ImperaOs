import { useEffect, useState } from 'react';
import { Bug, Folder, Hammer, Radar, RefreshCw } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { useAssistantModels } from '../../assistant/useAssistantModels';
import type { AssistantProviderKind } from '../../assistant/modelDiscovery';
import type { AssistantComposerControls } from '../../assistant/assistantTypes';
import { AssistantComposer } from '../../components/assistant/AssistantComposer';
import {
  getAssistantRuntimeSettings,
  loadSettings,
  resolveLocale,
  saveSettings,
  type AssistantRuntimeSettings,
  type PanelSettings,
} from '../../settings';
import { useProductShellStore } from '../state/productShellStore';
import { productWorkspaceClient, type ProductWorkspaceProject } from '../adapters/productWorkspaceClient';

const suggestions = [
  {
    title: 'Kodlamayı keşfet ve anla',
    icon: Radar,
    tone: 'blue' as const,
    prompt: 'Bu kod tabanını keşfet ve mimarisini açıkla.',
  },
  {
    title: 'Yeni bir özellik, uygulama veya araç oluştur',
    icon: Hammer,
    tone: 'purple' as const,
    prompt: 'Yeni bir özellik, uygulama veya araç oluştur.',
  },
  {
    title: 'Kodu gözden geçir ve değişiklik öner',
    icon: RefreshCw,
    tone: 'green' as const,
    prompt: 'Kodu gözden geçir ve iyileştirme önerileri sun.',
  },
  {
    title: 'Sorunları ve hataları düzelt',
    icon: Bug,
    tone: 'orange' as const,
    prompt: 'Sorunları ve hataları bul ve düzelt.',
  },
];

export function NewWorkPage() {
  const upsertTasks = useProductShellStore((state) => state.upsertTasks);
  const upsertProjects = useProductShellStore((state) => state.upsertProjects);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState('');
  const [projects, setProjects] = useState<ProductWorkspaceProject[]>([]);
  const [projectId, setProjectId] = useState('');
  const [seedPrompt, setSeedPrompt] = useState('');
  const [settings, setSettings] = useState<PanelSettings>(() => loadSettings());
  const modelProvider = settings.assistantProvider.trim()
    ? settings.assistantProvider.trim() as AssistantProviderKind
    : 'all';
  const modelDiscovery = useAssistantModels({
    settings,
    profile: settings.profile,
    provider: modelProvider,
  });
  useEffect(() => {
    let active = true;
    void productWorkspaceClient.listProjects().then(({ projects }) => {
      if (!active) return;
      const activeProjects = projects.filter((project) => project.status !== 'archived');
      setProjects(activeProjects);
      upsertProjects(activeProjects.map((project) => ({
        projectId: project.projectId,
        rootRef: project.rootRef,
        rootDisplayName: project.rootDisplayName,
      })));
      const requestedProjectId = searchParams.get('project');
      if (requestedProjectId && activeProjects.some((project) => project.projectId === requestedProjectId)) {
        setProjectId(requestedProjectId);
      } else {
        setProjectId((current) => current || activeProjects[0]?.projectId || '');
      }
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : 'Could not load governed projects.');
    });
    return () => { active = false; };
  }, [searchParams, upsertProjects]);
  const updateRuntimeSettings = (next: Partial<AssistantRuntimeSettings>) => {
    setSettings((current) => {
      const updated = { ...current, ...next };
      saveSettings(updated);
      return updated;
    });
  };
  const start = async (
    message: string,
    runtimeSettings: AssistantRuntimeSettings,
    controls: AssistantComposerControls,
  ) => {
    try {
      setError('');
      const selectedProjectId = projectId || (await productWorkspaceClient.getOrCreateProject('Operator work')).projectId;
      const assistantSessionId = `product-session-${crypto.randomUUID()}`;
      const task = await productWorkspaceClient.createTask(selectedProjectId, message, assistantSessionId, {
        reasoningEffort: runtimeSettings.reasoningEffort ?? 'medium',
        speedProfile: runtimeSettings.speedProfile ?? 'standard',
        approvalProfile: runtimeSettings.approvalProfile ?? 'risk_based',
      });
      await productWorkspaceClient.addMessage(task.taskId, 'user', message);
      upsertTasks([{ id: task.taskId, projectId: task.projectId, title: task.title, createdAt: task.createdAtUtc, updatedAt: task.updatedAtUtc, status: task.status, priority: task.priority, pinned: task.pinned, manualOrder: task.manualOrder, archivedAt: task.archivedAtUtc, assistantSessionId: task.assistantSessionId ?? undefined, reasoningEffort: task.reasoningEffort, speedProfile: task.speedProfile, approvalProfile: task.approvalProfile }]);
      navigate(`/task/${task.taskId}`, { state: { initialMessage: message, runtimeSettings, controls } });
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create governed work.'); }
  };
  return (
    <main className="new-work-page codex-home">
      <div className="welcome-stage">
        <div className="welcome-hero">
          <div className="welcome-glyph" aria-hidden>
            <svg width="60" height="54" viewBox="0 0 40 36" fill="none">
              <path
                d="M13.5 28c-4.7 0-8.5-3.4-8.5-7.6 0-3.2 2-5.9 5-7.1C10.5 8.5 14.4 5.5 19.2 5.5c4.2 0 7.8 2.3 9.5 5.6 1 .2 1.9.5 2.7 1 3.2 1.7 5.1 4.7 5.1 8.1 0 5-4.3 9-9.6 9H13.5z"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinejoin="round"
              />
              <path d="M15 18.5h4.5M15 22h7.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              <path d="M15 15.5l2 2-2 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h1>Ne oluşturalım?</h1>
          <div className="suggestion-grid codex-suggestions">
            {suggestions.map(({ title, icon: SuggestionIcon, tone, prompt }) => (
              <button
                key={title}
                type="button"
                className={`suggestion-card tone-${tone}`}
                onClick={() => setSeedPrompt(prompt)}
              >
                <span className={`suggestion-icon tone-${tone}`}>
                  <SuggestionIcon size={18} strokeWidth={1.75} />
                </span>
                <span className="suggestion-title">{title}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="welcome-composer">
          {error ? <p className="product-home-error" role="alert">{error}</p> : null}
          <AssistantComposer
            label="Governed assistant"
            placeholder="İstediğin şeyi yap"
            sendLabel="Başlat"
            disabled={false}
            initialValue={seedPrompt}
            runtimeSettings={getAssistantRuntimeSettings(settings)}
            modelDiscovery={modelDiscovery}
            locale={resolveLocale(settings.locale)}
            variant="product"
            projectControl={(
              <label className="composer-chip product-project-control">
                <Folder size={14} strokeWidth={1.6} />
                <select
                  aria-label="Project"
                  value={projectId}
                  onChange={(event) => setProjectId(event.target.value)}
                >
                  <option value="">Yeni “Operator work” projesi oluştur</option>
                  {projects.map((project) => (
                    <option key={project.projectId} value={project.projectId}>{project.title}</option>
                  ))}
                </select>
              </label>
            )}
            onRuntimeSettingsChange={updateRuntimeSettings}
            onSend={(message, runtimeSettings, controls) => void start(message, runtimeSettings, controls)}
          />
        </div>
      </div>
    </main>
  );
}
