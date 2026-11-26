import { createContext, useContext, useEffect } from 'react';

import type { ApiMeta } from '../api/types';
import type { AggregateMeta } from './metaStore';

/**
 * The registry every surface reports its meta into, and the hooks that read it.
 *
 * Kept apart from the provider component so neither file mixes components with
 * values, which is what the React Refresh rule asks for and what keeps a hot
 * reload from silently dropping state.
 */

export interface MetaRegistry {
  readonly report: (id: string, meta: ApiMeta | undefined) => void;
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

/** Report this surface's meta for as long as it is on screen, and withdraw it after. */
export function useReportMeta(id: string, meta: ApiMeta | undefined): void {
  const { report } = useRegistry();
  useEffect(() => {
    report(id, meta);
    return () => {
      report(id, undefined);
    };
  }, [id, meta, report]);
}

export function useAggregateMeta(): AggregateMeta {
  return useRegistry().aggregate;
}
