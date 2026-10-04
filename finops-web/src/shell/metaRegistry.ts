import { createContext, useContext, useEffect } from 'react';

import type { ApiMeta } from '../api/types';
import type { AggregateMeta, FreshnessSource } from './metaStore';

/**
 * The registry every surface reports its meta into, and the hooks that read it.
 *
 * Kept apart from the provider component so neither file mixes components with
 * values, which is what the React Refresh rule asks for and what keeps a hot
 * reload from silently dropping state.
 */

export interface MetaRegistry {
  readonly report: (id: string, meta: ApiMeta | undefined, freshness?: FreshnessSource) => void;
  readonly aggregate: AggregateMeta;
}

export const MetaContext = createContext<MetaRegistry | undefined>(undefined);

function useRegistry(): MetaRegistry {
  const registry = useContext(MetaContext);
  if (registry === undefined) {
    // A surface rendered outside the shell would silently lose its coverage and
    // its freshness, which is the one thing the shell exists to show.
    throw new Error('A data surface must be rendered inside MetaProvider');
  }
  return registry;
}

/**
 * Report this surface's meta for as long as it is on screen, and withdraw it after.
 *
 * `freshness` says where the surface's figures say how fresh they are. Left out, it is the
 * envelope, which is what every surface before P7 means. A surface passes `per-figure` only
 * when each figure it draws carries its own `as_of` beside it, see `FreshnessSource`.
 */
export function useReportMeta(
  id: string,
  meta: ApiMeta | undefined,
  freshness: FreshnessSource = 'envelope',
): void {
  const { report } = useRegistry();
  useEffect(() => {
    report(id, meta, freshness);
    return () => {
      report(id, undefined);
    };
  }, [id, meta, freshness, report]);
}

export function useAggregateMeta(): AggregateMeta {
  return useRegistry().aggregate;
}
