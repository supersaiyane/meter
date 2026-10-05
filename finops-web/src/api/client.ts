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

/** A file the server wrote, under the name it gave it. */
export interface DownloadedFile {
  readonly name: string;
  readonly body: Blob;
}

/**
 * The name the server gave a file, or one built from what was asked for when the header is
 * missing, which a proxy that strips it would make the case.
 */
export function fileNameOf(disposition: string | null, path: string): string {
  const named = disposition === null ? null : /filename="([^"]+)"/.exec(disposition);
  if (named?.[1] !== undefined) {
    return named[1];
  }
  const at = path.indexOf('?');
  const format = at === -1 ? null : new URLSearchParams(path.slice(at + 1)).get('format');
  return `meter-export.${format ?? 'csv'}`;
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
     * A file rather than a payload: an export, FEAT-067.
     *
     * Separate from `get` because it deliberately does not check for the envelope. An export
     * is a view's own rows, written as a workbook or a CSV by the server behind the same scope
     * dependency and guard as the screen, and what the envelope says travels inside the file.
     * Kept as its own method rather than a flag on `get`, so a route that should carry an
     * envelope cannot lose its check by passing an argument.
     */
    async getFile(path: string): Promise<DownloadedFile> {
      const response = await fetchImpl(`${baseUrl}${path}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new ApiError(response.status, detail || response.statusText);
      }
      return {
        name: fileNameOf(response.headers.get('Content-Disposition'), path),
        body: await response.blob(),
      };
    },

    /**
     * The only writing method. It sends a body only when given one.
     *
     * Most writes this product makes are instructions rather than documents:
     * remediate this finding, undo that change. What to write is decided by the
     * server from the finding it already holds, so a body would be a second
     * description of the same thing and a chance for the two to disagree. Those
     * calls pass no body and send none, not even an empty one.
     *
     * A question to the assistant is the exception, because the question is the
     * document. It travels as JSON in the body and never in the URL, where it
     * would be written into every access log on the way.
     */
    async post<T>(path: string, body?: unknown): Promise<ApiEnvelope<T>> {
      const response = await fetchImpl(`${baseUrl}${path}`, {
        method: 'POST',
        headers:
          body === undefined
            ? { Authorization: `Bearer ${token}` }
            : { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
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
