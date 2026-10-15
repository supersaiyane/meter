import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useApi } from './apiContext';
import type {
  ApiCodeHostConnection,
  ApiEnvelope,
  ApiFix,
  ApiFixes,
  ApiMergePolicy,
  ApiRepositoryMappings,
} from './types';

/**
 * Fixes through pull requests, P15, TASK-P15-008: every fix asked for, asking for one, and the
 * three settings that decide where fixes go and which Meter may merge.
 *
 * Plain queries rather than `useQuerySurface`, because none of these is a table to export: each
 * route is exempt in `tests/api/test_export_routes.py` with its reason, and a surface would offer
 * the export menu on them.
 */

const FIXES_KEY = ['remediation-fixes'] as const;
const CONNECTION_KEY = ['remediation-connection'] as const;
const MAPPINGS_KEY = ['remediation-repositories'] as const;
const POLICY_KEY = ['remediation-merge-policy'] as const;

export const FIXES = '/api/v1/remediation/pull-requests';
export const CONNECTION = '/api/v1/remediation/connection';
export const REPOSITORIES = '/api/v1/remediation/repositories';
export const MERGE_POLICY = '/api/v1/remediation/merge-policy';

export function askPath(recommendationId: string): string {
  return `/api/v1/waste/recommendations/${encodeURIComponent(recommendationId)}/pull-request`;
}

/** Every fix in the reader's scope, the newest ask first, each with its steps. FEAT-092. */
export function useFixes() {
  const client = useApi();
  return useQuery<ApiEnvelope<ApiFixes>>({
    queryKey: FIXES_KEY,
    queryFn: () => client.get<ApiFixes>(FIXES),
  });
}

/** Ask for a recommendation's fix to be opened as a pull request, with an optional note. */
export function useAskForFix() {
  const client = useApi();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: ({
      recommendationId,
      note,
    }: {
      readonly recommendationId: string;
      readonly note: string;
    }) =>
      client.post<ApiFix>(
        askPath(recommendationId),
        note.trim() === '' ? {} : { note: note.trim() },
      ),
    onSettled: () => queries.invalidateQueries({ queryKey: FIXES_KEY }),
  });
}

/**
 * One of the organization's settings, read only for a reader whose scope covers it: the routes
 * answer a narrowed reader 404 with the reason, and the screen says the reason without asking.
 */
function useSetting<T>(key: readonly string[], path: string, enabled: boolean) {
  const client = useApi();
  return useQuery<ApiEnvelope<T>>({
    queryKey: key,
    queryFn: () => client.get<T>(path),
    enabled,
  });
}

function useChange<T, B>(key: readonly string[], path: string) {
  const client = useApi();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (body: B) => client.put<T>(path, body),
    onSettled: () => queries.invalidateQueries({ queryKey: key }),
  });
}

export function useCodeHostConnection(enabled: boolean) {
  return useSetting<ApiCodeHostConnection>(CONNECTION_KEY, CONNECTION, enabled);
}

export function useConnect() {
  return useChange<
    ApiCodeHostConnection,
    { readonly host: 'github'; readonly app_id: string; readonly key_secret_name: string }
  >(CONNECTION_KEY, CONNECTION);
}

export function useRepositoryMappings(enabled: boolean) {
  return useSetting<ApiRepositoryMappings>(MAPPINGS_KEY, REPOSITORIES, enabled);
}

export interface MappingIn {
  readonly state_reference: string;
  readonly repository: string;
  readonly base_branch: string;
  readonly folder: string;
}

export function useMapRepositories() {
  return useChange<ApiRepositoryMappings, { readonly mappings: readonly MappingIn[] }>(
    MAPPINGS_KEY,
    REPOSITORIES,
  );
}

export function useMergePolicy(enabled: boolean) {
  return useSetting<ApiMergePolicy>(POLICY_KEY, MERGE_POLICY, enabled);
}

export function useSetMergePolicy() {
  return useChange<
    ApiMergePolicy,
    { readonly classes: readonly string[]; readonly reason: string }
  >(POLICY_KEY, MERGE_POLICY);
}
