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
  costBudgetsFixture,
  costCommitmentsFixture,
} from './fixtures/cost';
import {
  recommendationsFixture,
  refusalsFixture,
  realizedSavingsFixture,
  scoresFixture,
} from './fixtures/waste';
import {
  blastRadiusFixture,
  entityFixture,
  graphCoverageFixture,
  geographyFixture,
  resourceListFixture,
  inventoryRootsFixture,
  subgraphFixture,
} from './fixtures/topology';
import { quotaDetailFixture, quotaRequestsFixture, quotasFixture } from './fixtures/quotas';
import {
  clustersFixture,
  containerCostFixture,
  containerWasteFixture,
} from './fixtures/containers';
import { digestsFixture, exchangesFixture, redactionsFixture } from './fixtures/assistant';
import type {
  ApiDigest,
  ApiExchange,
  ApiRedaction,
  ApiClusters,
  ApiContainerCost,
  ApiContainerWaste,
  ApiQuotaDetail,
  ApiQuotaRequests,
  ApiQuotas,
  ApiAdhocQuery,
  Account,
  ApiBlastRadius,
  ApiEntity,
  ApiGraphCoverage,
  ApiInventoryRoots,
  ApiGeographies,
  ApiResourceList,
  ApiSubgraph,
  ApiBudgets,
  ApiCommitments,
  ApiCostAnomalies,
  ApiCostDay,
  ApiCostSlice,
  ApiCostSummary,
  ApiEnvelope,
  ApiQueryFinding,
  ApiQueryGroup,
  ApiRemediation,
  ApiQueryFindingDetail,
  ApiRealizedSavings,
  ApiRecommendations,
  ApiRefusals,
  ApiScores,
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

export function useCostCommitments() {
  return useQuerySurface<ApiCommitments>(
    ['cost-commitments'],
    '/api/v1/cost/commitments',
    '/api/v1/cost/commitments',
    costCommitmentsFixture,
  );
}

/**
 * The P3 surfaces. FEAT-028, FEAT-029 and FEAT-043.
 *
 * Three hooks rather than one, mirroring the three routes, and that separation
 * is the feature: a single hook returning the estimate and the realization would
 * be the one place a screen could add them together.
 */
export function useRefusals() {
  return useQuerySurface<ApiRefusals>(
    ['waste-refusals'],
    '/api/v1/waste/refusals',
    '/api/v1/waste/refusals',
    refusalsFixture,
  );
}

export function useRecommendations() {
  return useQuerySurface<ApiRecommendations>(
    ['waste-recommendations'],
    '/api/v1/waste/recommendations',
    '/api/v1/waste/recommendations',
    recommendationsFixture,
  );
}

export function useRealizedSavings() {
  return useQuerySurface<ApiRealizedSavings>(
    ['waste-savings'],
    '/api/v1/waste/savings',
    '/api/v1/waste/savings',
    realizedSavingsFixture,
  );
}

export function useFinopsScore() {
  return useQuerySurface<ApiScores>(
    ['waste-score'],
    '/api/v1/waste/score',
    '/api/v1/waste/score',
    scoresFixture,
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
/**
 * The P4 surfaces. FEAT-030 and FEAT-032.
 *
 * Three hooks for three routes, and the subgraph hook takes its bounds as arguments
 * rather than holding them, because the depth and the node cap are things a reader
 * changes on the screen and a hook with them baked in would need a second hook per
 * combination.
 */
export function useInventoryRoots(nodeKind?: string) {
  const query = nodeKind === undefined ? '' : `?node_kind=${encodeURIComponent(nodeKind)}`;
  return useQuerySurface<ApiInventoryRoots>(
    ['inventory-roots', nodeKind ?? 'all'],
    '/api/v1/inventory/roots',
    `/api/v1/inventory/roots${query}`,
    inventoryRootsFixture,
  );
}

export function useGraphCoverage() {
  return useQuerySurface<ApiGraphCoverage>(
    ['inventory-coverage'],
    '/api/v1/inventory/coverage',
    '/api/v1/inventory/coverage',
    graphCoverageFixture,
  );
}

/**
 * One subgraph, by root.
 *
 * `enabled` is false until a root is chosen, because a map with no root is not a
 * request that can be made and firing one with an empty identifier would produce a
 * 404 the screen would then have to explain away.
 */
export function useTopologySubgraph(
  rootId: string | null,
  bounds: { readonly depth: number; readonly nodes: number },
) {
  const client = useApi();
  const path =
    rootId === null
      ? ''
      : `/api/v1/inventory/topology/${rootId}?depth=${String(bounds.depth)}` +
        `&nodes=${String(bounds.nodes)}`;
  return useQuery<Resolved<ApiEnvelope<ApiSubgraph>>>({
    queryKey: ['inventory-topology', rootId, bounds.depth, bounds.nodes],
    queryFn: resolveSurface(
      '/api/v1/inventory/topology/{node_id}',
      () => client.get<ApiSubgraph>(path),
      () => subgraphFixture(rootId ?? ''),
    ),
    enabled: rootId !== null,
  });
}

/**
 * One resource. FEAT-053.
 *
 * `enabled` is false until a node is chosen, for the same reason the subgraph hook's is:
 * firing with an empty identifier produces a 404 the screen would then have to explain
 * away as though it meant something.
 */
export function useEntity(nodeId: string | null) {
  const client = useApi();
  const path = nodeId === null ? '' : `/api/v1/inventory/nodes/${nodeId}`;
  return useQuery<Resolved<ApiEnvelope<ApiEntity>>>({
    queryKey: ['inventory-entity', nodeId],
    queryFn: resolveSurface(
      '/api/v1/inventory/nodes/{node_id}',
      () => client.get<ApiEntity>(path),
      () => entityFixture(nodeId ?? ''),
    ),
    enabled: nodeId !== null,
  });
}

/**
 * A page of resources. FEAT-056.
 *
 * Filters and bounds are arguments rather than state held here, for the same reason the
 * subgraph hook's are: a reader changes them on the screen, and a hook holding them would
 * need one instance per combination.
 *
 * The query key carries every filter, so two different filters are two cached answers rather
 * than one answer served for both.
 */
export function useGeography() {
  return useQuerySurface<ApiGeographies>(
    ['inventory-geography'],
    '/api/v1/inventory/geography',
    '/api/v1/inventory/geography',
    geographyFixture,
  );
}

export function useResources(query: {
  // `| undefined` explicitly, because `exactOptionalPropertyTypes` is on: an optional property
  // and a property that may hold undefined are different types under it, and the caller builds
  // this object with undefined for the filters it is not applying.
  readonly accountId?: string | undefined;
  readonly regionId?: string | undefined;
  /** Every region in one geography, by prefix. FEAT-061's click from the map. */
  readonly geography?: string | undefined;
  readonly nodeKind?: string | undefined;
  readonly resourceType?: string | undefined;
  readonly limit: number;
  readonly offset: number;
}) {
  const search = new URLSearchParams({
    limit: String(query.limit),
    offset: String(query.offset),
  });
  if (query.accountId !== undefined) search.set('account_id', query.accountId);
  if (query.regionId !== undefined) search.set('region_id', query.regionId);
  if (query.geography !== undefined) search.set('geography', query.geography);
  if (query.nodeKind !== undefined) search.set('node_kind', query.nodeKind);
  if (query.resourceType !== undefined) search.set('resource_type', query.resourceType);
  return useQuerySurface<ApiResourceList>(
    [
      'inventory-resources',
      query.accountId ?? 'all',
      query.regionId ?? 'all',
      query.geography ?? 'all',
      query.nodeKind ?? 'all',
      query.resourceType ?? 'all',
      query.limit,
      query.offset,
    ],
    '/api/v1/inventory/resources',
    `/api/v1/inventory/resources?${search.toString()}`,
    resourceListFixture,
  );
}

/**
 * One resource's blast radius. FEAT-044.
 *
 * Its own hook and its own route rather than a field on the entity payload, because the entity
 * page walks one hop and this walks four: folding it in would make every visit to a resource
 * pay for a traversal most visits do not need.
 */
export function useBlastRadius(nodeId: string | null) {
  const client = useApi();
  const path = nodeId === null ? '' : `/api/v1/inventory/nodes/${nodeId}/blast-radius`;
  return useQuery<Resolved<ApiEnvelope<ApiBlastRadius>>>({
    queryKey: ['inventory-blast-radius', nodeId],
    queryFn: resolveSurface(
      '/api/v1/inventory/nodes/{node_id}/blast-radius',
      () => client.get<ApiBlastRadius>(path),
      () => blastRadiusFixture(),
    ),
    enabled: nodeId !== null,
  });
}

/**
 * Budgets for a period. FEAT-060.
 *
 * The budgets screen owns this, and the home screen's panel reads the same hook and the same
 * query key rather than asking for its own slice, per docs/13-UI-ARCHITECTURE.md: a panel with
 * its own query will one day disagree with the screen it summarises.
 */
/**
 * The two quota lists and the counts behind them. FEAT-033.
 *
 * One hook for both lists, unlike the estimate and the realization in `useWaste`, and the
 * reason is the opposite: those two must never be added together, while these two are halves
 * of one answer and the ratio between them is the finding. A screen holding one without the
 * other would report an estate with excellent headroom everywhere.
 */
export function useQuotas() {
  return useQuerySurface<ApiQuotas>(
    ['governance-quotas'],
    '/api/v1/governance/quotas',
    '/api/v1/governance/quotas',
    quotasFixture,
  );
}

/**
 * One quota, everywhere it applies, with the draft and the requests. FEAT-033 and FEAT-034.
 *
 * Reached from the list rather than from the navigation, like the query finding detail and the
 * entity page: a quota code is not something anybody types.
 */
export function useQuotaDetail(serviceCode: string, quotaCode: string) {
  return useQuerySurface<ApiQuotaDetail>(
    ['governance-quota', serviceCode, quotaCode],
    '/api/v1/governance/quotas/{service_code}/{quota_code}',
    `/api/v1/governance/quotas/${serviceCode}/${quotaCode}`,
    quotaDetailFixture,
  );
}

/** Increase requests and what became of them, refusals included. FEAT-034. */
export function useQuotaRequests() {
  return useQuerySurface<ApiQuotaRequests>(
    ['governance-quota-requests'],
    '/api/v1/governance/quotas/requests',
    '/api/v1/governance/quotas/requests',
    quotaRequestsFixture,
  );
}

export function useBudgets() {
  return useQuerySurface<ApiBudgets>(
    ['cost-budgets'],
    '/api/v1/cost/budgets',
    '/api/v1/cost/budgets',
    costBudgetsFixture,
  );
}

/**
 * Cost by cluster, namespace and workload. FEAT-035, under Cost per ADR-0020.
 *
 * Measured, not apportioned: the figures are split cost allocation columns on the bill
 * already being read, so every one carries the same timestamps as any other charge.
 */
export function useContainerCost() {
  return useQuerySurface<ApiContainerCost>(
    ['cost-containers'],
    '/api/v1/cost/containers',
    '/api/v1/cost/containers',
    containerCostFixture,
  );
}

/**
 * Requested against used, per workload. FEAT-036, under Waste.
 *
 * A separate read from the cost, because a cluster can have a cost and no readable
 * requests, and folding one into the other would invite a join that drops it.
 */
export function useContainerWaste() {
  return useQuerySurface<ApiContainerWaste>(
    ['waste-containers'],
    '/api/v1/waste/containers',
    '/api/v1/waste/containers',
    containerWasteFixture,
  );
}

/** Clusters, their fleets, Spot ratio and bin packing. Under Inventory. */
export function useClusters() {
  return useQuerySurface<ApiClusters>(
    ['inventory-clusters'],
    '/api/v1/inventory/clusters',
    '/api/v1/inventory/clusters',
    clustersFixture,
  );
}

/**
 * The P7 surfaces. FEAT-038, FEAT-041, FEAT-042 and FEAT-046, under Assistant.
 *
 * The asker's own exchanges and their own redaction events, ADR-0029: a person reads what
 * they asked and nobody else's, whatever else their scope reaches. The digests are payer
 * wide, and a narrowed reader is told so by the coverage rather than by an empty list.
 */
const EXCHANGES_KEY = ['assistant-exchanges'] as const;
const REDACTIONS_KEY = ['assistant-redactions'] as const;

export function useExchanges() {
  return useQuerySurface<ApiExchange[]>(
    EXCHANGES_KEY,
    '/api/v1/assistant/exchanges',
    '/api/v1/assistant/exchanges',
    exchangesFixture,
  );
}

export function useRedactions() {
  return useQuerySurface<ApiRedaction[]>(
    REDACTIONS_KEY,
    '/api/v1/assistant/redactions',
    '/api/v1/assistant/redactions',
    redactionsFixture,
  );
}

export function useDigests() {
  return useQuerySurface<ApiDigest[]>(
    ['assistant-digests'],
    '/api/v1/assistant/digests',
    '/api/v1/assistant/digests',
    digestsFixture,
  );
}

/**
 * Ask one question. The only write P7 makes, and it writes into Meter's own database.
 *
 * The question goes in the body, never the URL, where it would be written into every access
 * log on the way. Both lists are read again afterwards rather than patched here, because the
 * server wrote the exchange whatever came back, and a question holding a secret also wrote a
 * redaction event: a screen that assumed what was stored would show a history that exists
 * nowhere.
 */
export function useAsk() {
  const client = useApi();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (question: string) =>
      client.post<ApiExchange>('/api/v1/assistant/ask', { question }),
    // Not returned. A returned promise is awaited before the mutation settles, so the answer
    // would wait on both lists being read again, and the lists are not what was asked for.
    onSettled: () => {
      void queries.invalidateQueries({ queryKey: EXCHANGES_KEY });
      void queries.invalidateQueries({ queryKey: REDACTIONS_KEY });
    },
  });
}
