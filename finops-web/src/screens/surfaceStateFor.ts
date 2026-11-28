import type { ApiMeta } from '../api/types';
import type { Cause } from '../components/provenance';
import type { SurfaceState } from '../components/surfaceState';

/**
 * Choosing which of the seven states a screen is in.
 *
 * Written once, because the ordering is where the mistakes are. A failed
 * request outranks everything: showing rows beside a failure banner implies the
 * rows are complete. Never collected outranks empty, because an empty success
 * and a collector that has never run look identical on screen and mean opposite
 * things.
 */
export interface QueryLike {
  readonly isPending: boolean;
  readonly isError: boolean;
  readonly error: unknown;
}

const KNOWN_CAUSES = new Set<string>([
  'AccessDenied',
  'Throttled',
  'NotOptedIn',
  'Unreachable',
  'SchemaDrift',
]);

function causeOf(error: unknown): Exclude<Cause, 'NoData'> {
  const name = error instanceof Error ? error.message : String(error);
  for (const cause of KNOWN_CAUSES) {
    if (name.includes(cause)) return cause as Exclude<Cause, 'NoData'>;
  }
  // A failure the frontend cannot classify is drift, which is loud, rather than
  // something softer that would read as ordinary.
  return 'SchemaDrift';
}

export function surfaceStateFor(
  query: QueryLike,
  meta: ApiMeta | undefined,
  visibleRows: number,
  filterLabel: string,
  collector: string,
): SurfaceState {
  if (query.isPending) {
    return { kind: 'loading', rows: 8 };
  }
  if (query.isError) {
    return {
      kind: 'failed',
      cause: causeOf(query.error),
      remediation: query.error instanceof Error ? query.error.message : 'The request failed.',
    };
  }
  if (meta === undefined) {
    return {
      kind: 'failed',
      cause: 'SchemaDrift',
      remediation: 'The response carried no meta.',
    };
  }
  if (meta.as_of === null) {
    return { kind: 'never-collected', collector };
  }
  if (visibleRows === 0) {
    return { kind: 'empty', filter: filterLabel };
  }
  if (meta.degraded && meta.failures.length > 0) {
    return {
      kind: 'degraded',
      failing: [...new Set(meta.failures.map((failure) => failure.collector))],
    };
  }
  if (meta.scope_coverage.is_partial) {
    return {
      kind: 'partial',
      missing: meta.scope_coverage.total - meta.scope_coverage.visible,
      reason: 'outside your scope',
    };
  }
  return { kind: 'ready' };
}
