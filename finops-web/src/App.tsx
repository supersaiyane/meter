import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiProvider } from './api/ApiProvider';
import type { ApiClient } from './api/client';
import { createQueryClient } from './queryClient';
import { AppShell } from './shell/AppShell';
import { MetaProvider } from './shell/MetaProvider';
import type { Section } from './shell/sections';
import { AccountsScreen } from './screens/AccountsScreen';
import { FreshnessScreen } from './screens/FreshnessScreen';
import { IngestScreen } from './screens/IngestScreen';
import { OrganizationScreen } from './screens/OrganizationScreen';
import { PlatformScreen } from './screens/PlatformScreen';

/**
 * The application root.
 *
 * There is no login screen in P0 and none is faked here. Without a usable token
 * the API answers 401, the screens render that as a typed failure, and the
 * reader is told what happened. A placeholder that pretended to authenticate
 * would be the one dishonest surface in a product built on not being one.
 */
export function App({
  client,
  queryClient = createQueryClient(),
}: {
  readonly client: ApiClient;
  readonly queryClient?: QueryClient;
}) {
  const [section, setSection] = useState<Section>('Accounts');
  return (
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={client}>
        <MetaProvider>
          <AppShell section={section} onSelect={setSection}>
            {section === 'Accounts' ? <AccountsScreen /> : null}
            {section === 'Organization' ? <OrganizationScreen /> : null}
            {section === 'Ingest' ? <IngestScreen /> : null}
            {section === 'Freshness' ? <FreshnessScreen /> : null}
            {section === 'Platform' ? <PlatformScreen /> : null}
          </AppShell>
        </MetaProvider>
      </ApiProvider>
    </QueryClientProvider>
  );
}
