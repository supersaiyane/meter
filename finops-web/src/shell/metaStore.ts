import type { ApiFailure, ApiMeta } from '../api/types';

/**
 * Combining the meta from every surface currently on screen.
 *
 * The shell shows one freshness figure and one coverage figure for the whole
 * page, and both have to be the worst case rather than an average. A page whose
 * oldest panel is nine hours old is a nine hour old page, and reporting the
 * newest panel would make it look current while a stale number sits beside it.
 */

export interface AggregateMeta {
  readonly asOf: string | null;
  readonly collectedAt: string | null;
  readonly visible: number;
  readonly total: number;
  readonly isPartial: boolean;
  readonly degraded: boolean;
  readonly failures: readonly ApiFailure[];
}

export const EMPTY_AGGREGATE: AggregateMeta = {
  asOf: null,
  collectedAt: null,
  visible: 0,
  total: 0,
  isPartial: false,
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
  return {
    asOf,
    collectedAt,
    visible: resolvedVisible,
    total,
    isPartial: resolvedVisible < total,
    degraded,
    failures: dedupe(failures),
  };
}
