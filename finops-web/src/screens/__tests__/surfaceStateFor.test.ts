import { describe, expect, it } from 'vitest';

import type { ApiMeta } from '../../api/types';
import { surfaceStateFor } from '../surfaceStateFor';

const READY = { isPending: false, isError: false, error: null } as never;

function meta(partial: Partial<ApiMeta> = {}): ApiMeta {
  return {
    as_of: '2026-08-29T08:00:00Z',
    collected_at: '2026-08-29T08:05:00Z',
    scope_coverage: { visible: 2, total: 3, is_partial: true, unit: 'workspaces' },
    degraded: true,
    failures: [],
    ...partial,
  };
}

function failure(collector: string, cause: string) {
  return {
    scope_key: `aws:1:eu-west-2`,
    collector,
    cause,
    remediation: 'do the thing',
    occurrences: 1,
    last_seen_at: '2026-08-29T08:05:00Z',
  };
}

describe('why part of an estate is missing', () => {
  it('names the cause the envelope reported', () => {
    // It said `outside your scope` whatever the cause, which sent a reader to
    // request a permission they already hold. ISS-152.
    const state = surfaceStateFor(
      READY,
      meta({ failures: [failure('query_audit', 'AccessDenied')] }),
      3,
      'none',
      'query_audit',
    );
    expect(state).toMatchObject({ kind: 'partial', missing: 1 });
    expect((state as { reason: string }).reason).toContain('AccessDenied');
  });

  it('names only the collector that feeds this surface', () => {
    // The envelope carries every open failure in the tenant. Listing all of
    // them made a findings gap read as caused by a throttled account health
    // check, which had nothing to do with it.
    const state = surfaceStateFor(
      READY,
      meta({
        failures: [
          failure('account_health', 'Throttled'),
          failure('query_audit', 'AccessDenied'),
        ],
      }),
      3,
      'none',
      'query_audit',
    );
    expect((state as { reason: string }).reason).toContain('AccessDenied');
    expect((state as { reason: string }).reason).not.toContain('Throttled');
  });

  it('falls back to entitlement when nothing explains the gap', () => {
    // With no failure to point at, the remaining explanation is that the reader
    // was not given the rest, and saying so is correct.
    const state = surfaceStateFor(READY, meta(), 3, 'none', 'query_audit');
    expect((state as { reason: string }).reason).toBe('outside your scope');
  });
});

describe('a request that failed', () => {
  it('names a Misconfigured failure as that, not as unrecognised', () => {
    // The local list of causes here had no Misconfigured, so a failure that said whose
    // problem it was reached the reader as UNRECOGNISED, which sent them to look for an API
    // change when the fix was one line of their own settings.
    const message = '409: Misconfigured: the aggregator named in the settings does not exist';
    const state = surfaceStateFor(
      { isPending: false, isError: true, error: new Error(message) },
      undefined,
      0,
      'none',
      'cost_focus',
    );
    expect(state).toEqual({ kind: 'failed', cause: 'Misconfigured', remediation: message });
  });

  it('still calls a failure it cannot classify drift', () => {
    const state = surfaceStateFor(
      { isPending: false, isError: true, error: new Error('500: something else') },
      undefined,
      0,
      'none',
      'cost_focus',
    );
    expect(state).toMatchObject({ kind: 'failed', cause: 'SchemaDrift' });
  });
});
