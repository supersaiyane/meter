import { describe, expect, it } from 'vitest';

import { FIXTURE_SURFACES, resolveSurface } from '../fixtureSeam';

describe('resolveSurface', () => {
  it('uses the fixture, and says so, for a declared fixture template', async () => {
    // Enforcement, because findings went live with TASK-P2-021 and left the
    // set. A template here has to be one that is actually still invented.
    const read = resolveSurface(
      '/api/v1/query/enforcement',
      () => Promise.resolve(['real']),
      () => ['fixture'],
    );
    await expect(read()).resolves.toEqual({ data: ['fixture'], source: 'fixture' });
  });

  it('compares the whole template, so a live route is never served a fixture', async () => {
    // The parameterised case is now covered by
    // tests/api/test_fixture_surfaces.py, which compares route shapes with
    // parameter names normalised. That guard caught this exact mismatch:
    // `{id}` here against `{finding_id}` on the route.
    const read = resolveSurface(
      '/api/v1/query/findings',
      () => Promise.resolve(['real']),
      () => ['fixture'],
    );
    await expect(read()).resolves.toEqual({ data: ['real'], source: 'route' });
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
