import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';

import { ApiProvider } from '../../api/ApiProvider';
import type { ApiClient } from '../../api/client';
import { MetaProvider } from '../../shell/MetaProvider';

export function Harness({
  client,
  children,
  initialPath = '/',
}: {
  readonly client: ApiClient;
  readonly children: ReactNode;
  /** Optional, so the screen tests written before routing existed still pass. */
  readonly initialPath?: string;
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={queryClient}>
        <ApiProvider client={client}>
          <MetaProvider>{children}</MetaProvider>
        </ApiProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}
