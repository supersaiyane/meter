import { useMemo } from 'react';

import { useQueryAdhoc } from '../api/queries';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';
import type { ApiAdhocQuery } from '../api/types';

/**
 * The queries that belong to nobody. FEAT-051.
 *
 * Every other governance screen starts from something Meter can enumerate: a
 * panel, an alert rule. These ran from neither. They are visible only because
 * CloudTrail saw them, which is also why every figure here is measured and none
 * is modelled: there is no definition to model from.
 *
 * Ranked by cost, then by how often it ran. Two queries costing the same are
 * not equally interesting, and the repeated one is the habit worth a
 * conversation.
 */

/** A gibibyte, so a scan is reported in the unit the console quotes. */
const GIB = 1024 ** 3;

function gibibytes(bytes: number): string {
  return `${(bytes / GIB).toLocaleString(undefined, { maximumFractionDigits: 0 })} GiB`;
}

export function QueryAdhocScreen() {
  const query = useQueryAdhoc();
  const envelope = query.data?.data;
  const rows = useMemo(() => envelope?.data ?? [], [envelope]);
  useReportMeta('query-adhoc', envelope?.meta);
  const state = surfaceStateFor(query, envelope?.meta, rows.length, 'none', 'query_audit');

  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };

  const columns: readonly Column<ApiAdhocQuery>[] = [
    {
      key: 'cost',
      header: 'Cost',
      numeric: true,
      render: (row) => (
        // Measured, always. An ad hoc query exists only in the evidence, so a
        // modelled figure here would be an invention rather than an estimate.
        <Figure value={{ kind: 'measured', amount: Number(row.cost_usd) }} freshness={freshness} />
      ),
    },
    { key: 'runs', header: 'Runs', numeric: true, render: (row) => row.runs },
    {
      key: 'scanned',
      header: 'Scanned',
      numeric: true,
      render: (row) => gibibytes(row.scan_bytes),
    },
    {
      key: 'principal',
      header: 'Who ran it',
      // Null is not a gap to tidy away. A query nobody owns is the case this
      // screen exists for, so it is named as unattributed and ranked beside
      // the rest rather than hidden.
      render: (row) => row.principal ?? 'unattributed',
    },
    { key: 'account', header: 'Account', render: (row) => `${row.account_id} ${row.region_id}` },
    {
      key: 'query',
      header: 'The query',
      // Whole, never truncated. The reader has to recognise their own query to
      // act on it, and a shortened one is unrecognisable.
      prose: true,
      render: (row) => row.query_text,
    },
  ];

  return (
    <section aria-label="Ad hoc queries">
      <StateBoundary state={state}>
        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(row) => row.adhoc_id}
          caption={`${String(rows.length)} queries that belong to no panel and no alert rule`}
        />
      </StateBoundary>
    </section>
  );
}
