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
  // Partial first. A page that is both is better described by the one with a
  // number in it, and the failing collectors are listed in the trust strip on
  // every screen regardless. Degraded and complete still reports degraded.
  if (meta.scope_coverage.is_partial) {
    return {
      kind: 'partial',
      missing: meta.scope_coverage.total - meta.scope_coverage.visible,
      reason: reasonFor(meta),
    };
  }
  if (meta.degraded && meta.failures.length > 0) {
    return {
      kind: 'degraded',
      failing: [...new Set(meta.failures.map((failure) => failure.collector))],
    };
  }
  return { kind: 'ready' };
}

/**
 * Why part of the estate is missing, in the words of whatever reported it.
 *
 * This used to be the literal string `outside your scope` whatever the cause,
 * and on the query screens the cause is usually a workspace that refused Meter.
 * Naming the wrong cause sends a reader to request a permission they already
 * hold, which is worse than saying nothing at all. ISS-152.
 *
 * When nothing on the envelope explains the gap, entitlement is the remaining
 * explanation and saying so is correct.
 */
function reasonFor(meta: ApiMeta): string {
  const causes = [...new Set(meta.failures.map((failure) => failure.cause))];
  if (causes.length === 0) {
    return 'outside your scope';
  }
  if (causes.length === 1) {
    return `${causes[0] as string}, so Meter could not read it`;
  }
  return `${causes.join(', ')}, so Meter could not read them`;
}
