import { useMemo } from 'react';

import { useCostSummary, useShowback } from '../api/queries';
import type { ApiShowbackRow } from '../api/types';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import type { Column, ColumnTotal } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Showback, the file finance opens. FEAT-045, delivered through FEAT-067.
 *
 * One billing period by account, service and tag value, the grain finance asks for. Since
 * TASK-P8-009 the rows are on the screen and the file comes from the Export menu beside the
 * title, which every screen has: a workbook whose About sheet says what it holds, or a CSV of
 * every row, both written by the server under this screen's scope. The CSV this screen used to
 * fetch and save by hand is gone, and so is its reason for refusing a workbook, because the
 * workbook now says what its figures are instead of looking like decisions nobody made.
 *
 * The screen keeps its one claim: the total the file must add up to, which is the figure the
 * spend screen shows. A reader who sums the Effective Cost column in their spreadsheet and gets
 * that figure has checked our arithmetic, which is worth more than any reassurance.
 */

/** What the API calls a charge nobody tagged. Matched, never re-derived. */
const UNALLOCATED = 'unallocated';

/** The tag key the rows are grouped by, which is the route's default. */
const TAG = 'team';

interface Freshness {
  readonly asOf: Date;
  readonly collectedAt: Date;
}

function money(amount: string): number {
  return Number(amount);
}

/** A money column's total, drawn the way its cells are. */
function dollars(
  pick: (row: ApiShowbackRow) => string,
  freshness: Freshness,
): ColumnTotal<ApiShowbackRow> {
  return {
    value: (row) => money(pick(row)),
    unit: () => 'USD',
    provenance: () => 'measured',
    render: (sum) => <Figure value={{ kind: 'measured', amount: sum }} freshness={freshness} />,
  };
}

function columnsFor(freshness: Freshness): readonly Column<ApiShowbackRow>[] {
  return [
    {
      key: 'account',
      header: 'Account',
      render: (row) => row.account_id,
      sortValue: (row) => row.account_id,
    },
    {
      key: 'service',
      header: 'Service',
      render: (row) => row.service_name,
      sortValue: (row) => row.service_name,
    },
    {
      key: 'tag',
      header: `By ${TAG}`,
      render: (row) =>
        row.tag_value === UNALLOCATED ? (
          // Named, not blank. An empty cell reads as a rendering fault.
          <span data-testid="export-unallocated-row">Unallocated cost</span>
        ) : (
          row.tag_value
        ),
      sortValue: (row) => row.tag_value,
    },
    {
      key: 'effective',
      header: 'Effective Cost',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: money(row.effective_cost) }}
          freshness={freshness}
        />
      ),
      sortValue: (row) => money(row.effective_cost),
      total: dollars((row) => row.effective_cost, freshness),
    },
    {
      key: 'billed',
      header: 'Billed Cost',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: money(row.billed_cost) }}
          freshness={freshness}
        />
      ),
      sortValue: (row) => money(row.billed_cost),
      total: dollars((row) => row.billed_cost, freshness),
    },
    {
      key: 'items',
      header: 'Line items',
      numeric: true,
      render: (row) => row.line_items,
      sortValue: (row) => row.line_items,
    },
  ];
}

export function CostExportScreen() {
  const summaryQuery = useCostSummary();
  const showback = useShowback();
  const envelope = showback.data;
  const rows = useMemo(() => envelope?.data ?? [], [envelope]);
  const summary = summaryQuery.data?.data.data;

  useReportMeta('cost-export', envelope?.meta);
  const state = surfaceStateFor(showback, envelope?.meta, rows.length, 'none', 'cost_focus_daily');

  const freshness = useMemo(
    () => ({
      asOf: new Date(envelope?.meta.as_of ?? 0),
      collectedAt: new Date(envelope?.meta.collected_at ?? 0),
    }),
    [envelope],
  );
  const columns = useMemo(() => columnsFor(freshness), [freshness]);
  const period = rows[0]?.billing_period ?? summary?.current.period ?? '';

  return (
    <section aria-label="Exports">
      <StateBoundary state={state}>
        <div>
          {summary === undefined ? null : (
            <p data-testid="export-claim">
              One row per account, service and {TAG} for the period starting {period}. The
              Effective Cost column adds up to{' '}
              <Figure
                value={{ kind: 'measured', amount: money(summary.current.effective_cost) }}
                freshness={freshness}
              />
              , which is the figure on the spend screen. If your spreadsheet disagrees, the
              export is wrong and we want to know
            </p>
          )}

          <p data-testid="export-how">
            Export, beside the title, writes these rows as an Excel workbook whose About sheet
            says what it holds, or as a CSV of every row. The server writes both, under the same
            scope as this screen
          </p>

          <p data-testid="export-measures">
            Both measures are in the file under their FOCUS names. Amortized and billed differ by
            exactly the commitment discount, and a column headed only cost is a column somebody
            argues about
          </p>

          <p data-testid="export-unallocated">
            Charges nobody tagged appear as a row named unallocated. They are never dropped and
            never folded into another row, because a file that loses what it cannot attribute
            reports a smaller estate than exists
          </p>

          <DataTable
            rows={rows}
            columns={columns}
            rowKey={(row) => `${row.account_id}|${row.service_name}|${row.tag_value}`}
            initialSort={{ key: 'effective', direction: 'descending' }}
            caption={`${String(rows.length)} rows, largest first, including what nobody tagged`}
          />
        </div>
      </StateBoundary>
    </section>
  );
}
