import type { AssistantArtifactProposalPart } from '../../assistant/assistantTypes';
import { Button } from '../primitives/Button';

function proposalStatusLabel(status: AssistantArtifactProposalPart['status']): string {
  switch (status) {
    case 'pending': return 'Awaiting approval';
    case 'approved': return 'Approved to apply';
    case 'applied': return 'Applied';
    case 'rejected': return 'Rejected';
    case 'failed': return 'Needs review';
  }
}

export function ArtifactProposalCard({
  proposal,
  disabled,
  disabledReason,
  onReview,
  onApprove,
  onReject,
  onApply,
  risk,
}: {
  proposal: AssistantArtifactProposalPart;
  disabled: boolean;
  disabledReason: string;
  onReview: (approvalId: string) => void;
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string) => void;
  onApply: (proposal: AssistantArtifactProposalPart) => void;
  risk?: 'low' | 'medium' | 'high';
}) {
  const decisionDisabled = disabled || proposal.status !== 'pending';
  const executeDisabled = disabled || proposal.status !== 'approved';

  return (
    <section className="assistant-artifact-proposal" aria-label="Artifact proposal">
      <div className="assistant-artifact-proposal-heading">
        <div>
          <strong>{proposal.title}</strong>
          <p>{proposal.kind} change proposal</p>
        </div>
        <span className={`assistant-artifact-proposal-status status-${proposal.status}`}>{proposalStatusLabel(proposal.status)}</span>
      </div>
      <p>{proposal.summary}</p>
      <dl className="assistant-artifact-proposal-details" aria-label="Proposal safeguards">
        <div>
          <dt>Approval</dt>
          <dd>{proposal.status === 'pending' ? 'Approval required' : proposalStatusLabel(proposal.status)}</dd>
        </div>
        <div>
          <dt>Base revision</dt>
          <dd>Revision {proposal.baseRevisionNumber}</dd>
        </div>
        <div>
          <dt>Scope</dt>
          <dd>Scoped artifact change</dd>
        </div>
        <div>
          <dt>Risk</dt>
          <dd>{risk ? `${risk[0].toUpperCase()}${risk.slice(1)} risk` : 'Risk review required'}</dd>
        </div>
      </dl>
      {proposal.error ? <p role="alert" className="assistant-error-text">{proposal.error.slice(0, 500)}</p> : null}
      <div className="assistant-artifact-proposal-actions">
        <Button variant="secondary" onClick={() => onReview(proposal.approvalId)}>
          Review proposal approval
        </Button>
        {proposal.status === 'pending' ? (
          <>
            <Button disabled={decisionDisabled} title={decisionDisabled ? disabledReason : undefined} onClick={() => onApprove(proposal.approvalId)}>
              Approve proposal
            </Button>
            <Button variant="danger" disabled={decisionDisabled} title={decisionDisabled ? disabledReason : undefined} onClick={() => onReject(proposal.approvalId)}>
              Reject proposal
            </Button>
          </>
        ) : null}
        {proposal.status === 'approved' ? (
          <Button disabled={executeDisabled} title={executeDisabled ? disabledReason : undefined} onClick={() => onApply(proposal)}>
            Apply approved proposal
          </Button>
        ) : null}
      </div>
    </section>
  );
}
