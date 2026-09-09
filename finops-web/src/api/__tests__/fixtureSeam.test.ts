import { describe, expect, it } from 'vitest';

import { FIXTURE_SURFACES, resolveSurface } from '../fixtureSeam';

describe('resolveSurface', () => {
  it('uses the fixture, and says so, for a declared fixture template', async () => {
    const read = resolveSurface(
      '/api/v1/query/findings',
      () => Promise.resolve(['real']),
      () => ['fixture'],
    );
    await expect(read()).resolves.toEqual({ data: ['fixture'], source: 'fixture' });
  });

  it('matches a parameterised template rather than a concrete url', async () => {
    const read = resolveSurface(
      '/api/v1/query/findings/{id}',
      () => Promise.resolve(['real']),
      () => ['fixture'],
    );
    await expect(read()).resolves.toEqual({ data: ['fixture'], source: 'fixture' });
  });

  it('uses the route, and says so, for any other template', async () => {
    const read = resolveSurface(
      '/api/v1/accounts',
      () => Promise.resolve(['real']),
      () => ['fixture'],
    );
    await expect(read()).resolves.toEqual({ data: ['real'], source: 'route' });
  });

  it('lets a route failure surface rather than falling back to the fixture', async () => {
    // A resolver that fell back on error would render invented numbers during an
    // outage, which is the precise failure rule 5 of 12-UI-DESIGN prevents.
    const boom = (): Promise<string[]> => Promise.reject(new Error('AccessDenied'));
    const read = resolveSurface('/api/v1/accounts', boom, () => ['fixture']);
    await expect(read()).rejects.toThrow('AccessDenied');
  });

  it('declares every fixture template under the api prefix', () => {
    for (const template of FIXTURE_SURFACES) {
      expect(template.startsWith('/api/v1/')).toBe(true);
    }
  });
});
