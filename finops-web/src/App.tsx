import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

import { createQueryClient } from './queryClient';
import { AppShell } from './shell/AppShell';
import { MetaProvider } from './shell/MetaProvider';
import type { Section } from './shell/sections';

/** The application root. */
export function App({ client = createQueryClient() }: { readonly client?: QueryClient }) {
  const [section, setSection] = useState<Section>('Accounts');
  return (
    <QueryClientProvider client={client}>
      <MetaProvider>
        <AppShell section={section} onSelect={setSection}>
          <p>Screens arrive in TASK-P0-027 and TASK-P0-028.</p>
        </AppShell>
      </MetaProvider>
    </QueryClientProvider>
  );
}
