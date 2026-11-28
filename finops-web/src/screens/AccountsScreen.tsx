import { useMemo, useState } from 'react';

import { useAccounts } from '../api/queries';
import type { Account } from '../api/types';
import { DataTable } from '../components/DataTable';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
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

export function AccountsScreen() {
  const query = useAccounts();
  const [filter, setFilter] = useState<Filter>('All');
  useReportMeta('accounts', query.data?.meta);

  const rows = useMemo(
    () => (query.data?.data ?? []).filter((account) => matches(account, filter)),
    [query.data, filter],
  );

  const state = surfaceStateFor(query, query.data?.meta, rows.length, filter, 'account_health');

  return (
    <section aria-label="Accounts">
      <div role="group" aria-label="Filter by role health">
        {FILTERS.map((name) => (
          <button
            key={name}
            type="button"
            aria-pressed={filter === name}
            onClick={() => {
              setFilter(name);
            }}
          >
            {name.replace('_', ' ').toLowerCase()}
          </button>
        ))}
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
