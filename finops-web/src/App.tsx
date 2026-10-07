import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router';

import { ApiProvider } from './api/ApiProvider';
import type { ApiClient } from './api/client';
import { createQueryClient } from './queryClient';
import { AppShell } from './shell/AppShell';
import { MetaProvider } from './shell/MetaProvider';
import { redirectFor, screenFor } from './shell/sections';
import { AccountsScreen } from './screens/AccountsScreen';
import { HomeScreen } from './screens/HomeScreen';
import { FreshnessScreen } from './screens/FreshnessScreen';
import { IngestScreen } from './screens/IngestScreen';
import { OrganizationScreen } from './screens/OrganizationScreen';
import { BudgetsScreen } from './screens/BudgetsScreen';
import { ForecastScreen } from './screens/ForecastScreen';
import { GeographyScreen } from './screens/GeographyScreen';
import { EntityScreen } from './screens/EntityScreen';
import { ResourceListScreen } from './screens/ResourceListScreen';
import { TopologyScreen } from './screens/TopologyScreen';
import { QueryFindingDetailScreen } from './screens/QueryFindingDetailScreen';
import { CostScreen } from './screens/CostScreen';
import { CostAllocationScreen } from './screens/CostAllocationScreen';
import { CostAnomaliesScreen } from './screens/CostAnomaliesScreen';
import { CostCommitmentsScreen } from './screens/CostCommitmentsScreen';
import { CostExportScreen } from './screens/CostExportScreen';
import { QueryAdhocScreen } from './screens/QueryAdhocScreen';
import { QueryFindingsScreen } from './screens/QueryFindingsScreen';
import { EnforcementScreen } from './screens/EnforcementScreen';
import { QuerySurfacesScreen } from './screens/QuerySurfacesScreen';
import { QuotaDetailScreen } from './screens/QuotaDetailScreen';
import { QuotasScreen } from './screens/QuotasScreen';
import { WasteScreen } from './screens/WasteScreen';
import { WasteSavingsScreen } from './screens/WasteSavingsScreen';
import { WasteScoreScreen } from './screens/WasteScoreScreen';
import { ContainerWasteScreen } from './screens/ContainerWasteScreen';
import { ContainerCostScreen } from './screens/ContainerCostScreen';
import { ClustersScreen } from './screens/ClustersScreen';
import { PlatformScreen } from './screens/PlatformScreen';
import { AssistantScreen } from './screens/AssistantScreen';
import { DigestsScreen } from './screens/DigestsScreen';
import { ReportLibraryScreen } from './screens/ReportLibraryScreen';

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
 * An address that is not a route: one that moved in P8 goes where it went, with
 * its query and fragment, and anything else is not built or not a screen.
 * Replaced rather than pushed, so the back button does not return to an
 * address that only forwards.
 */
function MovedOrNotBuilt() {
  const { pathname, search, hash } = useLocation();
  const moved = redirectFor(pathname);
  if (moved !== null) {
    return <Navigate to={`${moved}${search}${hash}`} replace />;
  }
  return <NotBuiltYet />;
}

/**
 * The application root.
 *
 * There is no login screen in P0 and none is faked here. Without a usable token
 * the API answers 401, the screens render that as a typed failure, and the
 * reader is told what happened. A placeholder that pretended to authenticate
 * would be the one dishonest surface in a product built on not being one.
 *
 * Routes follow the navigation of ADR-0030, grouped as `sections.ts` groups
 * them. Every path the navigation had before P8 still resolves, through
 * `MovedOrNotBuilt`, because a link nobody can follow is a finding nobody hands
 * to its owner.
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

                <Route path="/analyze/explorer" element={<CostScreen />} />
                <Route path="/analyze/allocation" element={<CostAllocationScreen />} />
                <Route path="/analyze/anomalies" element={<CostAnomaliesScreen />} />
                <Route path="/analyze/kubernetes-cost" element={<ContainerCostScreen />} />
                <Route
                  path="/analyze/kubernetes-rightsizing"
                  element={<ContainerWasteScreen />}
                />
                <Route path="/analyze/clusters" element={<ClustersScreen />} />

                <Route path="/plan/budgets" element={<BudgetsScreen />} />
                <Route path="/plan/forecasts" element={<ForecastScreen />} />
                <Route path="/plan/score" element={<WasteScoreScreen />} />

                <Route path="/optimize" element={<WasteScreen />} />
                <Route path="/optimize/commitments" element={<CostCommitmentsScreen />} />
                <Route path="/optimize/savings" element={<WasteSavingsScreen />} />

                <Route path="/govern/query-cost" element={<QueryFindingsScreen />} />
                <Route
                  path="/govern/query-cost/findings/:id"
                  element={<QueryFindingDetailScreen />}
                />
                <Route path="/govern/query-cost/surfaces" element={<QuerySurfacesScreen />} />
                <Route path="/govern/query-cost/adhoc" element={<QueryAdhocScreen />} />
                <Route path="/govern/quotas" element={<QuotasScreen />} />
                <Route
                  path="/govern/quotas/:serviceCode/:quotaCode"
                  element={<QuotaDetailScreen />}
                />
                <Route path="/govern/policies" element={<EnforcementScreen />} />

                <Route path="/inventory/accounts" element={<AccountsScreen />} />
                <Route
                  path="/inventory/accounts/organization"
                  element={<OrganizationScreen />}
                />
                {/* FEAT-056, closing ISS-204. Declared before the detail route so the
                    literal path is not eaten by the parameter. */}
                <Route path="/inventory/resources" element={<ResourceListScreen />} />
                {/* FEAT-053. The detail page, reached from the map, the waste list and
                    the anomaly list. */}
                <Route path="/inventory/resources/:nodeId" element={<EntityScreen />} />
                <Route path="/inventory/topology" element={<TopologyScreen />} />
                <Route path="/inventory/topology/geography" element={<GeographyScreen />} />

                <Route path="/report/library" element={<ReportLibraryScreen />} />
                <Route path="/report/exports" element={<CostExportScreen />} />

                <Route path="/assist" element={<AssistantScreen />} />
                <Route path="/assist/digests" element={<DigestsScreen />} />

                <Route path="/platform/freshness" element={<FreshnessScreen />} />
                <Route path="/platform/ingest" element={<IngestScreen />} />
                <Route path="/platform/cost" element={<PlatformScreen />} />

                <Route path="*" element={<MovedOrNotBuilt />} />
              </Routes>
            </AppShell>
          </MetaProvider>
        </BrowserRouter>
      </ApiProvider>
    </QueryClientProvider>
  );
}
