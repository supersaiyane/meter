import type { ApiRealizedSaving } from '../api/types';
import type { Stacked } from './exploreSeries';

/** The verdict that means the bill fell at least as fast as the usage did. */
export const VERIFIED = 'VERIFIED';

/**
 * Verified savings accumulated by the day each check closed: each verified recommendation's
 * monthly saving, cost before less cost after as the domain defines it, added on the day its
 * after window ended. Verified only, because the screen never adds verdicts together and an
 * inconclusive fall is not a saving.
 */
export function verifiedCumulative(rows: readonly ApiRealizedSaving[]): Stacked {
  const verified = rows
    .filter((row) => row.verdict === VERIFIED)
    .map((row) => ({
      day: row.window_after_end,
      saved: Number(row.cost_before) - Number(row.cost_after),
    }));
  const days = [...new Set(verified.map((one) => one.day))].sort();
  const onDay = days.map((day) =>
    verified.filter((one) => one.day === day).reduce((sum, one) => sum + one.saved, 0),
  );
  const running = onDay.reduce<readonly number[]>(
    (totals, value) => [...totals, (totals[totals.length - 1] ?? 0) + value],
    [],
  );
  return days.length === 0
    ? { periods: [], series: [] }
    : { periods: days, series: [{ key: VERIFIED, label: 'Verified', values: running }] };
}
