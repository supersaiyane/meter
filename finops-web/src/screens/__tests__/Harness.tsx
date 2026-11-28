import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { ApiProvider } from '../../api/ApiProvider';
import type { ApiClient } from '../../api/client';
import { MetaProvider } from '../../shell/MetaProvider';

export function Harness({
  client,
  children,
}: {
  readonly client: ApiClient;
  readonly children: ReactNode;
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={client}>
        <MetaProvider>{children}</MetaProvider>
      </ApiProvider>
    </QueryClientProvider>
  );
}
