import { useRuns } from '../api/queries';
import type { Run } from '../api/types';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import { TypedError } from '../components/TypedError';
import type { Cause } from '../components/provenance';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Runs, per collector and per scope, with their typed causes.
 *
 * The column that matters is the last one, and ISS-015 is the whole reason it
 * exists. A run that wrote nothing because there was nothing to write shows a
 * zero. A run that wrote nothing because it was refused shows the refusal and
 * no number at all. If those two looked alike, every failure in the product
 * would read as free.
 */

const KNOWN = new Set<string>([
  'AccessDenied',
  'Throttled',
  'NotOptedIn',
  'Unreachable',
  'SchemaDrift',
]);

function itemsCell(run: Run) {
  const freshness = {
    asOf: new Date(run.started_at),
    collectedAt: new Date(run.finished_at ?? run.started_at),
  };
  if (run.error_type !== null && KNOWN.has(run.error_type)) {
    // No numeral. Not zero, not a dash, not blank.
    return (
      <TypedError
        cause={run.error_type as Exclude<Cause, 'NoData'>}
        remediation={run.error_detail ?? 'See the run detail.'}
      />
    );
  }
  return (
    <Figure
      value={{ kind: 'measured', amount: run.items_written }}
      freshness={freshness}
      unit="count"
    />
  );
}

const COLUMNS: readonly Column<Run>[] = [
  { key: 'collector', header: 'Collector', render: (row) => row.collector },
  { key: 'scope', header: 'Scope', render: (row) => row.scope_key },
  {
    key: 'status',
    header: 'Status',
    // PARTIAL is the normal outcome at three hundred accounts. It is not an
    // error state and it must never render as success.
    render: (row) => <span data-status={row.status}>{row.status.toLowerCase()}</span>,
  },
  { key: 'items', header: 'Items written', render: itemsCell, numeric: true },
];

export function IngestScreen() {
  const query = useRuns();
  useReportMeta('runs', query.data?.meta);
  const rows = query.data?.data ?? [];
  const state = surfaceStateFor(query, query.data?.meta, rows.length, 'none', 'ingest');

  return (
    <section aria-label="Ingest runs">
      <StateBoundary state={state}>
        <DataTable
          rows={rows}
          columns={COLUMNS}
          rowKey={(row) => row.run_id}
          caption="Recent collection runs"
        />
      </StateBoundary>
    </section>
  );
}
