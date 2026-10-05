import { useCostForecast } from '../api/queries';
import type { ApiForecast } from '../api/types';
import { StackedArea } from '../components/charts';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import type { Freshness } from '../components/provenance';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { dayLabel, dollars, monthLabel } from './exploreModel';
import {
  aheadRows,
  backtestRows,
  chartOf,
  percentOf,
  type AheadRow,
  type TestRow,
} from './forecastModel';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Forecasts, under Plan. FEAT-066 and TASK-P8-008, the first screen to show a forecast.
 *
 * A forecast here is always a range and always says so, and its accuracy sits beside it, which
 * is ADR-0015's first, second and fourth conditions on the screen. The third is the route's: a
 * month it will not forecast arrives with the sentence saying why, and that sentence is shown
 * where the figure would have been. The layout is the one the owner approved on 2026-10-05.
 */
export function ForecastScreen() {
  const query = useCostForecast();
  const envelope = query.data;
  const forecast = envelope?.data;
  useReportMeta('cost-forecast', envelope?.meta);
  const state = surfaceStateFor(
    query,
    envelope?.meta,
    forecast === undefined ? 0 : 1,
    'none',
    'cost_focus',
  );
  const freshness: Freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };
  return (
    <section aria-label="Forecasts">
      <StateBoundary state={state}>
        {forecast === undefined ? null : (
          <ForecastView forecast={forecast} freshness={freshness} />
        )}
      </StateBoundary>
    </section>
  );
}

function range(low: number, high: number, freshness: Freshness) {
  return <Figure value={{ kind: 'forecast', low, high }} freshness={freshness} />;
}

function aheadColumns(interval: number, freshness: Freshness): readonly Column<AheadRow>[] {
  return [
    { key: 'month', header: 'Month', render: (row) => row.month },
    {
      key: 'forecast',
      header: `Forecast, ${String(interval)} percent interval`,
      prose: true,
      render: (row) =>
        row.figure === null ? (
          <span data-testid="forecast-withheld">{row.withheld}</span>
        ) : (
          range(row.figure.low, row.figure.high, freshness)
        ),
    },
    {
      key: 'miss',
      header: 'Median miss in backtest',
      numeric: true,
      render: (row) => row.medianMiss ?? 'Not tested',
    },
    { key: 'tested', header: 'Months tested', numeric: true, render: (row) => row.heldOut },
  ];
}

function backtestColumns(freshness: Freshness): readonly Column<TestRow>[] {
  return [
    { key: 'month', header: 'Month', render: (row) => row.month },
    {
      key: 'range',
      header: 'Forecast range',
      numeric: true,
      // Withheld forecasts keep their misses and lose their ranges, so the backtest cannot show
      // by the side door the figure the screen was not allowed to.
      render: (row) =>
        row.range === null ? 'Withheld' : range(row.range.low, row.range.high, freshness),
    },
    {
      key: 'actual',
      header: 'Actual',
      numeric: true,
      render: (row) => (
        <Figure value={{ kind: 'measured', amount: row.actual }} freshness={freshness} />
      ),
    },
    { key: 'miss', header: 'Miss', numeric: true, render: (row) => row.miss },
    {
      key: 'within',
      header: 'Inside the range',
      render: (row) => (row.within === null ? '' : row.within ? 'Yes' : 'No'),
    },
  ];
}

function ForecastView({
  forecast,
  freshness,
}: {
  readonly forecast: ApiForecast;
  readonly freshness: Freshness;
}) {
  const month = forecast.month_end;
  const chart = chartOf(forecast);
  return (
    <div data-testid="forecast">
      <div data-testid="forecast-headline">
        <section data-testid="forecast-month-end" aria-label="Forecast to month end">
          <h3>Forecast to month end, {monthLabel(month.month)}</h3>
          {month.figure === null ? (
            <p data-testid="forecast-withheld">{month.withheld}</p>
          ) : (
            <p data-testid="forecast-range">
              {range(Number(month.figure.low), Number(month.figure.high), freshness)}
            </p>
          )}
          <p>
            {String(forecast.interval_percent)} percent interval. Billed through{' '}
            {dayLabel(forecast.billed_through)}:{' '}
            <Figure
              value={{ kind: 'measured', amount: Number(forecast.billed_to_date) }}
              freshness={freshness}
            />
          </p>
        </section>
        <section data-testid="forecast-accuracy" aria-label="Accuracy">
          <h3>Accuracy</h3>
          <p>
            {month.median_miss === null
              ? 'Not yet tested on a complete month.'
              : `Median miss ${percentOf(month.median_miss)} over the last ${String(month.held_out)} months, measured by backtest.`}
          </p>
          <p>
            Method: {forecast.method}. {forecast.method_detail}
          </p>
          <p>
            Shown only when tested on at least {String(forecast.min_held_out)} complete months
            with a median miss of at most {percentOf(forecast.max_median_miss)}.
          </p>
        </section>
      </div>
      <div data-testid="forecast-chart">
        <StackedArea
          periods={chart.periods}
          series={chart.series}
          forecast={chart.band}
          label="Effective Cost this month, billed and forecast, cumulative"
          format={dollars}
        />
      </div>
      <div data-testid="forecast-ahead">
        <DataTable
          rows={aheadRows(forecast)}
          columns={aheadColumns(forecast.interval_percent, freshness)}
          rowKey={(row) => row.key}
          caption="The next three months"
        />
      </div>
      <div data-testid="forecast-backtest">
        <DataTable
          rows={backtestRows(forecast)}
          columns={backtestColumns(freshness)}
          rowKey={(row) => row.key}
          caption="Backtest: each complete month forecast again as if it were today"
        />
      </div>
    </div>
  );
}
