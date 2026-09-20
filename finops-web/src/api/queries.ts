import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useApi } from './apiContext';
import { resolveSurface, type Resolved } from './fixtureSeam';
import {
  queryFindingDetailFixture,
  queryFindingsFixture,
  adhocQueriesFixture,
  queryGroupsFixture,
  surfaceInstancesFixture,
  enforcementActionsFixture,
} from './fixtures/query';
import {
  costSummaryFixture,
  costByServiceFixture,
  costByAccountFixture,
  costAllocationFixture,
  costTrendFixture,
  costAnomaliesFixture,
} from './fixtures/cost';
import type {
  ApiAdhocQuery,
  Account,
  ApiCostAnomalies,
  ApiCostDay,
  ApiCostSlice,
  ApiCostSummary,
  ApiEnvelope,
  ApiQueryFinding,
  ApiQueryGroup,
  ApiRemediation,
  ApiQueryFindingDetail,
  ApiEnforcementAction,
  ApiSurfaceInstance,
  Freshness,
  PlatformCost,
  Run,
} from './types';
import type { FlatNode } from '../components/orgNodes';

/**
 * Server state, one hook per route.
 *
 * The envelope is kept whole rather than unwrapped to the data. A hook that
 * returned only the rows would let a screen render them without ever seeing the
 * coverage or the failures that came with them, which is the exact habit the
 * envelope exists to prevent.
 */

export function useAccounts() {
  const client = useApi();
  return useQuery<ApiEnvelope<Account[]>>({
    queryKey: ['accounts'],
    queryFn: () => client.get<Account[]>('/api/v1/accounts'),
  });
}

export function useOrgTree() {
  const client = useApi();
  return useQuery<ApiEnvelope<FlatNode[]>>({
    queryKey: ['org-tree'],
    queryFn: () => client.get<FlatNode[]>('/api/v1/org/tree'),
  });
}

export function useRuns() {
  const client = useApi();
  return useQuery<ApiEnvelope<Run[]>>({
    queryKey: ['runs'],
    queryFn: () => client.get<Run[]>('/api/v1/ingest/runs'),
  });
}

export function useFreshness() {
  const client = useApi();
  return useQuery<ApiEnvelope<Freshness[]>>({
    queryKey: ['freshness'],
    queryFn: () => client.get<Freshness[]>('/api/v1/health/freshness'),
  });
}

export function usePlatformCost() {
  const client = useApi();
  return useQuery<ApiEnvelope<PlatformCost[]>>({
    queryKey: ['platform-cost'],
    queryFn: () => client.get<PlatformCost[]>('/api/v1/platform/cost'),
  });
}

/**
 * A surface whose route may not exist yet, per
 * `docs/13-UI-ARCHITECTURE.md` section 11.
 *
 * The envelope is kept whole for the same reason every other hook here keeps
 * it: a hook returning only the rows lets a screen render them without seeing
 * the coverage or the failures that came with them. The resolved value also
 * carries `source`, which the screen hands to `FixtureBand` so a fixture cannot
 * be rendered without saying so.
 */
export function useQuerySurface<T>(
  key: readonly unknown[],
  template: string,
  path: string,
  fixture: () => ApiEnvelope<T>,
) {
  const client = useApi();
  return useQuery<Resolved<ApiEnvelope<T>>>({
    queryKey: key,
    queryFn: resolveSurface(template, () => client.get<T>(path), fixture),
  });
}

export function useQueryFindings() {
  return useQuerySurface<ApiQueryFinding[]>(
    ['query-findings'],
    '/api/v1/query/findings',
    '/api/v1/query/findings',
    queryFindingsFixture,
  );
}

/**
 * One finding, by id.
 *
 * The declared template and the fetched path differ here, which is the case the
 * template matching in `fixtureSeam` exists for: `{id}` is what FastAPI calls
 * the route, and the concrete id is what the browser asks for.
 */
export function useQueryFinding(id: string) {
  return useQuerySurface<ApiQueryFindingDetail | null>(
    ['query-finding', id],
    '/api/v1/query/findings/{id}',
    `/api/v1/query/findings/${id}`,
    () => queryFindingDetailFixture(id),
  );
}

/**
 * Remediate one finding, or put the last remediation back.
 *
 * Both invalidate the finding rather than patching a local copy, so what the
 * screen shows afterwards is what the server actually holds. A remediation can
 * refuse, and can revert itself when the write did not take, and a screen that
 * assumed success would then be showing a state that does not exist anywhere.
 */
export function useRemediate(findingId: string) {
  const client = useApi();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: () => client.post<ApiRemediation>(`/api/v1/query/remediate/${findingId}`),
    onSettled: () => queries.invalidateQueries({ queryKey: ['query-finding', findingId] }),
  });
}

export function useUndoRemediation(findingId: string) {
  const client = useApi();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: () => client.post<ApiRemediation>(`/api/v1/query/remediate/${findingId}/undo`),
    onSettled: () => queries.invalidateQueries({ queryKey: ['query-finding', findingId] }),
  });
}

export function useQueryGroups() {
  return useQuerySurface<ApiQueryGroup[]>(
    ['query-groups'],
    '/api/v1/query/groups',
    '/api/v1/query/groups',
    queryGroupsFixture,
  );
}

export function useQueryAdhoc() {
  return useQuerySurface<ApiAdhocQuery[]>(
    ['query-adhoc'],
    '/api/v1/query/adhoc',
    '/api/v1/query/adhoc',
    adhocQueriesFixture,
  );
}

export function useCostSummary() {
  return useQuerySurface<ApiCostSummary>(
    ['cost-summary'],
    '/api/v1/cost/summary',
    '/api/v1/cost/summary',
    costSummaryFixture,
  );
}

export function useCostByService() {
  return useQuerySurface<ApiCostSlice[]>(
    ['cost-by-service'],
    '/api/v1/cost/by-service',
    '/api/v1/cost/by-service',
    costByServiceFixture,
  );
}

export function useCostByAccount() {
  return useQuerySurface<ApiCostSlice[]>(
    ['cost-by-account'],
    '/api/v1/cost/by-account',
    '/api/v1/cost/by-account',
    costByAccountFixture,
  );
}

export function useCostTrend() {
  return useQuerySurface<ApiCostDay[]>(
    ['cost-trend'],
    '/api/v1/cost/trend',
    '/api/v1/cost/trend',
    costTrendFixture,
  );
}

/**
 * Allocation by one tag key.
 *
 * The key is part of the query string, so it is part of the cache key too. Two
 * groupings of the same period by different keys are different answers and
 * must not share an entry.
 */
export function useCostAllocation(tag: string) {
  return useQuerySurface<ApiCostSlice[]>(
    ['cost-allocation', tag],
    '/api/v1/cost/allocation',
    `/api/v1/cost/allocation?tag=${encodeURIComponent(tag)}`,
    costAllocationFixture,
  );
}

export function useCostAnomalies() {
  return useQuerySurface<ApiCostAnomalies>(
    ['cost-anomalies'],
    '/api/v1/cost/anomalies',
    '/api/v1/cost/anomalies',
    costAnomaliesFixture,
  );
}

export function useQuerySurfaces() {
  return useQuerySurface<ApiSurfaceInstance[]>(
    ['query-instances'],
    '/api/v1/query/instances',
    '/api/v1/query/instances',
    surfaceInstancesFixture,
  );
}

export function useEnforcementActions() {
  return useQuerySurface<ApiEnforcementAction[]>(
    ['query-enforcement'],
    '/api/v1/query/enforcement',
    '/api/v1/query/enforcement',
    enforcementActionsFixture,
  );
}
