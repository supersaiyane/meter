import { useCallback, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import type { ApiMeta } from '../api/types';
import { MetaContext, type MetaRegistry } from './metaRegistry';
import { aggregate } from './metaStore';

export function MetaProvider({ children }: { readonly children: ReactNode }) {
  const [metas, setMetas] = useState<Readonly<Record<string, ApiMeta>>>({});

  const report = useCallback((id: string, meta: ApiMeta | undefined) => {
    setMetas((current) => {
      if (meta === undefined) {
        if (!(id in current)) return current;
        return Object.fromEntries(Object.entries(current).filter(([key]) => key !== id));
      }
      if (current[id] === meta) return current;
      return { ...current, [id]: meta };
    });
  }, []);

  const value = useMemo<MetaRegistry>(
    () => ({ report, aggregate: aggregate(Object.values(metas)) }),
    [report, metas],
  );

  return <MetaContext.Provider value={value}>{children}</MetaContext.Provider>;
}
