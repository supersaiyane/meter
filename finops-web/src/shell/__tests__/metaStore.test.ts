import { describe, expect, it } from 'vitest';

import type { ApiMeta } from '../../api/types';
import { aggregate, aggregateReports, EMPTY_AGGREGATE } from '../metaStore';

function meta(partial: Partial<ApiMeta> = {}): ApiMeta {
  return {
    as_of: '2026-08-27T09:00:00Z',
    collected_at: '2026-08-27T09:30:00Z',
    scope_coverage: { visible: 5, total: 5, is_partial: false, unit: 'accounts' },
    degraded: false,
    failures: [],
    ...partial,
  };
}

describe('the counted noun', () => {
  it('never renders a missing noun as the word undefined', () => {
    // A response that predates the field, or one from a version that never had
    // it, put `Showing 2 of 5 undefined` on the screen. A missing noun is not a
    // noun, and a coverage statement is the last place to print a placeholder.
    const older = meta({
      scope_coverage: { visible: 2, total: 5, is_partial: true } as never,
    });
    expect(aggregate([older]).unit).toBe('in view');
    expect(aggregate([older]).coverage[0]?.unit).toBe('in view');
  });

  it('takes the noun the route reported', () => {
    // The shell used to say `accounts` on every screen, and the query screens
    // count workspaces. A wrong noun in a coverage statement is a wrong claim.
    const workspaces = meta({
      scope_coverage: { visible: 2, total: 3, is_partial: true, unit: 'workspaces' },
    });
    expect(aggregate([workspaces]).unit).toBe('workspaces');
  });

  it('names neither when two surfaces count different things', () => {
    // Picking one would be a claim nothing on the page supports.
    const accounts = meta({
      scope_coverage: { visible: 1, total: 2, is_partial: true, unit: 'accounts' },
    });
    const workspaces = meta({
      scope_coverage: { visible: 2, total: 3, is_partial: true, unit: 'workspaces' },
    });
    expect(aggregate([accounts, workspaces]).unit).toBe('in view');
  });
});

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
      meta({ scope_coverage: { visible: 2, total: 5, is_partial: true, unit: 'accounts' } }),
      meta({ scope_coverage: { visible: 5, total: 5, is_partial: false, unit: 'accounts' } }),
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

describe('freshness stated beside each figure', () => {
  const own = meta({ as_of: null, collected_at: null });

  it('holds when every surface on the page says its figures carry their own', () => {
    const page = aggregateReports([
      { meta: own, freshness: 'per-figure' },
      { meta: own, freshness: 'per-figure' },
    ]);
    expect(page.freshnessPerFigure).toBe(true);
    // Nothing is made up for the page. The envelopes had no as_of, and neither does this.
    expect(page.asOf).toBeNull();
    expect(page.collectedAt).toBeNull();
  });

  it('does not hold beside a surface that states one freshness for its whole response', () => {
    // Its claim, oldest in view or not yet collected, is true of it and must stay on the strip.
    const page = aggregateReports([
      { meta: own, freshness: 'per-figure' },
      { meta: own, freshness: 'envelope' },
    ]);
    expect(page.freshnessPerFigure).toBe(false);
  });

  it('never holds for plain envelopes, which is every surface before P7', () => {
    expect(aggregate([own]).freshnessPerFigure).toBe(false);
    expect(aggregateReports([]).freshnessPerFigure).toBe(false);
  });
});
