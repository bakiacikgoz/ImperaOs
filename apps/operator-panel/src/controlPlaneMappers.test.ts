import { describe, expect, it } from 'vitest';

import { asControlPlaneAgentList } from './controlPlaneMappers';

describe('control-plane agent mapper', () => {
  it('maps registry v2 external agent status fields', () => {
    const list = asControlPlaneAgentList({
      agents: [
        {
          agent_id: 'external-agent',
          display_name: 'External Gateway Agent',
          runtime_kind: 'external_stdio',
          agent_type: 'external_stdio',
          status: 'registered',
          readiness: 'policy_simulated',
          owner_team: 'platform-security',
          policy_pack_id: 'enterprise_default',
          risk_profile: 'guarded',
          last_run_id: 'cp-ext-run-preview',
          last_evidence_pack_id: null,
          last_evidence_status: 'missing',
        },
      ],
    });

    expect(list.agents[0].agent_type).toBe('external_stdio');
    expect(list.agents[0].policy_pack_id).toBe('enterprise_default');
    expect(list.agents[0].risk_profile).toBe('guarded');
    expect(list.agents[0].last_evidence_status).toBe('missing');
  });

  it('maps the canonical ImperaOS team runtime kind with safe defaults', () => {
    const list = asControlPlaneAgentList({
      agents: [{ agent_id: 'governed-ops', runtime_kind: 'imperaos_team' }],
    });

    expect(list.agents[0].runtime_kind).toBe('imperaos_team');
    expect(list.agents[0].agent_type).toBe('internal');
    expect(list.agents[0].policy_pack_id).toBe('active-runtime-policy');
    expect(list.agents[0].risk_profile).toBe('guarded');
    expect(list.agents[0].last_evidence_status).toBe('missing');
  });
});
