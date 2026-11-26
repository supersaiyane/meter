import { describe, expect, it } from 'vitest';

import type { ApiMeta } from '../../api/types';
import { aggregate, EMPTY_AGGREGATE } from '../metaStore';

function meta(partial: Partial<ApiMeta> = {}): ApiMeta {
  return {
    as_of: '2026-08-27T09:00:00Z',
    collected_at: '2026-08-27T09:30:00Z',
    scope_coverage: { visible: 5, total: 5, is_partial: false },
    degraded: false,
    failures: [],
    ...partial,
  };
}

describe('aggregate', () => {
  it('reports the oldest as_of in view, not the newest', () => {
    // A page whose oldest panel is nine hours old is a nine hour old page.
    const combined = aggregate([
      meta({ as_of: '2026-08-27T09:00:00Z' }),
      meta({ as_of: '2026-08-27T01:00:00Z' }),
    ]);
    expect(combined.asOf).toBe('2026-08-27T01:00:00Z');
  });

  it('reports the oldest collected_at too', () => {
    const combined = aggregate([
      meta({ collected_at: '2026-08-27T09:30:00Z' }),
      meta({ collected_at: '2026-08-27T02:30:00Z' }),
    ]);
    expect(combined.collectedAt).toBe('2026-08-27T02:30:00Z');
  });

  it('takes the most conservative coverage', () => {
    // If one panel sees two accounts and another sees five, the page cannot
    // claim five.
    const combined = aggregate([
      meta({ scope_coverage: { visible: 2, total: 5, is_partial: true } }),
      meta({ scope_coverage: { visible: 5, total: 5, is_partial: false } }),
    ]);
    expect(combined.visible).toBe(2);
    expect(combined.total).toBe(5);
    expect(combined.isPartial).toBe(true);
  });

  it('is degraded when any panel is', () => {
    expect(aggregate([meta(), meta({ degraded: true })]).degraded).toBe(true);
  });

  it('reports one row for the same break seen by three panels', () => {
    const failure = {
      scope_key: 'aws:111122223333:eu-west-1',
      collector: 'account_health',
      cause: 'AccessDenied',
      remediation: 'Check the StackSet.',
      occurrences: 3,
      last_seen_at: '2026-08-27T09:00:00Z',
    };
    const combined = aggregate([
      meta({ failures: [failure] }),
      meta({ failures: [failure] }),
      meta({ failures: [failure] }),
    ]);
    expect(combined.failures).toHaveLength(1);
  });

  it('reports nothing collected as null rather than as a date', () => {
    const combined = aggregate([meta({ as_of: null, collected_at: null })]);
    expect(combined.asOf).toBeNull();
  });

  it('returns the empty aggregate when no surface has reported', () => {
    expect(aggregate([])).toEqual(EMPTY_AGGREGATE);
  });
});
