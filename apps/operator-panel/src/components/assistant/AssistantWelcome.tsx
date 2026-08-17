import { Icon } from '../primitives/Icon';
import { PRODUCT_IDENTITY } from '../../productIdentity';

export function AssistantWelcome({
  title,
  subtitle,
  badgeLabel,
  readOnlyByDefault,
}: {
  title: string;
  subtitle: string;
  badgeLabel: string;
  readOnlyByDefault: string;
}) {
  const brandName = PRODUCT_IDENTITY.displayName;
  const brandIndex = title.indexOf(brandName);
  const highlightedTitle =
    brandIndex >= 0 ? (
      <>
        {title.slice(0, brandIndex)}
        <span>{brandName}</span>
        {title.slice(brandIndex + brandName.length)}
      </>
    ) : (
      title
    );

  return (
    <div className="assistant-welcome-card">
      <div className="assistant-hero-line" aria-hidden="true" />
      <div className="assistant-hero-mark" aria-hidden="true">
        <Icon name="sparkle" />
      </div>
      <div className="assistant-welcome-copy">
        <h2 aria-label={title}>{highlightedTitle}</h2>
        <p>{subtitle}</p>
        <div className="assistant-welcome-chips" aria-label={badgeLabel}>
          <span className="assistant-chip-success">
            <Icon name="shield" /> Policy-aware
          </span>
          <span>
            <Icon name="approval" /> {readOnlyByDefault}
          </span>
          <span className="assistant-chip-warning">
            <Icon name="check" /> Approval protected
          </span>
        </div>
      </div>
    </div>
  );
}
