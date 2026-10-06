import { useMemo } from 'react';
import { verdictName } from '../components/displayNames';
import { ChartPanel } from '../components/ChartPanel';
import { StackedArea } from '../components/charts';
import { verifiedCumulative } from './realizedSavings';

import { useRealizedSavings } from '../api/queries';
import { DataTable } from '../components/DataTable';
import { RankedBars } from '../components/RankedBars';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';
import type { ApiRealizedSaving } from '../api/types';

/**
 * The one screen in this product where a number is allowed to be disappointing.
 * FEAT-029.
 *
 * It shows what actually appeared in the bill sixty days after somebody marked a
 * recommendation done. That figure is usually smaller than the estimate promised
 * on `/waste`, and the gap is the point rather than a defect: it is the only
 * evidence anywhere that this product works.
 *
 * **Three verdicts, and the third is listed.** `INCONCLUSIVE` means the cost fell
 * and the usage fell at least as fast, so the saving cannot be told apart from a
 * workload that shrank on its own. It is expected to be the most common verdict.
 * Hiding those rows would leave a page of successes, which is exactly the vanity
 * metric ISS-029 warns about, so they appear with their working like everything
 * else.
 *
 * **The totals are grouped by verdict and never summed.** One realized total
 * would be added to the estimated total by the first person who saw the two side
 * by side, and an inconclusive saving is not a saving.
 *
 * **An unobserved usage quantity says so.** Some services publish no
 * `consumed_quantity` at all. A zero there would read as a workload that
 * vanished, so the cell says the quantity was not published.
 */

function wholeDollars(value: number): string {
  return `$${value.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`;
}

function money(amount: string): number {
  return Number(amount);
}

const VERDICT_MEANING: Readonly<Record<string, string>> = {
  VERIFIED: 'cost fell at least as fast as usage',
  REGRESSED: 'cost did not fall',
  INCONCLUSIVE: 'the fall cannot be told apart from a smaller workload',
};

export function WasteSavingsScreen() {
  const query = useRealizedSavings();
  const envelope = query.data?.data;
  const found = envelope?.data;
  const rows = useMemo(() => found?.savings ?? [], [found]);

  useReportMeta('waste-savings', envelope?.meta);
  const state = surfaceStateFor(query, envelope?.meta, rows.length, 'none', 'realized_saving');

  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };

  const columns: readonly Column<ApiRealizedSaving>[] = [
    {
      key: 'verdict',
      header: 'Verdict',
      render: (row) => (
        <span data-testid={`verdict-${row.recommendation_id}`} data-verdict={row.verdict}>
          {verdictName(row.verdict)}
        </span>
      ),
    },
    {
      key: 'before',
      header: 'Cost before',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: money(row.cost_before) }}
          freshness={freshness}
        />
      ),
    },
    {
      key: 'after',
      header: 'Cost after',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: money(row.cost_after) }}
          freshness={freshness}
        />
      ),
    },
    {
      key: 'usage',
      header: 'Usage before and after',
      // The control. Without it a fall in cost cannot be told apart from a fall
      // in use, and the counterfactual is unobservable.
      render: (row) =>
        row.usage_before === null || row.usage_after === null ? (
          <span data-testid={`unobserved-${row.recommendation_id}`}>
            not published, so there is no control
          </span>
        ) : (
          <span data-testid={`usage-${row.recommendation_id}`}>
            {row.usage_before} to {row.usage_after}
          </span>
        ),
    },
    {
      key: 'window',
      header: 'Windows',
      render: (row) => `${row.window_before_start} to ${row.window_after_end}`,
    },
    {
      key: 'why',
      header: 'Why',
      // Whole, never shortened, and especially on the inconclusive rows: that
      // sentence is the entire reason those rows are worth reading.
      prose: true,
      render: (row) => row.why,
    },
  ];

  const totals = Object.entries(found?.by_verdict ?? {});

  const cumulative = verifiedCumulative(rows);

  return (
    <section aria-label="Realized savings">
      {/*
        Grouped, and deliberately not added up. Three figures under three
        headings, because one number here would be summed with the estimate on
        the recommendations screen within a week of anybody seeing both.
      */}
      <section aria-label="By verdict" data-testid="savings-by-verdict">
        {totals.length === 0 ? (
          <p data-testid="savings-none">
            Nothing has been verified yet. A recommendation is judged sixty days after it is
            marked done, so this page is empty because not enough time has passed, not because
            nothing worked
          </p>
        ) : (
          <dl>
            {totals.map(([verdict, total]) => (
              <div key={verdict} data-testid={`total-${verdict}`}>
                <dt>
                  {/* The verdict in words. Its code sat here unseen by the raw identifier
                      test only because the heading before it left no word boundary. */}
                  {verdictName(verdict)}, {VERDICT_MEANING[verdict] ?? 'no description'}
                </dt>
                <dd>
                  <Figure
                    value={{ kind: 'measured', amount: money(total.realized_monthly) }}
                    freshness={freshness}
                    label={`${String(total.count)} ${total.count === 1 ? 'change' : 'changes'}`}
                  />
                </dd>
              </div>
            ))}
          </dl>
        )}

        {/* The same three figures, drawn, and scaled to the largest of them rather than to
            their total. The total is the number this screen exists to refuse: one realized
            figure would be added to the estimate on the recommendations screen within a week
            of anybody seeing both. So the bars compare the verdicts with each other, which is
            a comparison that is true, and no share is printed, because a percentage with no
            whole behind it is a number nobody can check. Measured, not hatched: this is the
            one place in the product where a saving has actually been observed. */}
        {totals.length > 1 ? (
          <RankedBars
            points={totals.map(([verdict, total]) => ({
              label: `${verdict}, ${String(total.count)} ${
                total.count === 1 ? 'change' : 'changes'
              }`,
              value: money(total.realized_monthly),
            }))}
            provenance="measured"
            basis="largest"
            format={(value) =>
              `$${value.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`
            }
          />
        ) : null}
      </section>

      {/* What the verified changes have added up to, by the day each check closed. Verified
          only: the inconclusive and the regressed keep their own totals above, never added in. */}
      <ChartPanel
        id="savings-cumulative"
        title="Verified savings, as they added up"
        caption="Each verified change's monthly saving, cost before less cost after, added on the day its check closed. Inconclusive and regressed changes are never added in"
      >
        {/* Said rather than drawn below two days: one point is not a running total, and the
            chart's own words for that are about collection, which is not what is missing. */}
        {cumulative.periods.length === 0 ? (
          <p data-testid="savings-unverified">
            Nothing has been verified yet, so there is nothing to add up
          </p>
        ) : cumulative.periods.length === 1 ? (
          <p data-testid="savings-once">
            One day of verified changes so far,{' '}
            {wholeDollars(cumulative.series[0]?.values[0] ?? 0)} a month from{' '}
            {cumulative.periods[0]}. The running total is drawn once a second day closes
          </p>
        ) : (
          <StackedArea
            periods={cumulative.periods}
            series={cumulative.series.map((one) => ({
              ...one,
              provenance: 'measured' as const,
            }))}
            label="Verified monthly savings, cumulative, by the day each check closed"
            format={wholeDollars}
          />
        )}
      </ChartPanel>

      <StateBoundary state={state}>
        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(row) => row.recommendation_id}
          caption={`${String(rows.length)} ${
            rows.length === 1 ? 'change' : 'changes'
          } checked against the bill, newest first`}
        />
      </StateBoundary>
    </section>
  );
}
