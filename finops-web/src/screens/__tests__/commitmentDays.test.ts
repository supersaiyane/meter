import { describe, expect, it } from 'vitest';

import type { ApiCommitmentDay } from '../../api/types';
import { committedEachDay, coverageEachDay, dayByDay } from '../commitmentDays';

/** One kind on one day: committed, used, eligible and covered, with the route's fractions. */
function day(
  commitmentType: string,
  on: string,
  [committed, used, eligible, covered]: readonly [number, number, number, number],
): ApiCommitmentDay {
  return {
    commitment_type: commitmentType,
    day: on,
    committed: String(committed),
    used: String(used),
    utilization: committed === 0 ? null : String(used / committed),
    eligible_spend: String(eligible),
    covered_spend: String(covered),
    coverage: eligible === 0 ? null : String(covered / eligible),
    as_of: `${on}T23:59:59Z`,
    collected_at: `${on}T23:59:59Z`,
  };
}

const ROWS: readonly ApiCommitmentDay[] = [
  day('SavingsPlan', '2026-10-01', [10, 8, 40, 8]),
  day('ReservedInstance', '2026-10-01', [6, 3, 10, 3]),
  day('SavingsPlan', '2026-10-02', [10, 10, 30, 10]),
  // No reservation on the second day, and a day with nothing committed to divide by.
  day('ReservedInstance', '2026-10-03', [0, 0, 12, 0]),
];

describe('the daily commitment shapes', () => {
  it('stacks each day to what was committed, used under unused', () => {
    const shape = committedEachDay(ROWS);
    expect(shape.periods).toEqual(['2026-10-01', '2026-10-02', '2026-10-03']);
    expect(shape.series.map((one) => [one.label, one.values])).toEqual([
      ['Used', [11, 10, 0]],
      ['Paid for and unused', [5, 0, 0]],
    ]);
  });

  it('stacks each day to what could have been covered, covered under on demand', () => {
    expect(coverageEachDay(ROWS).series.map((one) => one.values)).toEqual([
      [11, 10, 0],
      [39, 20, 12],
    ]);
  });

  it('puts each kind utilization and coverage on its own heatmap row, never added', () => {
    const grid = dayByDay(ROWS);
    expect(grid.rows).toEqual([
      'Reserved Instance utilization',
      'Reserved Instance coverage',
      'Savings Plan utilization',
      'Savings Plan coverage',
    ]);
    expect(grid.columns).toEqual(['1 Oct', '2 Oct', '3 Oct']);
    // No reservation row on the 2nd, and nothing committed to divide by on the 3rd.
    expect(grid.values[0]).toEqual([50, null, null]);
    expect(grid.values[1]).toEqual([30, null, 0]);
    expect(grid.values[2]).toEqual([80, 100, null]);
  });
});
