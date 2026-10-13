import type { ApiMeta } from '../api/types';

/**
 * How the commitments panels speak of time, TASK-P14-009. Kept apart from the components so each
 * panel file exports components only.
 */

/** `2026-10-01` as `October 2026`, the way a billing month is spoken. */
export function monthName(period: string): string {
  return new Date(`${period}T00:00:00Z`).toLocaleDateString('en-GB', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

/** `2026-11-03T00:00:00Z`, or `2026-11-03`, as `3 November 2026`. */
export function dayName(stamp: string): string {
  const instant = stamp.length === 10 ? `${stamp}T00:00:00Z` : stamp;
  return new Date(instant).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

/** A Savings Plans program as a reader knows it: the API's `EC2Instance` is `EC2 Instance`. */
export function programName(program: string): string {
  return program === 'EC2Instance' ? 'EC2 Instance' : program;
}

/**
 * A decimal the API sends with its column's places, `2.0000`, as a reader reads it, `2`. ISS-298.
 */
export function plainNumber(value: string): string {
  return String(Number(value));
}

/** An envelope's two timestamps, constraint 10, as a figure's freshness. */
export function freshnessOf(meta: ApiMeta | undefined) {
  return {
    asOf: new Date(meta?.as_of ?? 0),
    collectedAt: new Date(meta?.collected_at ?? 0),
  };
}
