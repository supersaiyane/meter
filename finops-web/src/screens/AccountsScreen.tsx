import { useMemo } from 'react';

import { useAccounts, useCostByAccount, useFreshness } from '../api/queries';
import { Heatmap } from '../components/charts';
import { ChartPanel } from '../components/ChartPanel';
import { RankedBars } from '../components/RankedBars';
import type { Account } from '../api/types';
import { DataTable } from '../components/DataTable';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useFilters } from '../shell/filters';
import { useReportMeta } from '../shell/metaRegistry';
import { ACCOUNT_FILTERS } from '../shell/sections';
import { healthGrid } from './accountHealth';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Accounts, filterable by role health, because broken onboarding is the thing
 * somebody comes to this screen to find.
 *
 * "Broken" is one filter rather than four, so finding every account that cannot
 * be read is a single click. Making somebody select four states in turn is how
 * a screen that technically supports the question fails to answer it.
 */

const FILTERS = [
  'All',
  'Broken',
  'HEALTHY',
  'ACCESS_DENIED',
  'NOT_DEPLOYED',
  'THROTTLED',
  'UNKNOWN',
] as const;
type Filter = (typeof FILTERS)[number];

function isFilter(value: string): value is Filter {
  return (FILTERS as readonly string[]).includes(value);
}

function matches(account: Account, filter: Filter): boolean {
  if (filter === 'All') return true;
  if (filter === 'Broken') return account.role_health !== 'HEALTHY';
  return account.role_health === filter;
}

const COLUMNS: readonly Column<Account>[] = [
  { key: 'account_id', header: 'Account', render: (row) => row.account_id },
  { key: 'name', header: 'Name', render: (row) => row.name },
  { key: 'status', header: 'Status', render: (row) => row.status },
  {
    key: 'role_health',
    header: 'Role health',
    render: (row) =>
      row.role_health === 'HEALTHY' ? (
        <span>healthy</span>
      ) : (
        // The provider's own words, so nobody has to read a log to act.
        <span className="meter-failure">
          {row.role_health.replace('_', ' ').toLowerCase()}
          {row.role_health_error === null ? '' : `. ${row.role_health_error}`}
        </span>
      ),
  },
];

/** Accounts named in the spend ranking before the rest are summed into one row. */
const TOP_ACCOUNTS = 10;

export function AccountsScreen() {
  const query = useAccounts();
  const { values, set } = useFilters(ACCOUNT_FILTERS);
  // From the address, so a link can land on the broken accounts. A value that is not a
  // filter here shows them all, and the pressed chip says so rather than the address.
  const filter: Filter = isFilter(values.status) ? values.status : 'All';
  useReportMeta('accounts', query.data?.meta);

  const rows = useMemo(
    () => (query.data?.data ?? []).filter((account) => matches(account, filter)),
    [query.data, filter],
  );

  const state = surfaceStateFor(query, query.data?.meta, rows.length, filter, 'account_health');

  const freshness = useFreshness();
  useReportMeta('accounts-freshness', freshness.data?.meta);
  const grid = useMemo(
    () => healthGrid(query.data?.data ?? [], freshness.data?.data ?? []),
    [query.data, freshness.data],
  );
  const freshnessState = surfaceStateFor(
    freshness,
    freshness.data?.meta,
    grid.rows.length,
    'none',
    'freshness',
  );

  const spend = useCostByAccount();
  const spendEnvelope = spend.data?.data;
  useReportMeta('accounts-spend', spendEnvelope?.meta);
  const slices = spendEnvelope?.data ?? [];
  const spendState = surfaceStateFor(
    spend,
    spendEnvelope?.meta,
    slices.length,
    'none',
    'cost_focus_daily',
  );

  return (
    <section aria-label="Accounts">
      <div role="group" aria-label="Filter by role health">
        {FILTERS.map((name) => (
          <button
            key={name}
            type="button"
            aria-pressed={filter === name}
            onClick={() => {
              set('status', name === 'All' ? '' : name);
            }}
          >
            {name.replace('_', ' ').toLowerCase()}
          </button>
        ))}
      </div>
      <div data-testid="chart-row">
        <ChartPanel
          id="accounts-spend"
          title="Where the money is"
          caption="This period's Effective Cost by account, the ten largest and the rest together"
        >
          <StateBoundary state={spendState} coverageShownElsewhere>
            <RankedBars
              points={slices.map((row) => ({
                label: row.name,
                value: Number(row.effective_cost),
              }))}
              provenance="measured"
              format={(value) =>
                `$${value.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`
              }
              limit={TOP_ACCOUNTS}
              restLabel="All other accounts"
            />
          </StateBoundary>
        </ChartPanel>
        <ChartPanel
          id="accounts-health"
          title="How fresh each account is"
          caption="Time since each collector last read the account, in that collector's own interval: under one is on time, two is a run missed. An outline has no age to count. The stalest accounts first"
        >
          <StateBoundary state={freshnessState} coverageShownElsewhere>
            <Heatmap
              rows={grid.rows}
              columns={grid.columns}
              values={grid.values}
              provenance="measured"
              label="Intervals since each collector last read each account"
              format={(value) => `${value.toFixed(1)} intervals`}
              missing="no age to count"
            />
            {grid.more === 0 ? null : (
              <p data-testid="accounts-health-rest">
                {grid.restOnTime
                  ? `The other ${String(grid.more)} accounts are on time with every collector`
                  : `${String(grid.more)} more accounts, and some of them are late too. The Freshness screen lists every one`}
              </p>
            )}
          </StateBoundary>
        </ChartPanel>
      </div>
      <StateBoundary state={state}>
        <DataTable
          rows={rows}
          columns={COLUMNS}
          rowKey={(row) => `${row.provider}:${row.account_id}`}
          caption="Accounts in scope"
        />
      </StateBoundary>
    </section>
  );
}
