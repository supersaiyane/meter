import { describe, expect, it } from 'vitest';

import { ApiError, createApiClient, EnvelopeError, fileNameOf, reasonOf } from '../client';

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
  it('returns a file under the name the server gave it, without asking for an envelope', async () => {
    const csv = 'Billing period,Effective Cost\n2026-08-01,4512.7113\n';
    const named: typeof fetch = () =>
      Promise.resolve(
        new Response(csv, {
          headers: {
            'Content-Disposition': 'attachment; filename="meter-showback-2026-10-05.csv"',
          },
        }),
      );
    const client = createApiClient({ token: 't', fetchImpl: named });
    const file = await client.getFile('/api/v1/cost/showback?format=csv');
    expect(file.name).toBe('meter-showback-2026-10-05.csv');
    expect(file.body.size).toBe(csv.length);
  });

  it('names a file for its format when the server gave it no name', async () => {
    const unnamed: typeof fetch = () => Promise.resolve(new Response('cells'));
    const client = createApiClient({ token: 't', fetchImpl: unnamed });
    await expect(client.getFile('/api/v1/cost/trend?format=xlsx')).resolves.toMatchObject({
      name: 'meter-export.xlsx',
    });
    expect(fileNameOf(null, '/api/v1/cost/trend')).toBe('meter-export.csv');
  });

  it('throws with the status when a file cannot be fetched', async () => {
    const client = createApiClient({
      token: 't',
      fetchImpl: respondWith('not in your scope', 403),
    });
    await expect(client.getFile('/api/v1/cost/showback?format=csv')).rejects.toMatchObject({
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

describe('the api client, for a saved view, FEAT-068', () => {
  function recording(status = 200, body: unknown = ENVELOPE) {
    const seen: { readonly url: string; readonly init: RequestInit | undefined }[] = [];
    const spy = ((url: string, init?: RequestInit) => {
      seen.push({ url, init });
      return Promise.resolve(fakeResponse(body, status));
    }) as unknown as typeof fetch;
    return { seen, client: createApiClient({ token: 'abc', fetchImpl: spy }) };
  }

  it('changes a view with PATCH and the change as a JSON body', async () => {
    const { seen, client } = recording();
    await client.patch('/api/v1/reports/views/v1', { name: 'Renamed' });
    expect(seen.map((one) => [one.url, one.init?.method, one.init?.body])).toEqual([
      ['/api/v1/reports/views/v1', 'PATCH', '{"name":"Renamed"}'],
    ]);
    const headers = seen[0]?.init?.headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('application/json');
    expect(headers.Authorization).toBe('Bearer abc');
  });

  it('deletes a view with DELETE and no body, and answers with the envelope', async () => {
    const { seen, client } = recording();
    const answer = await client.delete('/api/v1/reports/views/v1');
    expect(seen[0]?.init?.method).toBe('DELETE');
    expect(seen[0]?.init !== undefined && 'body' in seen[0].init).toBe(false);
    expect(answer).toEqual(ENVELOPE);
  });

  it('throws a refusal and says it in the words the API wrote for the reader', async () => {
    const said = 'Only the person who saved this view may rename, share or delete it.';
    const { client } = recording(403, { detail: said });
    const refusal: unknown = await client
      .patch('/x', { name: 'y' })
      .catch((error: unknown) => error);
    expect(refusal).toBeInstanceOf(ApiError);
    expect(reasonOf(refusal)).toBe(said);
  });

  it('says what a refused body was refused for, one message after another', () => {
    const listed = new ApiError(
      422,
      JSON.stringify({
        detail: [
          { msg: 'Value error, a saved view needs a name that is not blank' },
          { msg: 'Input should be a valid string' },
          { loc: ['body'] },
        ],
      }),
    );
    expect(reasonOf(listed)).toBe(
      'a saved view needs a name that is not blank Input should be a valid string',
    );
  });

  it('falls back to the body, then to the message, where there are no words to quote', () => {
    expect(reasonOf(new ApiError(502, 'Bad Gateway'))).toBe('Bad Gateway');
    expect(reasonOf(new ApiError(422, '{"detail":[]}'))).toBe('{"detail":[]}');
    expect(reasonOf(new ApiError(500, '{"detail":7}'))).toBe('{"detail":7}');
    expect(reasonOf(new Error('offline'))).toBe('offline');
    expect(reasonOf('nothing')).toBe('The request failed.');
  });

  it('refuses a change whose answer carries no envelope', async () => {
    const { client } = recording(200, { data: [] });
    await expect(client.delete('/api/v1/reports/views/v1')).rejects.toBeInstanceOf(
      EnvelopeError,
    );
  });
});
