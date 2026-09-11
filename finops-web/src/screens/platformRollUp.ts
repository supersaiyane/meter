import type { PlatformCost } from '../api/types';

/**
 * Rolling the daily rows up per module, with a thirty day shape.
 *
 * A module is only as fresh as its stalest day, so the oldest timestamp wins
 * rather than the newest. Taking the newest would let one recently collected
 * day make a month of older figures look current.
 */

export interface ModuleRow {
  readonly module: string;
  readonly total: number;
  readonly days: readonly number[];
  readonly asOf: string;
  readonly collectedAt: string;
}

/** Thirty days, no more. The sparkline answers "is this going up" and nothing else. */
export const WINDOW_DAYS = 30;

export function rollUp(rows: readonly PlatformCost[]): ModuleRow[] {
  const byModule = new Map<
    string,
    { total: number; byDay: Map<string, number>; asOf: string; collectedAt: string }
  >();
  for (const row of rows) {
    const amount = Number(row.amortized_cost);
    const entry = byModule.get(row.module) ?? {
      total: 0,
      byDay: new Map<string, number>(),
      asOf: row.as_of,
      collectedAt: row.collected_at,
    };
    entry.total += amount;
    entry.byDay.set(row.day, (entry.byDay.get(row.day) ?? 0) + amount);
    // The oldest, because a module is only as fresh as its stalest day.
    entry.asOf = entry.asOf < row.as_of ? entry.asOf : row.as_of;
    entry.collectedAt =
      entry.collectedAt < row.collected_at ? entry.collectedAt : row.collected_at;
    byModule.set(row.module, entry);
  }
  return [...byModule.entries()]
    .map(([module, entry]) => ({
      module,
      total: entry.total,
      days: [...entry.byDay.keys()]
        .sort()
        .slice(-WINDOW_DAYS)
        .map((day) => entry.byDay.get(day) ?? 0),
      asOf: entry.asOf,
      collectedAt: entry.collectedAt,
    }))
    .sort((left, right) => right.total - left.total);
}

export interface GrandTotal {
  readonly total: number;
  readonly asOf: string;
  readonly collectedAt: string;
}

/**
 * One figure across every module, for the front page.
 *
 * The oldest timestamp wins here for the same reason it wins per module: a
 * total is only as fresh as its stalest part. Null when there is nothing to
 * total, so the caller renders an absence rather than a confident zero.
 */
export function grandTotal(rows: readonly ModuleRow[]): GrandTotal | null {
  const first = rows[0];
  if (first === undefined) {
    return null;
  }
  return {
    total: rows.reduce((sum, row) => sum + row.total, 0),
    asOf: rows.reduce((oldest, row) => (row.asOf < oldest ? row.asOf : oldest), first.asOf),
    collectedAt: rows.reduce(
      (oldest, row) => (row.collectedAt < oldest ? row.collectedAt : oldest),
      first.collectedAt,
    ),
  };
}
