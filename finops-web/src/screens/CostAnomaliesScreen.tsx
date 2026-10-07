import { useMemo } from 'react';

import { useCostAnomalies, useCostExplore } from '../api/queries';
import { ChartPanel } from '../components/ChartPanel';
import { StackedArea } from '../components/charts';
import { DataTable } from '../components/DataTable';
import { RankedBars } from '../components/RankedBars';
import { Figure } from '../components/Figure';
import { SeverityBadge } from '../components/SeverityBadge';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { exploreQuery, lastDays, stacked } from './exploreSeries';
import { signedDollars } from './exploreModel';
import { severityLevel } from './querySeverity';
import { surfaceStateFor } from './surfaceStateFor';
import type { ApiCostAnomaly } from '../api/types';

/**
 * Days that did not look like the days before them. FEAT-023.
 *
 * The hardest thing on this screen is the empty state, because an empty list
 * means two opposite things. An estate with a fortnight of history and nothing
 * wrong is behaving, and saying so is useful. An estate with four days of
 * history has not been judged at all, and telling that one it has no anomalies
 * is a reassuring lie it will act on.
 *
 * So the payload carries how many days have been collected, and this screen
 * says which of the two situations the reader is in.
 *
 * Every row carries three numbers and its working. A percentage alone is not
 * actionable: somebody has to know the money before they can decide whether to
 * care, and the baseline before they can disagree.
 */

function money(amount: string): number {
  return Number(amount);
}

/** The fortnight judged and the fortnight before it, which is what it was judged against. */
const CHART_DAYS = 30;

/** Services drawn by name. Every other service is one layer, so nothing leaves the stack. */
const SERVICES_KEPT = 5;

function dollars(value: number): string {
  return `$${value.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`;
}

export function CostAnomaliesScreen() {
  const query = useCostAnomalies();
  const envelope = query.data?.data;
  const found = envelope?.data;
  const rows = useMemo(() => found?.anomalies ?? [], [found]);

  useReportMeta('cost-anomalies', envelope?.meta);
  const state = surfaceStateFor(query, envelope?.meta, rows.length, 'none', 'cost_anomaly');

  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };

  const judgeable = (found?.days_collected ?? 0) >= (found?.days_needed ?? 0);

  // The days around the anomalies, read the way Cost Explorer reads them, so the chart and the
  // Explorer share one answer.
  const window = useMemo(() => lastDays(CHART_DAYS, new Date()), []);
  const daily = useCostExplore(
    exploreQuery({ period: 'custom', start: window.start, end: window.end }),
    { title: 'Effective Cost per day by service, last 30 days' },
  );
  useReportMeta('anomalies-daily', daily.data?.meta);
  const dailyState = surfaceStateFor(daily, daily.data?.meta, 1, 'none', 'cost_focus_daily');
  const shape = useMemo(
    () => stacked(daily.data?.data, SERVICES_KEPT, 'All other services'),
    [daily.data],
  );
  const markers = {
    name: 'Anomaly',
    at: rows.map((row) => ({
      period: row.day,
      label: `${row.service_name} in ${row.account_id}, ${signedDollars(money(row.delta))}`,
    })),
  };

  const columns: readonly Column<ApiCostAnomaly>[] = [
    {
      key: 'severity',
      header: 'Severity',
      // The same mapping the query findings use, so two screens do not mean
      // different things by the word high.
      render: (row) => <SeverityBadge level={severityLevel(row.severity)} />,
    },
    { key: 'day', header: 'Day', render: (row) => row.day },
    {
      key: 'what',
      header: 'Account and service',
      render: (row) => `${row.account_id} ${row.service_name}`,
    },
    {
      key: 'delta',
      header: 'Impact',
      numeric: true,
      render: (row) => (
        <Figure value={{ kind: 'measured', amount: money(row.delta) }} freshness={freshness} />
      ),
    },
    {
      key: 'observed',
      header: 'Actual cost',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: money(row.observed) }}
          freshness={freshness}
        />
      ),
    },
    {
      key: 'baseline',
      header: 'Expected cost',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: money(row.baseline) }}
          freshness={freshness}
        />
      ),
    },
    {
      key: 'why',
      header: 'Why',
      // Whole, never shortened. A verdict a reader cannot argue with is one
      // they have to take on trust, and nobody takes a cost alert on trust
      // twice.
      prose: true,
      render: (row) => row.why,
    },
  ];

  return (
    <section aria-label="Anomalies">
      {/*
        Outside the boundary on purpose. This sentence is about whether the
        estate can be judged at all, which is a fact about the screen rather
        than about the request, and the boundary takes over the moment there
        are no rows. Inside it, the one distinction this screen exists to draw
        would be the one thing a reader never sees.
      */}
      <p data-testid="anomaly-context">
        {judgeable ? (
          <span data-testid="anomaly-judged">
            {found?.days_collected} days collected, which is enough to judge against
          </span>
        ) : (
          // Not "no anomalies". Nothing here has been judged, and a reader
          // who takes silence for safety will act on it.
          <span data-testid="anomaly-too-young">
            Only {found?.days_collected} days collected. Nothing can be judged until there are{' '}
            {found?.days_needed}, so this page is empty because nobody has looked yet, not
            because nothing is wrong
          </span>
        )}
      </p>

      {judgeable && rows.length === 0 ? (
        <p data-testid="anomaly-none">
          No day in the last fortnight stood out from the days before it
        </p>
      ) : null}

      {/* The days in context: what each cost by service, with a rule on every day that stood
          out, so a reader sees whether it was one service's spike or the whole estate's. */}
      <ChartPanel
        id="anomalies-daily"
        title="Each day, with the days that stood out"
        caption="Effective Cost per day for the last thirty days by service. A rule marks each day that stood out, and the bars below set it against its usual cost"
      >
        <StateBoundary state={dailyState} coverageShownElsewhere>
          <StackedArea
            periods={shape.periods}
            series={shape.series.map((one) => ({ ...one, provenance: 'measured' as const }))}
            markers={markers}
            label="Effective Cost per day by service, last thirty days, with anomalies marked"
            format={dollars}
          />
        </StateBoundary>
      </ChartPanel>

      <StateBoundary state={state}>
        {/* What the day cost, with a tick at what it usually costs. This is the screen where
            a picture explains the most, because the finding is a comparison between two
            numbers and the table puts them in two columns for the reader to subtract. The
            bar is the observed cost, the tick is the baseline, and how far past the tick the
            bar runs is the anomaly.

            Scaled to the largest observed day rather than to a total, because the days belong
            to different accounts and services and adding them up would produce a figure that
            is not the estate's spend and is not anything else either. No share is printed for
            the same reason. */}
        {rows.length > 0 ? (
          <RankedBars
            points={rows.map((row) => ({
              label: `${row.day}, ${row.service_name}`,
              value: money(row.observed),
              marker: money(row.baseline),
            }))}
            provenance="measured"
            basis="largest"
            format={(value) =>
              `$${value.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`
            }
          />
        ) : null}

        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(row) => `${row.account_id}:${row.service_name}:${row.day}`}
          caption={`${String(rows.length)} ${
            rows.length === 1 ? 'day' : 'days'
          } that stood out, biggest first`}
        />
      </StateBoundary>
    </section>
  );
}
