import type { ReactNode } from 'react';

import { ApiContext } from './apiContext';
import type { ApiClient } from './client';

export function ApiProvider({
  client,
  children,
}: {
  readonly client: ApiClient;
  readonly children: ReactNode;
}) {
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>;
}
