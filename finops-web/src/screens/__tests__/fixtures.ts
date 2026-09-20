import type { Account, ApiEnvelope, ApiMeta } from '../../api/types';
import type { ApiClient } from '../../api/client';
import type { FlatNode } from '../../components/orgNodes';

export function metaOf(partial: Partial<ApiMeta> = {}): ApiMeta {
  return {
    as_of: '2026-08-27T09:00:00Z',
    collected_at: '2026-08-27T09:30:00Z',
    scope_coverage: { visible: 2, total: 2, is_partial: false, unit: 'accounts' },
    degraded: false,
    failures: [],
    ...partial,
  };
}

export function accountOf(id: string, health: string): Account {
  return {
    provider: 'aws',
    account_id: id,
    name: `name-${id}`,
    status: 'ACTIVE',
    role_health: health,
    role_health_checked_at: '2026-08-27T09:00:00Z',
    role_health_error: health === 'HEALTHY' ? null : 'the trust policy names another principal',
    as_of: '2026-08-27T09:00:00Z',
    collected_at: '2026-08-27T09:30:00Z',
  };
}

export const TREE: FlatNode[] = [
  {
    node_id: 'r-root',
    node_type: 'ROOT',
    parent_node_id: null,
    name: 'root',
    path: '/r-root',
    depth: 0,
    reachable: true,
  },
  {
    node_id: '111122223333',
    node_type: 'ACCOUNT',
    parent_node_id: 'r-root',
    name: 'production',
    path: '/r-root/111122223333',
    depth: 1,
    reachable: true,
  },
  {
    node_id: '444455556666',
    node_type: 'ACCOUNT',
    parent_node_id: 'r-root',
    name: 'finance',
    path: '/r-root/444455556666',
    depth: 1,
    reachable: false,
  },
];

/**
 * A client that answers a fixed envelope per path, or fails.
 *
 * `posted` records what was written, so a test can assert that a control which
 * should not have called anything did not, which is the half of a refusal that
 * an assertion on the rendering alone would miss.
 */
export const posted: string[] = [];

export function clientReturning(
  answers: Readonly<Record<string, ApiEnvelope<unknown>>>,
  failure?: Error,
  /**
   * Answers for `getText`, which serves the one route without an envelope. Its own
   * map rather than a union in `answers`, because a stub that guessed whether a
   * value was a file or a payload would guess wrong exactly when a test cared.
   */
  files: Readonly<Record<string, string>> = {},
): ApiClient {
  return {
    getText: (path: string): Promise<string> => {
      if (failure) return Promise.reject(failure);
      const answer = files[path];
      if (answer === undefined) {
        return Promise.reject(new Error(`no file stub for ${path}`));
      }
      return Promise.resolve(answer);
    },
    post: <T>(path: string): Promise<ApiEnvelope<T>> => {
      posted.push(path);
      if (failure) return Promise.reject(failure);
      const answer = answers[path];
      if (answer === undefined) {
        return Promise.reject(new Error(`no stub for ${path}`));
      }
      return Promise.resolve(answer as ApiEnvelope<T>);
    },
    get: <T>(path: string): Promise<ApiEnvelope<T>> => {
      if (failure) return Promise.reject(failure);
      const answer = answers[path];
      if (answer === undefined) {
        return Promise.reject(new Error(`no stub for ${path}`));
      }
      return Promise.resolve(answer as ApiEnvelope<T>);
    },
  };
}
