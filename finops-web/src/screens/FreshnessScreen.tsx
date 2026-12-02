import { useFreshness } from '../api/queries';
import type { Freshness } from '../api/types';
import { DataTable } from '../components/DataTable';
import { StateBoundary } from '../components/StateBoundary';
import { formatAge } from '../components/provenance';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * How stale each collector is, per scope, against its own cadence.
 *
 * A daily collector six hours old is fine and an hourly one six hours old is
 * not, so the cadence is shown beside the age. A single staleness threshold
 * across collectors would call one of those wrong every time.
 */
const COLUMNS: readonly Column<Freshness>[] = [
  { key: 'collector', header: 'Collector', render: (row) => row.collector },
  { key: 'scope', header: 'Scope', render: (row) => row.scope_key },
  { key: 'age', header: 'Age', render: (row) => formatAge(row.age_seconds), numeric: true },
  {
    key: 'cadence',
    header: 'Cadence',
    numeric: true,
    render: (row) =>
      row.cadence_seconds === null
        ? // An unknown cadence is not a healthy one, and saying so beats a blank.
          'not scheduled'
        : `${String(Math.round(row.cadence_seconds / 60))} min`,
  },
  {
    key: 'stale',
    header: 'State',
    render: (row) =>
      row.is_stale ? <span className="meter-stale">stale</span> : <span>current</span>,
  },
];

export function FreshnessScreen() {
  const query = useFreshness();
  useReportMeta('freshness', query.data?.meta);
  const rows = query.data?.data ?? [];
  const state = surfaceStateFor(query, query.data?.meta, rows.length, 'none', 'freshness');

  return (
    <section aria-label="Freshness">
      <StateBoundary state={state}>
        <DataTable
          rows={rows}
          columns={COLUMNS}
          rowKey={(row) => `${row.collector}|${row.scope_key}`}
          caption="Collector freshness"
        />
      </StateBoundary>
    </section>
  );
}
