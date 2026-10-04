import { useCallback, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import type { ApiMeta } from '../api/types';
import { MetaContext, type MetaRegistry } from './metaRegistry';
import { aggregateReports, type FreshnessSource, type SurfaceReport } from './metaStore';

export function MetaProvider({ children }: { readonly children: ReactNode }) {
  const [reports, setReports] = useState<Readonly<Record<string, SurfaceReport>>>({});

  const report = useCallback(
    (id: string, meta: ApiMeta | undefined, freshness: FreshnessSource = 'envelope') => {
      setReports((current) => {
        if (meta === undefined) {
          if (!(id in current)) return current;
          return Object.fromEntries(Object.entries(current).filter(([key]) => key !== id));
        }
        const held = current[id];
        if (held !== undefined && held.meta === meta && held.freshness === freshness) {
          return current;
        }
        return { ...current, [id]: { meta, freshness } };
      });
    },
    [],
  );

  const value = useMemo<MetaRegistry>(
    () => ({ report, aggregate: aggregateReports(Object.values(reports)) }),
    [report, reports],
  );

  return <MetaContext.Provider value={value}>{children}</MetaContext.Provider>;
}
