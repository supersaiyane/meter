import { formatAge, isStale, type Freshness } from './provenance';

/**
 * How old the data is, never when the page loaded.
 *
 * `asOf` is absolute because it is a claim about the world and has to be
 * precise. `collectedAt` is an age because "6 min ago" is read correctly and
 * "11:04:22Z" requires arithmetic from the reader.
 *
 * The words "live" and "just now" appear nowhere. Meter is never live: the cost
 * export refreshes at most three times a day and Cost Explorer runs about a day
 * behind, so either word would be a claim the product cannot support.
 */
export interface FreshnessIndicatorProps {
  readonly freshness: Freshness;
  readonly now?: Date;
}

export function FreshnessIndicator({ freshness, now = new Date() }: FreshnessIndicatorProps) {
  const stale = isStale(freshness, now);
  const ageSeconds = Math.max(0, (now.getTime() - freshness.collectedAt.getTime()) / 1000);
  const asOf = freshness.asOf.toISOString().replace('T', ' ').slice(0, 16);

  return (
    <span
      className={stale ? 'meter-stale' : undefined}
      data-testid="freshness"
      data-stale={stale ? 'true' : 'false'}
    >
      {' '}
      as of {asOf}, collected {formatAge(ageSeconds)}
    </span>
  );
}
