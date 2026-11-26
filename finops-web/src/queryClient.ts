import { QueryClient } from '@tanstack/react-query';

/**
 * Retries are off deliberately.
 *
 * A retry hides a failure for as long as it takes to give up, and this
 * product's whole claim is that a failure is visible the moment it happens. The
 * backend already retries what is worth retrying, with backoff, and reports in
 * its envelope what it could not do.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false, staleTime: 30_000 },
    },
  });
}
