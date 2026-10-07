import { useRuns } from '../api/queries';
import { collectorName, runStatusName } from '../components/displayNames';
import type { Run } from '../api/types';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import { TypedError } from '../components/TypedError';
import { isFailureCause } from '../components/provenance';
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

function itemsCell(run: Run) {
  const freshness = {
    asOf: new Date(run.started_at),
    collectedAt: new Date(run.finished_at ?? run.started_at),
  };
  if (run.error_type !== null && isFailureCause(run.error_type)) {
    // No numeral. Not zero, not a dash, not blank.
    return (
      <TypedError
        cause={run.error_type}
        remediation={run.error_detail ?? 'See the run detail.'}
      />
    );
  }
  if (run.error_type !== null && run.error_type !== 'NoData') {
    // A cause this screen has no word for is still a failure, so it is drift, which is loud,
    // and its items are not drawn: a failure never reads as a figure. NoData is the one cause
    // whose zero is a true zero, and it falls through to the number below.
    return (
      <TypedError
        cause="SchemaDrift"
        remediation={`${run.error_type} is not a cause this screen knows. ${run.error_detail ?? 'See the run detail.'}`}
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
  { key: 'collector', header: 'Collector', render: (row) => collectorName(row.collector) },
  { key: 'scope', header: 'Scope', render: (row) => row.scope_key },
  {
    key: 'status',
    header: 'Status',
    // PARTIAL is the normal outcome at three hundred accounts. It is not an
    // error state and it must never render as success.
    render: (row) => <span data-status={row.status}>{runStatusName(row.status)}</span>,
  },
  { key: 'items', header: 'Items written', render: itemsCell, numeric: true },
];

export function IngestScreen() {
  const query = useRuns();
  useReportMeta('runs', query.data?.meta);
  const rows = query.data?.data ?? [];
  const state = surfaceStateFor(query, query.data?.meta, rows.length, 'none', 'ingest');

  return (
    <section aria-label="Ingestion runs">
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
