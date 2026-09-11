import type { CoverageLine } from '../shell/metaStore';

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
  /**
   * One line per thing being counted, each with the noun the route reported.
   *
   * A list rather than a single ratio, because a page can hold panels that
   * count different things and no single ratio is true of both. The noun is
   * required rather than defaulted: `accounts` was correct on most screens and
   * silently wrong on the ones counting workspaces, and a wrong noun in a
   * coverage statement is a wrong claim about the estate.
   */
  readonly coverage: readonly CoverageLine[];
}

export function CoverageBanner({ coverage }: CoverageBannerProps) {
  const partial = coverage.some((line) => line.visible < line.total);
  const said =
    coverage.length === 0
      ? // Nothing has reported yet. Not a claim of full coverage, which is what
        // an empty banner would read as.
        'Coverage not yet reported'
      : coverage
          .map((line) =>
            line.visible < line.total
              ? `${String(line.visible)} of ${String(line.total)} ${line.unit}`
              : `all ${String(line.total)} ${line.unit}`,
          )
          .join(', ');
  return (
    <div
      data-testid="coverage"
      data-partial={partial ? 'true' : 'false'}
      role="status"
      className={partial ? 'meter-stale' : undefined}
    >
      {coverage.length === 0 ? said : `Showing ${said}`}
    </div>
  );
}
