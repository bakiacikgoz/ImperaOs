import { asControlPlaneAgentList } from '../../controlPlaneMappers';
import type { UiLocale } from '../../i18n';
import { CodeToken, StatusBadge } from '../primitives/Token';

const copy = {
  en: {
    kicker: 'Registry',
    title: 'Agents',
    lead: 'Governed agent and workflow specifications.',
    registry: 'Registry',
    policy: 'Policy',
    evidence: 'Evidence',
    noRegisteredAgents: 'No registered agents',
    registerWithCli: 'Register an agent spec with the control-plane CLI.',
    governedActions: 'Governed actions',
    externalGateway: 'External gateway',
    configured: 'configured',
    notRegistered: 'not registered',
    approvalBoundary: 'Approval boundary',
    externalWritesGated: 'external writes gated',
    evidenceStatus: 'Evidence status',
    signedPackRequired: 'signed pack required',
  },
  tr: {
    kicker: 'Registry',
    title: 'Agentlar',
    lead: 'Yönetişimli agent ve workflow spesifikasyonları.',
    registry: 'Registry',
    policy: 'Policy',
    evidence: 'Evidence',
    noRegisteredAgents: 'Kayıtlı agent yok',
    registerWithCli: 'Control-plane CLI ile bir agent spec kaydedin.',
    governedActions: 'Yönetişimli aksiyonlar',
    externalGateway: 'Harici gateway',
    configured: 'yapılandırıldı',
    notRegistered: 'kayıtlı değil',
    approvalBoundary: 'Onay sınırı',
    externalWritesGated: 'harici yazmalar onaya bağlı',
    evidenceStatus: 'Evidence durumu',
    signedPackRequired: 'imzalı pack gerekli',
  },
} satisfies Record<UiLocale, Record<string, string>>;

export function AgentRegistryView({
  agents,
  locale = 'en',
  selectedAgentId,
  onSelectAgent,
}: {
  agents: unknown;
  locale?: UiLocale;
  selectedAgentId?: string | null;
  onSelectAgent?: (agentId: string) => void;
}) {
  const list = asControlPlaneAgentList(agents);
  const text = copy[locale];
  const selectedAgent = list.agents.find((agent) => agent.agent_id === selectedAgentId) ?? list.agents[0] ?? null;
  return (
    <section className="workspace" data-testid="page-primary-region">
      <div className="workspace-header">
        <div>
          <p className="workspace-kicker">{text.kicker}</p>
          <h2>{text.title}</h2>
          <p className="workspace-lead">{text.lead}</p>
        </div>
      </div>
      <div className="section-grid two-up">
        <article className="page-card">
          <h3>{text.registry}</h3>
          <div className="run-list">
            {list.agents.map((agent) => {
              const content = <>
                <div className="run-list-main">
                  <strong>{agent.display_name || agent.agent_id}</strong>
                  <div className="run-list-meta">
                    <CodeToken>{agent.agent_type}</CodeToken>
                    <CodeToken>{agent.runtime_kind}</CodeToken>
                    <span>{`${text.policy} ${agent.policy_pack_id}`}</span>
                    <span>{agent.risk_profile}</span>
                    <span>{`${text.evidence} ${agent.last_evidence_status}`}</span>
                  </div>
                </div>
                <StatusBadge tone={agent.status === 'active' ? 'success' : 'warning'}>
                  {`${agent.status} / ${agent.readiness}`}
                </StatusBadge>
              </>;
              return onSelectAgent ? <button type="button" className="run-list-item" key={agent.agent_id} aria-pressed={selectedAgent?.agent_id === agent.agent_id} onClick={() => onSelectAgent(agent.agent_id)}>{content}</button> : <article className="run-list-item" key={agent.agent_id}>{content}</article>;
            })}
            {list.agents.length === 0 ? (
              <article className="run-list-item">
                <div className="run-list-main">
                  <strong>{text.noRegisteredAgents}</strong>
                  <span>{text.registerWithCli}</span>
                </div>
                <CodeToken>imperaos control-plane agent register</CodeToken>
              </article>
            ) : null}
          </div>
        </article>
        <article className="page-card">
          <h3>{selectedAgent ? `${selectedAgent.display_name || selectedAgent.agent_id}` : text.governedActions}</h3>
          {selectedAgent ? <div className="metric-list">
            <div className="metric-row"><span>Agent ID</span><strong>{selectedAgent.agent_id}</strong></div>
            <div className="metric-row"><span>Runtime</span><strong>{selectedAgent.runtime_kind}</strong></div>
            <div className="metric-row"><span>{text.policy}</span><strong>{selectedAgent.policy_pack_id}</strong></div>
            <div className="metric-row"><span>{text.evidence}</span><strong>{selectedAgent.last_evidence_status}</strong></div>
          </div> : null}
          <h3>{text.governedActions}</h3>
          <div className="metric-list">
            <div className="metric-row">
              <span>{text.externalGateway}</span>
              <strong>{list.agents.some((agent) => agent.agent_type.startsWith('external')) ? text.configured : text.notRegistered}</strong>
            </div>
            <div className="metric-row">
              <span>{text.approvalBoundary}</span>
              <strong>{text.externalWritesGated}</strong>
            </div>
            <div className="metric-row">
              <span>{text.evidenceStatus}</span>
              <strong>{text.signedPackRequired}</strong>
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}
