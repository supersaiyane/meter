import type { Account, Freshness } from '../api/types';

/**
 * How fresh each account's data is, collector by collector, for the health heatmap on Accounts.
 *
 * Age is counted in the collector's own interval, because six hours is on time for a daily
 * collector and three runs missed for a two hourly one: under one is on time, and two means a
 * run was missed. A collector that reads an account in several regions is as stale as its
 * stalest region. A pair that has never collected, or that nothing schedules, has no age to
 * count, as the Freshness screen says, so it is drawn as an outline and never ranked as late.
 */

export interface HealthGrid {
  readonly rows: readonly string[];
  readonly columns: readonly string[];
  /** Intervals since the last collection, null where there is no age or no interval. */
  readonly values: readonly (readonly (number | null)[])[];
  /** Accounts read but not drawn, because the stalest are the ones worth a row. */
  readonly more: number;
  /** True when every account not drawn is on time with every collector. */
  readonly restOnTime: boolean;
}

/** Accounts the heatmap draws, the stalest first. */
export const HEALTH_ROWS = 12;

function intervals(one: Freshness): number | null {
  return one.age_seconds === null || one.cadence_seconds === null || one.cadence_seconds <= 0
    ? null
    : one.age_seconds / one.cadence_seconds;
}

/** The later of two ages, where a pair with no age gives way to one that has one. */
function later(before: number | null | undefined, age: number | null): number | null {
  if (before === undefined || before === null) {
    return age;
  }
  return age === null ? before : Math.max(before, age);
}

/** The account a scope key belongs to: provider, account and, for a regional slice, region. */
function accountOf(scopeKey: string): string {
  return scopeKey.split(':').slice(0, 2).join(':');
}

/** The latest of an account's ages, nought where none of its pairs has one. */
function stalest(byCollector: ReadonlyMap<string, number | null>): number {
  return Math.max(0, ...[...byCollector.values()].map((age) => age ?? 0));
}

export function healthGrid(
  accounts: readonly Account[],
  freshness: readonly Freshness[],
): HealthGrid {
  const keyOf = (account: Account): string => `${account.provider}:${account.account_id}`;
  const repeated = new Set(
    accounts
      .map((account) => account.name)
      .filter((name, index, names) => names.indexOf(name) !== index),
  );
  // A name two accounts share carries its number, so two rows never read as one account.
  const named = new Map(
    accounts.map((account) => [
      keyOf(account),
      repeated.has(account.name) ? `${account.name} ${account.account_id}` : account.name,
    ]),
  );
  const ages = new Map<string, Map<string, number | null>>();
  for (const one of freshness) {
    const account = accountOf(one.scope_key);
    if (!named.has(account)) {
      continue;
    }
    const byCollector = ages.get(account) ?? new Map<string, number | null>();
    byCollector.set(one.collector, later(byCollector.get(one.collector), intervals(one)));
    ages.set(account, byCollector);
  }
  const columns = [
    ...new Set([...ages.values()].flatMap((byCollector) => [...byCollector.keys()])),
  ].sort();
  const ranked = [...ages].sort((left, right) => stalest(right[1]) - stalest(left[1]));
  const drawn = ranked.slice(0, HEALTH_ROWS);
  const rest = ranked.slice(HEALTH_ROWS);
  return {
    rows: drawn.map(([account]) => named.get(account) ?? account),
    columns,
    values: drawn.map(([, byCollector]) =>
      columns.map((collector) => byCollector.get(collector) ?? null),
    ),
    more: rest.length,
    restOnTime: rest.every(([, byCollector]) => stalest(byCollector) <= 1),
  };
}
