/**
 * Persistent, never a toast, never dismissible.
 *
 * A user seeing 42 of 310 accounts must not be able to forget it. A banner gets
 * dismissed and the condition does not go away with it, so there is no close
 * button here and no timer.
 *
 * Complete coverage says so out loud. The absence of a warning is not
 * confirmation, and a reader needs confirmation before treating a total as a
 * total.
 */
export interface CoverageBannerProps {
  readonly visible: number;
  readonly total: number;
}

export function CoverageBanner({ visible, total }: CoverageBannerProps) {
  const partial = visible < total;
  return (
    <div
      data-testid="coverage"
      data-partial={partial ? 'true' : 'false'}
      role="status"
      className={partial ? 'meter-stale' : undefined}
    >
      {partial
        ? `Showing ${String(visible)} of ${String(total)} accounts`
        : `Showing all ${String(total)} accounts`}
    </div>
  );
}
