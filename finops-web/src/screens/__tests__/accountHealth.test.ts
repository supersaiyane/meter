import { describe, expect, it } from 'vitest';

import type { Freshness } from '../../api/types';
import { HEALTH_ROWS, healthGrid } from '../accountHealth';
import { accountOf } from './fixtures';

/** One collector's freshness for one scope, an hour apart by default. */
function fresh(
  collector: string,
  scopeKey: string,
  age: number | null,
  cadence: number | null = 3600,
): Freshness {
  return {
    collector,
    scope_key: scopeKey,
    as_of: age === null ? null : '2026-10-06T06:00:00Z',
    cadence_seconds: cadence,
    age_seconds: age,
    state: age === null ? 'never_collected' : 'current',
    cause: null,
    is_stale: age !== null && cadence !== null && age > cadence,
  };
}

describe('the account health grid', () => {
  const accounts = [accountOf('111122223333', 'HEALTHY'), accountOf('444455556666', 'HEALTHY')];

  it('counts age in each collector own interval, the stalest region winning', () => {
    const grid = healthGrid(accounts, [
      fresh('inventory', 'aws:111122223333:eu-west-1', 1800),
      fresh('inventory', 'aws:111122223333:us-east-1', 7200),
      fresh('cost_focus', 'aws:111122223333', 3600, 86_400),
      fresh('inventory', 'aws:444455556666:eu-west-1', 900),
    ]);
    expect(grid.columns).toEqual(['cost_focus', 'inventory']);
    // The account two intervals late on inventory comes first.
    expect(grid.rows).toEqual(['name-111122223333', 'name-444455556666']);
    expect(grid.values[0]?.[0]).toBeCloseTo(3600 / 86_400, 6);
    expect(grid.values[0]?.[1]).toBe(2);
    expect(grid.values[1]).toEqual([null, 0.25]);
  });

  it('draws a pair with no age or no interval as an outline, never as late', () => {
    const grid = healthGrid(accounts, [
      fresh('inventory', 'aws:111122223333', null),
      fresh('digests', 'aws:111122223333', 99_999, null),
      fresh('inventory', 'aws:444455556666', 1800),
    ]);
    // Neither of the first account's pairs has an age to count, so the late one leads.
    expect(grid.rows[0]).toBe('name-444455556666');
    expect(grid.values[1]).toEqual([null, null]);
  });

  it('leaves out scopes that are not accounts, and names two accounts that share a name', () => {
    const twins = [
      { ...accountOf('111122223333', 'HEALTHY'), name: 'Platform' },
      { ...accountOf('444455556666', 'HEALTHY'), name: 'Platform' },
    ];
    const grid = healthGrid(twins, [
      fresh('org_tree', 'organization', 60),
      fresh('inventory', 'aws:111122223333', 60),
      fresh('inventory', 'aws:444455556666', 30),
    ]);
    expect(grid.columns).toEqual(['inventory']);
    expect(grid.rows).toEqual(['Platform 111122223333', 'Platform 444455556666']);
  });

  it('draws the stalest accounts and says whether the rest are on time', () => {
    const many = Array.from({ length: HEALTH_ROWS + 3 }, (_, index) =>
      accountOf(String(100_000_000_000 + index), 'HEALTHY'),
    );
    const late = healthGrid(
      many,
      many.map((account, index) =>
        fresh('inventory', `aws:${account.account_id}`, index === 0 ? 900 : 3600 * 3),
      ),
    );
    expect(late.rows).toHaveLength(HEALTH_ROWS);
    expect(late.more).toBe(3);
    expect(late.restOnTime).toBe(false);

    const quiet = healthGrid(
      many,
      many.map((account, index) =>
        fresh('inventory', `aws:${account.account_id}`, index < HEALTH_ROWS ? 7200 : 600),
      ),
    );
    expect(quiet.restOnTime).toBe(true);
  });
});
