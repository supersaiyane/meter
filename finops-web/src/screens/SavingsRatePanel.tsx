import { useId, useMemo } from 'react';

import { useSavingsRate } from '../api/queries';
import type { ApiSavingsRateMonth } from '../api/types';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { FreshnessIndicator } from '../components/FreshnessIndicator';
import { PercentCell } from '../components/PercentCell';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { monthName } from './commitmentFormat';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * The commitments screen's headline: the effective savings rate, measured from the bill.
 * FEAT-087, TASK-P14-009.
 *
 * One minus Effective Cost over List Cost, over the usage lines that carry a List Cost, by billing
 * month. A month whose lines carry none has no rate, and says so in the API's own words rather than
 * drawing a nought, which would read as commitments that saved nothing.
 */

function rateOf(month: ApiSavingsRateMonth): number | null {
  return month.rate === null ? null : Number(month.rate);
}

export function SavingsRatePanel() {
  const heading = useId();
  const query = useSavingsRate();
  const envelope = query.data;
  const months = useMemo(() => envelope?.data.months ?? [], [envelope]);
  useReportMeta('commitment-savings-rate', envelope?.meta);
  const state = surfaceStateFor(query, envelope?.meta, months.length, 'none', 'cost_focus');
  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };
  const latest = months.at(-1);

  const columns: readonly Column<ApiSavingsRateMonth>[] = [
    {
      key: 'month',
      header: 'Billing month',
      rowHeader: true,
      render: (row) => monthName(row.period),
      sortValue: (row) => row.period,
    },
    {
      key: 'rate',
      header: 'Effective savings rate',
      numeric: true,
      render: (row) => (
        <PercentCell
          fraction={rateOf(row)}
          absent={row.reason ?? 'no List Cost'}
          provenance="measured"
        />
      ),
      sortValue: rateOf,
    },
    {
      key: 'effective',
      header: 'Effective Cost',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: Number(row.effective_cost) }}
          freshness={freshness}
          unit="usd"
        />
      ),
    },
    {
      key: 'list',
      header: 'List Cost, the on demand equivalent',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: Number(row.list_cost) }}
          freshness={freshness}
          unit="usd"
        />
      ),
    },
    {
      key: 'unlisted',
      header: 'Lines with no List Cost',
      numeric: true,
      // Counted, so a reader sees how much of the bill the rate leaves out.
      render: (row) => String(row.lines_without_list_cost),
    },
  ];

  return (
    <section className="meter-panel" aria-labelledby={heading} data-testid="savings-rate">
      <h2 id={heading}>Effective savings rate</h2>
      <p data-testid="savings-rate-means">
        One minus Effective Cost over List Cost, over the bill&apos;s usage lines that carry a
        List Cost: what commitments and discounts saved against paying on demand. Measured
        {envelope?.meta.as_of ? <FreshnessIndicator freshness={freshness} /> : null}
      </p>
      <StateBoundary state={state}>
        {latest ? (
          <p data-testid="savings-rate-headline">
            {monthName(latest.period)}:{' '}
            <PercentCell
              fraction={rateOf(latest)}
              absent={latest.reason ?? 'no List Cost'}
              provenance="measured"
            />
          </p>
        ) : null}
        <DataTable
          rows={months}
          columns={columns}
          rowKey={(row) => row.period}
          caption={`${String(months.length)} billing months, the oldest first`}
        />
      </StateBoundary>
    </section>
  );
}
