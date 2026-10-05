import { describe, expect, it } from 'vitest';

import { ApiError, createApiClient, EnvelopeError } from '../client';

/** Just enough of a Response for the client to work with. */
function fakeResponse(body: unknown, status: number): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: 'x',
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(typeof body === 'string' ? body : JSON.stringify(body)),
  } as unknown as Response;
}

function respondWith(body: unknown, status = 200): typeof fetch {
  return () => Promise.resolve(fakeResponse(body, status));
}

const ENVELOPE = {
  data: [],
  meta: {
    as_of: null,
    collected_at: null,
    scope_coverage: { visible: 0, total: 0, is_partial: false, unit: 'accounts' },
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
      return Promise.resolve(fakeResponse(ENVELOPE, 200));
    }) as unknown as typeof fetch;
    const client = createApiClient({ token: 'abc', fetchImpl: spy });
    await client.get('/api/v1/me');
    expect((seen?.headers as Record<string, string>)['Authorization']).toBe('Bearer abc');
  });

  it('sends a question as a JSON body and never in the URL', async () => {
    // A URL is written into every access log on the way, so the question goes in the body.
    let url = '';
    let seen: RequestInit | undefined;
    const spy = ((target: string, init?: RequestInit) => {
      url = target;
      seen = init;
      return Promise.resolve(fakeResponse(ENVELOPE, 200));
    }) as unknown as typeof fetch;
    const client = createApiClient({ token: 'abc', fetchImpl: spy });
    await client.post('/api/v1/assistant/ask', { question: 'What did we spend?' });
    expect(url).toBe('/api/v1/assistant/ask');
    expect(seen?.method).toBe('POST');
    expect(seen?.body).toBe(JSON.stringify({ question: 'What did we spend?' }));
    expect((seen?.headers as Record<string, string>)['Content-Type']).toBe('application/json');
  });

  it('sends no body at all on an instruction that carries none', async () => {
    let seen: RequestInit | undefined;
    const spy = ((_url: string, init?: RequestInit) => {
      seen = init;
      return Promise.resolve(fakeResponse(ENVELOPE, 200));
    }) as unknown as typeof fetch;
    const client = createApiClient({ token: 'abc', fetchImpl: spy });
    await client.post('/api/v1/query/remediate/abc');
    expect(seen !== undefined && 'body' in seen).toBe(false);
    expect((seen?.headers as Record<string, string>)['Content-Type']).toBeUndefined();
  });
});

describe('the api client, for files and for writes that fail', () => {
  it('returns a file as its text, without asking it for an envelope', async () => {
    const csv = 'period,effective_cost\n2026-08-01,4512.7113\n';
    const client = createApiClient({ token: 't', fetchImpl: respondWith(csv) });
    await expect(client.getText('/api/v1/cost/export')).resolves.toBe(csv);
  });

  it('throws with the status when a file cannot be fetched', async () => {
    const client = createApiClient({
      token: 't',
      fetchImpl: respondWith('not in your scope', 403),
    });
    await expect(client.getText('/api/v1/cost/export')).rejects.toMatchObject({
      status: 403,
      detail: 'not in your scope',
    });
  });

  it('throws when a write fails, and names the status when the body says nothing', async () => {
    const client = createApiClient({ token: 't', fetchImpl: respondWith('', 409) });
    await expect(client.post('/api/v1/remediations/r-1/undo')).rejects.toMatchObject({
      status: 409,
      detail: 'x',
    });
  });

  it('refuses a write whose answer carries no envelope', async () => {
    const client = createApiClient({ token: 't', fetchImpl: respondWith({ accepted: true }) });
    await expect(client.post('/api/v1/remediations/r-1/undo')).rejects.toBeInstanceOf(
      EnvelopeError,
    );
  });
});
