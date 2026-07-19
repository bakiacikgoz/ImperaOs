import type { ButtonHTMLAttributes, HTMLAttributes, PropsWithChildren } from 'react';

function classes(...values: Array<string | undefined | false>): string {
  return values.filter(Boolean).join(' ');
}

export type ArtifactButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'destructive';
};

export function ArtifactButton({
  variant = 'secondary',
  className,
  type = 'button',
  ...props
}: ArtifactButtonProps) {
  return (
    <button
      type={type}
      className={classes('aw-button', `aw-button--${variant}`, className)}
      {...props}
    />
  );
}

export type ArtifactPanelProps = PropsWithChildren<HTMLAttributes<HTMLElement>>;

export function ArtifactPanel({ className, children, ...props }: ArtifactPanelProps) {
  return (
    <section role="region" className={classes('aw-panel', className)} {...props}>
      {children}
    </section>
  );
}

export type ArtifactBadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: 'neutral' | 'success' | 'warning' | 'error' | 'info';
};

export function ArtifactBadge({ tone = 'neutral', className, ...props }: ArtifactBadgeProps) {
  return <span className={classes('aw-badge', `aw-badge--${tone}`, className)} {...props} />;
}
