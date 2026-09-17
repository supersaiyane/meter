import type { ApiFailure, ApiMeta } from '../api/types';

/**
 * Combining the meta from every surface currently on screen.
 *
 * The shell shows one freshness figure and one coverage figure for the whole
 * page, and both have to be the worst case rather than an average. A page whose
 * oldest panel is nine hours old is a nine hour old page, and reporting the
 * newest panel would make it look current while a stale number sits beside it.
 */

export interface CoverageLine {
  readonly unit: string;
  readonly visible: number;
  readonly total: number;
}

export interface AggregateMeta {
  readonly asOf: string | null;
  readonly collectedAt: string | null;
  readonly visible: number;
  readonly total: number;
  readonly isPartial: boolean;
  /** What the counts are counting. `in view` when two surfaces disagree. */
  readonly unit: string;
  /**
   * One line per thing being counted, so a page whose panels count different
   * things states each rather than one ratio that describes neither.
   *
   * Home is the case. It shows Meter's own cost, counted in accounts, beside
   * the top findings, counted in workspaces. The conservative rule took the
   * smallest visible and the largest total across both and produced "0 of 3",
   * which was true of nothing on the page.
   *
   * A unit whose total is zero is left out. There is nothing to be partial
   * about, and "all 0 accounts" is noise beside a real count.
   */
  readonly coverage: readonly CoverageLine[];
  readonly degraded: boolean;
  readonly failures: readonly ApiFailure[];
}

/** What a coverage line says when the response did not name what it counted. */
const FALLBACK_UNIT = 'in view';

export const EMPTY_AGGREGATE: AggregateMeta = {
  asOf: null,
  collectedAt: null,
  visible: 0,
  total: 0,
  isPartial: false,
  unit: 'accounts',
  coverage: [],
  degraded: false,
  failures: [],
};

function oldest(left: string | null, right: string | null): string | null {
  if (left === null) return right;
  if (right === null) return left;
  return left < right ? left : right;
}

/** One row per scope, collector and cause. The same break reported by three panels is one problem. */
function dedupe(failures: readonly ApiFailure[]): ApiFailure[] {
  const seen = new Map<string, ApiFailure>();
  for (const failure of failures) {
    seen.set(`${failure.scope_key}|${failure.collector}|${failure.cause}`, failure);
  }
  return [...seen.values()];
}

export function aggregate(metas: readonly ApiMeta[]): AggregateMeta {
  if (metas.length === 0) {
    return EMPTY_AGGREGATE;
  }
  let asOf: string | null = null;
  let collectedAt: string | null = null;
  let visible = Number.POSITIVE_INFINITY;
  let total = 0;
  let degraded = false;
  const failures: ApiFailure[] = [];

  for (const meta of metas) {
    asOf = oldest(asOf, meta.as_of);
    collectedAt = oldest(collectedAt, meta.collected_at);
    // The most conservative coverage wins. If one panel can see two accounts
    // and another can see five, the page cannot claim five.
    visible = Math.min(visible, meta.scope_coverage.visible);
    total = Math.max(total, meta.scope_coverage.total);
    degraded = degraded || meta.degraded;
    failures.push(...meta.failures);
  }

  const resolvedVisible = Number.isFinite(visible) ? visible : 0;
  // Two surfaces counting different things cannot be described by either noun,
  // and picking one of them would be a claim nothing supports.
  // Defaulted, because a response that predates the field, or one from a
  // version that never had it, would otherwise render the literal word
  // `undefined` in a coverage statement. A missing noun is not a noun.
  const units = new Set(metas.map((meta) => meta.scope_coverage.unit || FALLBACK_UNIT));
  const byUnit = new Map<string, CoverageLine>();
  for (const meta of metas) {
    const { visible: seen, total: all } = meta.scope_coverage;
    const unit = meta.scope_coverage.unit || FALLBACK_UNIT;
    const line = byUnit.get(unit);
    byUnit.set(unit, {
      unit,
      // Conservative within a unit, where the two numbers describe the same
      // thing and the smaller claim is the safe one.
      visible: line === undefined ? seen : Math.min(line.visible, seen),
      total: line === undefined ? all : Math.max(line.total, all),
    });
  }
  return {
    asOf,
    collectedAt,
    visible: resolvedVisible,
    total,
    isPartial: resolvedVisible < total,
    unit: units.size === 1 ? ([...units][0] as string) : 'in view',
    coverage: [...byUnit.values()].filter((line) => line.total > 0),
    degraded,
    failures: dedupe(failures),
  };
}
