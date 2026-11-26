import { describe, expect, it } from 'vitest';

import { ApiError, createApiClient, EnvelopeError } from '../client';

function respondWith(body: unknown, status = 200): typeof fetch {
  return (() =>
    Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      statusText: 'x',
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(typeof body === 'string' ? body : JSON.stringify(body)),
    } as Response)) as unknown as typeof fetch;
}

const ENVELOPE = {
  data: [],
  meta: {
    as_of: null,
    collected_at: null,
    scope_coverage: { visible: 0, total: 0, is_partial: false },
    degraded: true,
    failures: [],
  },
};

describe('the api client', () => {
  it('returns the envelope when the response carries one', async () => {
    const client = createApiClient({ token: 't', fetchImpl: respondWith(ENVELOPE) });
    const result = await client.get('/api/v1/accounts');
    expect(result.meta.degraded).toBe(true);
  });

  it('throws rather than returning an empty result when a request fails', async () => {
    // An empty list where a request failed is indistinguishable from an
    // organization with nothing in it.
    const client = createApiClient({ token: 't', fetchImpl: respondWith('no', 500) });
    await expect(client.get('/api/v1/accounts')).rejects.toBeInstanceOf(ApiError);
  });

  it('refuses a response with no meta envelope', async () => {
    // A screen cannot render those numbers honestly, so they never reach it.
    const client = createApiClient({ token: 't', fetchImpl: respondWith({ data: [1, 2] }) });
    await expect(client.get('/api/v1/accounts')).rejects.toBeInstanceOf(EnvelopeError);
  });

  it('sends the caller token as a bearer credential', async () => {
    let seen: RequestInit | undefined;
    const spy = ((_url: string, init?: RequestInit) => {
      seen = init;
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: 'ok',
        json: () => Promise.resolve(ENVELOPE),
        text: () => Promise.resolve(''),
      } as Response);
    }) as unknown as typeof fetch;
    const client = createApiClient({ token: 'abc', fetchImpl: spy });
    await client.get('/api/v1/me');
    expect((seen?.headers as Record<string, string>)['Authorization']).toBe('Bearer abc');
  });
});
