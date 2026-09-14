import { useQuery } from '@tanstack/react-query';

import { useApi } from './apiContext';
import { resolveSurface, type Resolved } from './fixtureSeam';
import {
  queryFindingDetailFixture,
  queryFindingsFixture,
  queryGroupsFixture,
  surfaceInstancesFixture,
  enforcementActionsFixture,
} from './fixtures/query';
import type {
  Account,
  ApiEnvelope,
  ApiQueryFinding,
  ApiQueryGroup,
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

export function useQueryGroups() {
  return useQuerySurface<ApiQueryGroup[]>(
    ['query-groups'],
    '/api/v1/query/groups',
    '/api/v1/query/groups',
    queryGroupsFixture,
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
