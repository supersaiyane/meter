import { useMemo } from 'react';

import { useQueryFindings } from '../api/queries';
import type { ApiQueryFinding } from '../api/types';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { FixtureBand } from '../components/FixtureBand';
import { SeverityBadge, type Severity } from '../components/SeverityBadge';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import type { FigureValue, Freshness } from '../components/provenance';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Query findings, ranked by what they cost, per P2 spec section 9.1.
 *
 * Dense, because the reader is scanning for outliers rather than reading.
 *
 * `why` is a column of prose and not a tooltip. This list is read in tickets and
 * in screenshots pasted into them, and a tooltip is invisible in both. The
 * ranking says what to look at; the prose is what says what to do about it.
 */

// MiB, not GiB. `Figure` renders a count with no decimal places, so a one MiB
// scan expressed in GiB rounds to the numeral zero, and a query that scans a
// megabyte would read as a query that scans nothing. ISS-137 records the
// residual case, a scan under one MiB.
const MIB = 1024 ** 2;

function figureOf(finding: ApiQueryFinding, amount: number): FigureValue {
  // Anything the model produced is modelled. Only an observed execution count
  // is measured, and treating an unrecognised provenance as measured would be
  // the one direction of this mapping that overclaims.
  return finding.provenance === 'measured'
    ? { kind: 'measured', amount }
    : { kind: 'modelled', amount };
}

function severityOf(finding: ApiQueryFinding): Severity {
  const level = Math.min(5, Math.max(1, Math.round(finding.severity)));
  return level as Severity;
}

function secondsLabel(seconds: number | null): string {
  if (seconds === null) return 'not set';
  if (seconds % 86400 === 0) return `${String(seconds / 86400)} d`;
  if (seconds % 3600 === 0) return `${String(seconds / 3600)} h`;
  if (seconds % 60 === 0) return `${String(seconds / 60)} min`;
  return `${String(seconds)} s`;
}

function columnsFor(freshness: Freshness): readonly Column<ApiQueryFinding>[] {
  return [
    {
      key: 'severity',
      header: 'Severity',
      render: (row) => <SeverityBadge level={severityOf(row)} />,
    },
    {
      key: 'dashboard',
      header: 'Dashboard and panel',
      render: (row) => (
        <>
          {row.dashboard_title}
          <br />
          {row.panel_title}
        </>
      ),
    },
    { key: 'refresh', header: 'Refresh', render: (row) => secondsLabel(row.refresh_seconds) },
    { key: 'window', header: 'Window', render: (row) => secondsLabel(row.window_seconds) },
    {
      key: 'runs',
      header: 'Runs per day',
      numeric: true,
      render: (row) => (
        <Figure value={figureOf(row, row.runs_per_day)} freshness={freshness} unit="count" />
      ),
    },
    {
      key: 'scan',
      header: 'Scan per run, MiB',
      numeric: true,
      render: (row) => (
        <Figure
          value={figureOf(row, row.bytes_scanned_per_run / MIB)}
          freshness={freshness}
          unit="count"
        />
      ),
    },
    {
      key: 'cost',
      header: 'Monthly cost',
      numeric: true,
      render: (row) => (
        <Figure value={figureOf(row, Number(row.monthly_cost))} freshness={freshness} unit="usd" />
      ),
    },
    // `unattributed` arrives as a value from FEAT-016 and renders as one. An
    // empty cell would read as "no owner needed" rather than "nobody claimed it".
    { key: 'owner', header: 'Owner', render: (row) => row.owner },
    { key: 'why', header: 'Why', render: (row) => row.why },
  ];
}

export function QueryFindingsScreen() {
  const query = useQueryFindings();
  const envelope = query.data?.data;
  useReportMeta('query-findings', envelope?.meta);

  const rows = useMemo(() => {
    // Sorted as decimals. A string sort puts 3.20 above 12400.00, which is the
    // exact inversion this screen exists to prevent.
    return [...(envelope?.data ?? [])].sort(
      (left, right) => Number(right.monthly_cost) - Number(left.monthly_cost),
    );
  }, [envelope]);

  const freshness: Freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };
  const state = surfaceStateFor(query, envelope?.meta, rows.length, 'none', 'query_audit');

  return (
    <section aria-label="Query findings">
      <FixtureBand source={query.data?.source ?? 'fixture'} />
      <StateBoundary state={state}>
        <DataTable
          rows={rows}
          columns={columnsFor(freshness)}
          rowKey={(row) => row.finding_id}
          caption="Queries ranked by what they cost each month"
        />
      </StateBoundary>
    </section>
  );
}
