import type { ApiCommitmentDay } from '../api/types';
import { commitmentTypeName } from '../components/displayNames';
import type { Stacked } from './exploreSeries';

/**
 * The daily commitment figures, TASK-P8-013, as the three shapes the Commitments screen draws.
 *
 * Both stacks are money and each stacks to a total that means something: what was committed,
 * and what could have been covered. Percentages are never stacked, because two utilizations
 * added together are a number that measures nothing; they go to the heatmap, one row each.
 */

function daysIn(rows: readonly ApiCommitmentDay[]): readonly string[] {
  return [...new Set(rows.map((row) => row.day))].sort();
}

function sumOn(
  rows: readonly ApiCommitmentDay[],
  day: string,
  pick: (row: ApiCommitmentDay) => number,
): number {
  return rows.filter((row) => row.day === day).reduce((sum, row) => sum + pick(row), 0);
}

/** What every commitment obliged each day, as used and paid for and unused. */
export function committedEachDay(rows: readonly ApiCommitmentDay[]): Stacked {
  const periods = daysIn(rows);
  return {
    periods,
    series: [
      {
        key: 'used',
        label: 'Used',
        values: periods.map((day) => sumOn(rows, day, (row) => Number(row.used))),
      },
      {
        key: 'unused',
        label: 'Paid for and unused',
        values: periods.map((day) =>
          sumOn(rows, day, (row) => Number(row.committed) - Number(row.used)),
        ),
      },
    ],
  };
}

/** Spend a commitment could have covered each day, as covered and left on demand. */
export function coverageEachDay(rows: readonly ApiCommitmentDay[]): Stacked {
  const periods = daysIn(rows);
  return {
    periods,
    series: [
      {
        key: 'covered',
        label: 'Covered',
        values: periods.map((day) => sumOn(rows, day, (row) => Number(row.covered_spend))),
      },
      {
        key: 'on-demand',
        label: 'Left on demand',
        values: periods.map((day) =>
          sumOn(rows, day, (row) => Number(row.eligible_spend) - Number(row.covered_spend)),
        ),
      },
    ],
  };
}

export interface DayGrid {
  readonly rows: readonly string[];
  readonly columns: readonly string[];
  /** Percent, null where a kind had nothing to divide by that day or no row at all. */
  readonly values: readonly (readonly (number | null)[])[];
}

/** A day as the heatmap's columns name it: 6 Oct. */
function dayLabel(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  });
}

/** Each kind's utilization and coverage per day, in percent, one heatmap row each. */
export function dayByDay(rows: readonly ApiCommitmentDay[]): DayGrid {
  const periods = daysIn(rows);
  const kinds = [...new Set(rows.map((row) => row.commitment_type))].sort();
  const lines = kinds.flatMap((kind) => [
    {
      label: `${commitmentTypeName(kind)} utilization`,
      kind,
      pick: (row: ApiCommitmentDay) => row.utilization,
    },
    {
      label: `${commitmentTypeName(kind)} coverage`,
      kind,
      pick: (row: ApiCommitmentDay) => row.coverage,
    },
  ]);
  return {
    rows: lines.map((line) => line.label),
    columns: periods.map(dayLabel),
    values: lines.map((line) =>
      periods.map((day) => {
        const found = rows.find((row) => row.day === day && row.commitment_type === line.kind);
        const fraction = found === undefined ? null : line.pick(found);
        return fraction === null ? null : Number(fraction) * 100;
      }),
    ),
  };
}
