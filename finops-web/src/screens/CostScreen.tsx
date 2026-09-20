import { useMemo } from 'react';

import { useCostByService, useCostSummary, useCostTrend } from '../api/queries';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { Sparkline } from '../components/Sparkline';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';
import type { ApiCostSlice } from '../api/types';

/**
 * What the estate spent, and on what. FEAT-021.
 *
 * Every figure here is amortized cost. The roadmap chose that as the primary
 * measure, and this screen does not quietly offer a different one beside it
 * under the same label.
 *
 * The open period warning is the most important thing on the page. A month in
 * progress holds fewer days than the month before it, so its total is lower,
 * and a reader comparing the two without being told concludes that spending
 * collapsed. That conclusion is confident, wrong, and entirely the screen's
 * fault.
 */

function money(amount: string): number {
  return Number(amount);
}

export function CostScreen() {
  const summary = useCostSummary();
  const services = useCostByService();
  const trend = useCostTrend();

  const envelope = summary.data?.data;
  const current = envelope?.data.current;
  const previous = envelope?.data.previous ?? null;
  const change = envelope?.data.change ?? null;

  useReportMeta('cost', envelope?.meta);
  const state = surfaceStateFor(summary, envelope?.meta, current ? 1 : 0, 'none', 'cost_focus');

  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };

  const rows = useMemo(() => services.data?.data.data ?? [], [services.data]);
  const days = useMemo(() => trend.data?.data.data ?? [], [trend.data]);

  const columns: readonly Column<ApiCostSlice>[] = [
    { key: 'service', header: 'Service', render: (row) => row.name },
    {
      key: 'cost',
      header: 'Amortized',
      numeric: true,
      render: (row) => (
        // Measured, always. A charge is what the provider billed, and there is
        // no model here for it to be a projection of.
        <Figure
          value={{ kind: 'measured', amount: money(row.effective_cost) }}
          freshness={freshness}
        />
      ),
    },
    {
      key: 'billed',
      header: 'Billed',
      numeric: true,
      render: (row) => (
        <Figure value={{ kind: 'measured', amount: money(row.billed_cost) }} freshness={freshness} />
      ),
    },
    {
      key: 'items',
      header: 'Line items',
      numeric: true,
      render: (row) => row.line_items,
    },
  ];

  return (
    <section aria-label="Spend and trend">
      <StateBoundary state={state}>
        <div data-testid="cost-summary">
          <p data-testid="cost-period">
            {current ? current.period : ''}
            {current?.is_open ? (
              // Beside the figure, not in a footnote. A reader who misses this
              // is comparing a part month against a whole one.
              <strong data-testid="cost-open"> still open, so this period is incomplete</strong>
            ) : null}
          </p>
          <p data-testid="cost-total">
            {current ? (
              <Figure
                value={{ kind: 'measured', amount: money(current.effective_cost) }}
                freshness={freshness}
              />
            ) : null}
          </p>
          <p data-testid="cost-change">
            {change === null ? (
              // Not a zero. No earlier period was collected, and a change of
              // nought would claim the estate spent the same as a month nobody
              // ever read.
              <span data-testid="cost-no-comparison">
                No earlier period has been collected, so there is nothing to compare against
              </span>
            ) : (
              <>
                <Figure value={{ kind: 'measured', amount: money(change) }} freshness={freshness} />
                <span> against {previous?.period}</span>
              </>
            )}
          </p>
        </div>

        <div data-testid="cost-trend">
          {/*
            A shape, not eighteen rows. The first version of this rendered one
            line per day with the freshness label repeated on each, which was
            the same sentence eighteen times around numbers nobody could
            compare. The sparkline answers whether it is going up, and the two
            ends give the range a reader would otherwise measure off it.
          */}
          <Sparkline
            points={days.map((day) => money(day.effective_cost))}
            provenance="measured"
            label={`Daily spend across ${String(days.length)} days of this period`}
          />
          {days.length > 1 ? (
            <p data-testid="cost-trend-range">
              <span data-testid="cost-trend-day">{days[0]?.day}</span>
              <Figure
                value={{ kind: 'measured', amount: money(days[0]?.effective_cost ?? '0') }}
                freshness={freshness}
              />
              <span> to </span>
              <span data-testid="cost-trend-day">{days[days.length - 1]?.day}</span>
              <Figure
                value={{
                  kind: 'measured',
                  amount: money(days[days.length - 1]?.effective_cost ?? '0'),
                }}
                freshness={freshness}
              />
            </p>
          ) : (
            // One point is not a trend. Saying so beats drawing a flat line,
            // which would imply a stability nobody has observed.
            <p data-testid="cost-trend-range">
              One day collected so far, which is not yet a trend
            </p>
          )}
        </div>

        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(row) => row.name}
          caption={`${String(rows.length)} services, most expensive first`}
        />
      </StateBoundary>
    </section>
  );
}
