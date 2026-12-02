import { useQuery } from '@tanstack/react-query';

import { useApi } from './apiContext';
import type { Account, ApiEnvelope, Freshness, PlatformCost, Run } from './types';
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
