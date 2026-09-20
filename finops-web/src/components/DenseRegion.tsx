import type { ReactNode } from 'react';

import { DensityContext } from './density';

/** Marks everything inside as a dense region. See `density.ts` for why. */
export function DenseRegion({ children }: { readonly children: ReactNode }) {
  return <DensityContext.Provider value={true}>{children}</DensityContext.Provider>;
}
