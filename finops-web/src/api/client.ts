import type { ApiEnvelope } from './types';

/**
 * The one way this application talks to the API.
 *
 * A failed request throws rather than returning an empty result. An empty list
 * rendered where a request failed is indistinguishable from an organization
 * with nothing in it, which is the same defect the backend spends its whole
 * error taxonomy preventing, arriving through the front door instead.
 *
 * The envelope is checked rather than assumed. A response without `meta` cannot
 * be rendered honestly, so it is refused here instead of reaching a screen that
 * would show its numbers with no provenance at all.
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`${String(status)}: ${detail}`);
    this.name = 'ApiError';
  }
}

export class EnvelopeError extends Error {
  constructor(readonly path: string) {
    super(`The response from ${path} carried no meta envelope`);
    this.name = 'EnvelopeError';
  }
}

function isEnvelope<T>(payload: unknown): payload is ApiEnvelope<T> {
  if (typeof payload !== 'object' || payload === null || !('meta' in payload)) {
    return false;
  }
  // The `in` check above already narrows payload, so no assertion is needed.
  const meta: unknown = payload.meta;
  return typeof meta === 'object' && meta !== null && 'scope_coverage' in meta;
}

export interface ApiClientOptions {
  readonly baseUrl?: string;
  readonly token: string;
  readonly fetchImpl?: typeof fetch;
}

export function createApiClient({ baseUrl = '', token, fetchImpl = fetch }: ApiClientOptions) {
  return {
    async get<T>(path: string): Promise<ApiEnvelope<T>> {
      const response = await fetchImpl(`${baseUrl}${path}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new ApiError(response.status, detail || response.statusText);
      }
      const payload: unknown = await response.json();
      if (!isEnvelope<T>(payload)) {
        throw new EnvelopeError(path);
      }
      return payload;
    },

    /**
     * A response that is a file rather than a payload.
     *
     * Separate from `get` because it deliberately does not check for the envelope.
     * The CSV export is the one route without one, and the reason is in
     * `ENVELOPE_EXEMPT`: a JSON wrapper round a CSV is a wrapper somebody has to
     * strip by hand. Its freshness travels as two columns in the file instead.
     *
     * Kept as its own method rather than a flag on `get`, so a route that should
     * carry an envelope cannot lose its check by passing an argument.
     */
    async getText(path: string): Promise<string> {
      const response = await fetchImpl(`${baseUrl}${path}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new ApiError(response.status, detail || response.statusText);
      }
      return response.text();
    },

    /**
     * The only writing method, and it sends no body.
     *
     * Every write this product makes is an instruction rather than a document:
     * remediate this finding, undo that change. What to write is decided by the
     * server from the finding it already holds, so a body would be a second
     * description of the same thing and a chance for the two to disagree.
     */
    async post<T>(path: string): Promise<ApiEnvelope<T>> {
      const response = await fetchImpl(`${baseUrl}${path}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new ApiError(response.status, detail || response.statusText);
      }
      const payload: unknown = await response.json();
      if (!isEnvelope<T>(payload)) {
        throw new EnvelopeError(path);
      }
      return payload;
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
