import type { ApiExplore } from '../api/types';
import { EXPLORER_FILTERS } from '../shell/sections';
import { apiQuery, type ExploreChange, type ExploreValues } from './exploreModel';

/**
 * Cost Explorer views that other screens chart, FEAT-065, and their points as stacked series.
 *
 * A screen that draws spend over time asks the Explorer's route exactly as the Explorer does, so
 * the chart and the Explorer share one cached answer for one view and cannot disagree.
 */

export const DAY_MS = 86_400_000;

/** Every Cost Explorer key, blank, which is the Explorer's own default view. */
const BLANK = Object.fromEntries(EXPLORER_FILTERS.map((key) => [key, ''])) as ExploreValues;

/**
 * A Cost Explorer view written as the Explorer writes its own query, so a chart on another screen
 * and the Explorer share one cached answer, and the chart cannot disagree with the screen it
 * links to.
 */
export function exploreQuery(changes: ExploreChange = {}): string {
  return apiQuery({ ...BLANK, ...changes });
}

/** The last `count` days ending on `today`, in the form the Explorer's custom period takes. */
export function lastDays(
  count: number,
  today: Date,
): { readonly start: string; readonly end: string } {
  const end = today.toISOString().slice(0, 10);
  const start = new Date(today.getTime() - (count - 1) * DAY_MS).toISOString().slice(0, 10);
  return { start, end };
}

export interface StackedSeries {
  readonly key: string;
  readonly label: string;
  readonly values: readonly (number | null)[];
}

export interface Stacked {
  readonly periods: readonly string[];
  readonly series: readonly StackedSeries[];
}

/** The key a point with no series is counted under. The route's null series is everything
 * past the named ones, so it always belongs to the rest and is never a series of its own. */
const EVERYTHING_ELSE = '';

/**
 * Explore's points as series over its buckets: the largest `keep` named series by total, then
 * every other series and the route's own everything else summed into one named for what it
 * holds, so nothing is dropped from the stack.
 */
export function stacked(view: ApiExplore | undefined, keep: number, rest: string): Stacked {
  if (view === undefined) {
    return { periods: [], series: [] };
  }
  const periods = [...new Set(view.points.map((point) => point.bucket))].sort();
  const totals = new Map<string, number>();
  for (const point of view.points) {
    const name = point.series ?? EVERYTHING_ELSE;
    totals.set(name, (totals.get(name) ?? 0) + Number(point.cost));
  }
  const named = [...totals]
    .filter(([name]) => name !== EVERYTHING_ELSE)
    .sort((left, right) => right[1] - left[1])
    .map(([name]) => name);
  const others = new Set(named.slice(keep));
  if (totals.has(EVERYTHING_ELSE)) {
    others.add(EVERYTHING_ELSE);
  }
  const valueOf = (names: ReadonlySet<string>, bucket: string): number =>
    view.points
      .filter((point) => point.bucket === bucket && names.has(point.series ?? EVERYTHING_ELSE))
      .reduce((total, point) => total + Number(point.cost), 0);
  const series: StackedSeries[] = named.slice(0, keep).map((name) => ({
    key: name,
    label: name,
    values: periods.map((bucket) => valueOf(new Set([name]), bucket)),
  }));
  if (others.size > 0) {
    series.push({
      key: rest,
      label: rest,
      values: periods.map((bucket) => valueOf(others, bucket)),
    });
  }
  return { periods, series };
}
