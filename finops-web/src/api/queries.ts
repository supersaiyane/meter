import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useChosenAccount, withChosenAccount } from './account';
import { useApi } from './apiContext';
import { useExportable } from './exportViews';
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
  costByAccountFixture,
  costAllocationFixture,
  costAnomaliesFixture,
  costBudgetsFixture,
  costCommitmentsFixture,
  reconciliationFixture,
} from './fixtures/cost';
import {
  recommendationsFixture,
  alternativesFixture,
  refusalsFixture,
  realizedSavingsFixture,
  scoresFixture,
} from './fixtures/waste';
import { ledgerCreditsFixture, ledgerFixture } from './fixtures/ledger';
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
import { aiCallersFixture, aiGpuFixture, aiSpendFixture } from './fixtures/ai';
import type {
  ApiCommitmentCalendar,
  ApiCommitmentInventory,
  ApiPurchasePlans,
  ApiSavingsRate,
  ApiAiCallers,
  ApiAiGpuFleet,
  ApiAiGrouping,
  ApiAiSpend,
  ApiCommitmentDay,
  ApiReportRun,
  ApiSchedule,
  ApiSchedules,
  Me,
  ScheduleChange,
  ScheduleIn,
  ApiSavedView,
  SavedViewChange,
  SavedViewIn,
  ApiQueryCostDay,
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
  ApiReconciliation,
  ApiCommitments,
  ApiCostAnomalies,
  ApiCostSlice,
  ApiShowbackRow,
  ApiExplore,
  ApiForecast,
  ApiCostSummary,
  ApiEnvelope,
  ApiQueryFinding,
  ApiQueryGroup,
  ApiRemediation,
  ApiQueryFindingDetail,
  ApiRealizedSavings,
  ApiRecommendations,
  ApiAlternatives,
  ApiRefusals,
  ApiScores,
  ApiEnforcementAction,
  ApiSurfaceInstance,
  Freshness,
  PlatformCost,
  Run,
  ApiLedger,
  ApiLedgerCredits,
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

/**
 * The account chosen in the address, FEAT-075, applied the same way to every read: in the path,
 * so the server narrows the scope rather than a screen filtering rows, and in the key, so one
 * account's figures are never served from the cache under another's name. A path that is empty
 * because its query is disabled stays empty.
 */
function useNarrowing() {
  const account = useChosenAccount();
  return {
    key: (key: readonly unknown[]): readonly unknown[] => [...key, { account }],
    path: (path: string): string => (path === '' ? path : withChosenAccount(path, account)),
  };
}

/** How a read is made and how it is offered to the Export menu. */
export interface ReadOptions {
  /** False waits, and offers nothing: a view nobody read is not one to export. */
  readonly enabled?: boolean;
  /** The view's name in the Export menu, where the route's own name would not tell two apart. */
  readonly title?: string;
  /** False reads without offering, for a figure that only feeds another one. */
  readonly offered?: boolean;
}

/** One read of a built route, narrowed, and offered to the Export menu as it was read. */
function useRead<T>(
  key: readonly unknown[],
  template: string,
  path: string,
  { enabled = true, title, offered = true }: ReadOptions = {},
) {
  const client = useApi();
  const narrowing = useNarrowing();
  const narrowed = narrowing.path(path);
  useExportable(template, enabled && offered ? narrowed : '', title);
  return useQuery<ApiEnvelope<T>>({
    queryKey: narrowing.key(key),
    queryFn: () => client.get<T>(narrowed),
    enabled,
  });
}

/** How long the accounts the search box offers stay fresh. They change when an account joins. */
const ACCOUNT_CHOICES_FRESH_MS = 5 * 60 * 1000;

/**
 * Every account this session may see, for the search box, FEAT-075. Never narrowed: a box
 * listing only the chosen account could not choose another. Loaded once and searched in the
 * browser, because at 1,399 accounts a round trip per keystroke leaves the list behind the typing.
 */
export function useAccountChoices() {
  const client = useApi();
  return useQuery<ApiEnvelope<Account[]>>({
    queryKey: ['account-choices'],
    queryFn: () => client.get<Account[]>('/api/v1/accounts'),
    staleTime: ACCOUNT_CHOICES_FRESH_MS,
  });
}

/**
 * The services with spend this period, for the search box, FEAT-075. Narrowed like every read,
 * so a reader who chose an account finds that account's services, and never offered to the
 * Export menu, because the box is not the screen.
 */
export function useServiceChoices() {
  const client = useApi();
  const narrowing = useNarrowing();
  const path = narrowing.path('/api/v1/cost/by-service');
  return useQuery<ApiEnvelope<ApiCostSlice[]>>({
    queryKey: narrowing.key(['service-choices']),
    queryFn: () => client.get<ApiCostSlice[]>(path),
    staleTime: ACCOUNT_CHOICES_FRESH_MS,
  });
}

/**
 * Resources whose name or ARN holds the text, searched on the server and bounded, FEAT-075. An
 * estate of 1,399 accounts holds too many resources to load into the browser. Null asks nothing.
 */
export function useResourceSearch(text: string | null, limit: number) {
  const client = useApi();
  const narrowing = useNarrowing();
  const search = new URLSearchParams({ q: text ?? '', limit: String(limit) });
  const path = narrowing.path(
    text === null ? '' : `/api/v1/inventory/resources?${search.toString()}`,
  );
  return useQuery<ApiEnvelope<ApiResourceList>>({
    queryKey: narrowing.key(['resource-search', text, limit]),
    queryFn: () => client.get<ApiResourceList>(path),
    enabled: text !== null,
  });
}

export function useAccounts() {
  return useRead<Account[]>(['accounts'], '/api/v1/accounts', '/api/v1/accounts');
}

export function useOrgTree() {
  return useRead<FlatNode[]>(['org-tree'], '/api/v1/org/tree', '/api/v1/org/tree');
}

export function useRuns() {
  return useRead<Run[]>(['runs'], '/api/v1/ingest/runs', '/api/v1/ingest/runs');
}

export function useFreshness() {
  return useRead<Freshness[]>(
    ['freshness'],
    '/api/v1/health/freshness',
    '/api/v1/health/freshness',
  );
}

export function usePlatformCost() {
  return useRead<PlatformCost[]>(
    ['platform-cost'],
    '/api/v1/platform/cost',
    '/api/v1/platform/cost',
  );
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
  const narrowing = useNarrowing();
  const narrowed = narrowing.path(path);
  useExportable(template, narrowed);
  return useQuery<Resolved<ApiEnvelope<T>>>({
    queryKey: narrowing.key(key),
    queryFn: resolveSurface(template, () => client.get<T>(narrowed), fixture),
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

export function useQueryTrend() {
  return useRead<ApiQueryCostDay[]>(
    ['query-trend'],
    '/api/v1/query/trend',
    '/api/v1/query/trend',
  );
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

/** FEAT-066. The spend forecast: a range or the reason there is none, never a point. */
export function useCostForecast() {
  return useRead<ApiForecast>(
    ['cost-forecast'],
    '/api/v1/cost/forecast',
    '/api/v1/cost/forecast',
  );
}

/**
 * FEAT-065. Cost Explorer's query. The screen's query string is the view, so it is the cache
 * key too, and a link to a view and the view a reader built share one cached answer.
 */
export function useCostExplore(query: string, options: ReadOptions = {}) {
  const path = `/api/v1/cost/explore${query === '' ? '' : `?${query}`}`;
  return useRead<ApiExplore>(['cost-explore', query], '/api/v1/cost/explore', path, options);
}

export function useCostByAccount() {
  return useQuerySurface<ApiCostSlice[]>(
    ['cost-by-account'],
    '/api/v1/cost/by-account',
    '/api/v1/cost/by-account',
    costByAccountFixture,
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

export function useCommitmentDays() {
  return useRead<ApiCommitmentDay[]>(
    ['commitment-days'],
    '/api/v1/cost/commitments/daily',
    '/api/v1/cost/commitments/daily',
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
 * One billing period by account, service and tag value: showback, FEAT-045. The Export screen
 * shows these rows and the Export menu writes them, FEAT-067, which replaced the CSV the screen
 * used to fetch and save by hand.
 */
export function useShowback() {
  return useRead<ApiShowbackRow[]>(
    ['cost-showback'],
    '/api/v1/cost/showback',
    '/api/v1/cost/showback',
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

/**
 * What one rightsizing was compared with, TASK-P9-010. The declared template is FastAPI's, the
 * fetched path names the recommendation, as `useQueryFinding` does.
 */
export function useAlternatives(recommendationId: string) {
  return useQuerySurface<ApiAlternatives>(
    ['waste-alternatives', recommendationId],
    '/api/v1/waste/recommendations/{recommendation_id}/alternatives',
    `/api/v1/waste/recommendations/${recommendationId}/alternatives`,
    () => alternativesFixture(recommendationId),
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

/**
 * The savings ledger: teams by the savings they hold, FEAT-078, TASK-P11-008. Teams, never
 * people, OPEN-27; every figure measured, the months the bill showed a saving held.
 */
export function useLedger() {
  return useQuerySurface<ApiLedger>(
    ['savings-ledger'],
    '/api/v1/savings/ledger',
    '/api/v1/savings/ledger',
    ledgerFixture,
  );
}

/**
 * The AI spend surfaces, FEAT-081 to 085. A billing period's first day, or the newest the bill
 * holds when none is asked for, which is what the route reads too.
 */
function periodQuery(period: string, first: boolean): string {
  return period === '' ? '' : `${first ? '?' : '&'}period=${encodeURIComponent(period)}`;
}

export function useAiSpend(groupBy: ApiAiGrouping, period = '') {
  return useQuerySurface<ApiAiSpend>(
    ['ai-spend', groupBy, period],
    '/api/v1/ai/spend',
    `/api/v1/ai/spend?group_by=${groupBy}${periodQuery(period, false)}`,
    () => aiSpendFixture(groupBy),
  );
}

/** Who called which model. A separate read, because a caller can have usage the bill never priced. */
export function useAiCallers(period = '') {
  return useQuerySurface<ApiAiCallers>(
    ['ai-callers', period],
    '/api/v1/ai/callers',
    `/api/v1/ai/callers${periodQuery(period, true)}`,
    aiCallersFixture,
  );
}

/** The GPU instances the bill names and how busy each agent said it was. */
export function useAiGpu(period = '') {
  return useQuerySurface<ApiAiGpuFleet>(
    ['ai-gpu', period],
    '/api/v1/ai/gpu',
    `/api/v1/ai/gpu${periodQuery(period, true)}`,
    aiGpuFixture,
  );
}

/** Every credit the reader can see, each with its months; the screen shows one team's. */
export function useLedgerCredits() {
  return useQuerySurface<ApiLedgerCredits>(
    ['savings-ledger-credits'],
    '/api/v1/savings/ledger/credits',
    '/api/v1/savings/ledger/credits',
    ledgerCreditsFixture,
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
  const narrowing = useNarrowing();
  const path = narrowing.path(
    rootId === null
      ? ''
      : `/api/v1/inventory/topology/${rootId}?depth=${String(bounds.depth)}` +
          `&nodes=${String(bounds.nodes)}`,
  );
  return useQuery<Resolved<ApiEnvelope<ApiSubgraph>>>({
    queryKey: narrowing.key(['inventory-topology', rootId, bounds.depth, bounds.nodes]),
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
  const narrowing = useNarrowing();
  const path = narrowing.path(nodeId === null ? '' : `/api/v1/inventory/nodes/${nodeId}`);
  return useQuery<Resolved<ApiEnvelope<ApiEntity>>>({
    queryKey: narrowing.key(['inventory-entity', nodeId]),
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
  const narrowing = useNarrowing();
  const path = narrowing.path(
    nodeId === null ? '' : `/api/v1/inventory/nodes/${nodeId}/blast-radius`,
  );
  return useQuery<Resolved<ApiEnvelope<ApiBlastRadius>>>({
    queryKey: narrowing.key(['inventory-blast-radius', nodeId]),
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
 * Each invoice for a billing period beside Meter's billed cost under it. FEAT-076.
 *
 * Payer wide: a reader narrowed to fewer accounts, or one who chose a single account, is refused
 * with a 403 that names why, and the screen says so rather than showing a failure.
 */
export function useReconciliation() {
  return useQuerySurface<ApiReconciliation>(
    ['cost-reconciliation'],
    '/api/v1/cost/reconciliation',
    '/api/v1/cost/reconciliation',
    reconciliationFixture,
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

/**
 * The report library, FEAT-068. Never narrowed to a chosen account, as the search box's accounts
 * are not: a view is configuration rather than a figure counted in accounts, and a library that
 * emptied when an account was chosen would hide what the reader saved. Nor offered for export, as
 * the API's own exemption says: each view exports from its own screen.
 */
const SAVED_VIEWS = '/api/v1/reports/views';
const SAVED_VIEWS_KEY = ['saved-views'] as const;

function savedViewPath(viewId: string): string {
  return `${SAVED_VIEWS}/${encodeURIComponent(viewId)}`;
}

export function useSavedViews() {
  const client = useApi();
  return useQuery<ApiEnvelope<ApiSavedView[]>>({
    queryKey: SAVED_VIEWS_KEY,
    queryFn: () => client.get<ApiSavedView[]>(SAVED_VIEWS),
  });
}

export function useSaveView() {
  const client = useApi();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (view: SavedViewIn) => client.post<ApiSavedView>(SAVED_VIEWS, view),
    onSettled: () => queries.invalidateQueries({ queryKey: SAVED_VIEWS_KEY }),
  });
}

export function useChangeView() {
  const client = useApi();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: ({
      viewId,
      change,
    }: {
      readonly viewId: string;
      readonly change: SavedViewChange;
    }) => client.patch<ApiSavedView>(savedViewPath(viewId), change),
    onSettled: () => queries.invalidateQueries({ queryKey: SAVED_VIEWS_KEY }),
  });
}

export function useDeleteView() {
  const client = useApi();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (viewId: string) => client.delete<ApiSavedView>(savedViewPath(viewId)),
    onSettled: () => queries.invalidateQueries({ queryKey: SAVED_VIEWS_KEY }),
  });
}

/** Who is reading, FEAT-069: the schedule panel offers the reader as its first recipient. */
export function useMe() {
  const client = useApi();
  return useQuery<ApiEnvelope<Me>>({
    queryKey: ['me'],
    queryFn: () => client.get<Me>('/api/v1/me'),
  });
}

/**
 * Scheduled reports, FEAT-069. Never narrowed to a chosen account, as the library is not: a
 * schedule renders in each recipient's own scope, and a run is the reader's own record.
 */
const SCHEDULES = '/api/v1/reports/schedules';
const SCHEDULES_KEY = ['report-schedules'] as const;
const RUNS = '/api/v1/reports/runs';
const RUNS_KEY = ['report-runs'] as const;

function schedulePath(scheduleId: string): string {
  return `${SCHEDULES}/${encodeURIComponent(scheduleId)}`;
}

/** Where a run's kept file is fetched from, after the server checks scope again. */
export function runFilePath(runId: string): string {
  return `${RUNS}/${encodeURIComponent(runId)}/file`;
}

export function useSchedules() {
  const client = useApi();
  return useQuery<ApiEnvelope<ApiSchedules>>({
    queryKey: SCHEDULES_KEY,
    queryFn: () => client.get<ApiSchedules>(SCHEDULES),
  });
}

export function useReportRuns() {
  const client = useApi();
  return useQuery<ApiEnvelope<ApiReportRun[]>>({
    queryKey: RUNS_KEY,
    queryFn: () => client.get<ApiReportRun[]>(RUNS),
  });
}

export function useCreateSchedule() {
  const client = useApi();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (schedule: ScheduleIn) => client.post<ApiSchedule>(SCHEDULES, schedule),
    onSettled: () => queries.invalidateQueries({ queryKey: SCHEDULES_KEY }),
  });
}

export function useChangeSchedule() {
  const client = useApi();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: ({
      scheduleId,
      change,
    }: {
      readonly scheduleId: string;
      readonly change: ScheduleChange;
    }) => client.patch<ApiSchedule>(schedulePath(scheduleId), change),
    onSettled: () => queries.invalidateQueries({ queryKey: SCHEDULES_KEY }),
  });
}

export function useDeleteSchedule() {
  const client = useApi();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (scheduleId: string) => client.delete<ApiSchedule>(schedulePath(scheduleId)),
    onSettled: () => queries.invalidateQueries({ queryKey: SCHEDULES_KEY }),
  });
}

/* --- P14 commitments, TASK-P14-009 ---------------------------------------------------------- */

/**
 * The effective savings rate by billing month, FEAT-087. Scoped as the bill is, so it narrows to a
 * chosen account like every cost read; the screen's headline and the overview's tile read it, and
 * nothing computes the rate a second way.
 */
export function useSavingsRate(months = 12) {
  return useRead<ApiSavingsRate>(
    ['commitment-savings-rate', months],
    '/api/v1/commitments/savings-rate',
    `/api/v1/commitments/savings-rate?months=${String(months)}`,
  );
}

/**
 * What the payer holds, what ends when, and what to buy: the payer's alone, ADR-0025. The API
 * answers a narrowed reader with a 404 that says so, so these are read only when the caller says
 * the reader's scope is the whole organization, and the screen says why otherwise.
 */
export function useCommitmentInventory(enabled: boolean) {
  return useRead<ApiCommitmentInventory>(
    ['commitment-inventory'],
    '/api/v1/commitments/inventory',
    enabled ? '/api/v1/commitments/inventory' : '',
    { enabled },
  );
}

export function useCommitmentCalendar(enabled: boolean) {
  return useRead<ApiCommitmentCalendar>(
    ['commitment-calendar'],
    '/api/v1/commitments/calendar',
    enabled ? '/api/v1/commitments/calendar' : '',
    { enabled },
  );
}

const PLANS_KEY = ['commitment-plans'] as const;

export function useCommitmentPlans(enabled: boolean) {
  return useRead<ApiPurchasePlans>(
    PLANS_KEY,
    '/api/v1/commitments/plans',
    enabled ? '/api/v1/commitments/plans' : '',
    { enabled, title: 'Purchase plan' },
  );
}

/** A person's step in a plan's lifecycle, FEAT-090. Meter records it; a person buys in AWS. */
export type PlanStep = 'approve' | 'bought' | 'withdraw';

export function usePlanStep() {
  const client = useApi();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: ({
      planId,
      step,
      note,
    }: {
      readonly planId: string;
      readonly step: PlanStep;
      readonly note: string;
    }) =>
      client.post<ApiPurchasePlans>(
        `/api/v1/commitments/plans/${encodeURIComponent(planId)}/${step}`,
        { note },
      ),
    onSettled: () => queries.invalidateQueries({ queryKey: PLANS_KEY }),
  });
}
