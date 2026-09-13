import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes, useLocation } from 'react-router';

import { ApiProvider } from './api/ApiProvider';
import type { ApiClient } from './api/client';
import { createQueryClient } from './queryClient';
import { AppShell } from './shell/AppShell';
import { MetaProvider } from './shell/MetaProvider';
import { screenFor } from './shell/sections';
import { AccountsScreen } from './screens/AccountsScreen';
import { HomeScreen } from './screens/HomeScreen';
import { FreshnessScreen } from './screens/FreshnessScreen';
import { IngestScreen } from './screens/IngestScreen';
import { OrganizationScreen } from './screens/OrganizationScreen';
import { QueryFindingsScreen } from './screens/QueryFindingsScreen';
import { PlatformScreen } from './screens/PlatformScreen';

/**
 * A route the navigation lists and no sub project has built yet.
 *
 * A listed screen with no implementation and a path that is not a screen at all
 * are different conditions, and they do not share a rendering. The first is a
 * roadmap entry the reader can trust; the second is a wrong address.
 */
function NotBuiltYet() {
  const { pathname } = useLocation();
  const screen = screenFor(pathname);

  if (screen === undefined) {
    return (
      <p data-testid="not-a-screen" data-state="unknown-route">
        No screen answers {pathname}.
      </p>
    );
  }
  return (
    <section data-testid="not-built" data-state="never-collected" aria-label={screen.label}>
      <h2>{screen.label}</h2>
      <p>not yet collected, arrives with {screen.arrives}</p>
    </section>
  );
}

/**
 * The application root.
 *
 * There is no login screen in P0 and none is faked here. Without a usable token
 * the API answers 401, the screens render that as a typed failure, and the
 * reader is told what happened. A placeholder that pretended to authenticate
 * would be the one dishonest surface in a product built on not being one.
 *
 * Routes carry their group, per ADR-0020. The five screens below moved here from
 * a five entry state machine, because a screen with no URL cannot be linked to,
 * and a finding nobody can link to is a finding nobody hands to its owner.
 */
export function App({
  client,
  queryClient = createQueryClient(),
}: {
  readonly client: ApiClient;
  readonly queryClient?: QueryClient;
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={client}>
        <BrowserRouter>
          <MetaProvider>
            <AppShell>
              <Routes>
                <Route path="/" element={<HomeScreen />} />
                <Route path="/inventory/accounts" element={<AccountsScreen />} />
                <Route path="/inventory/organization" element={<OrganizationScreen />} />
                <Route path="/governance/queries" element={<QueryFindingsScreen />} />
                <Route path="/platform/ingest" element={<IngestScreen />} />
                <Route path="/platform/freshness" element={<FreshnessScreen />} />
                <Route path="/platform/cost" element={<PlatformScreen />} />
                <Route path="*" element={<NotBuiltYet />} />
              </Routes>
            </AppShell>
          </MetaProvider>
        </BrowserRouter>
      </ApiProvider>
    </QueryClientProvider>
  );
}
