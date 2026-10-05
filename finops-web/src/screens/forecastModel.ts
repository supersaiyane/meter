import type { ApiForecast } from '../api/types';
import type { ForecastBand, TimeSeries } from '../components/charts/StackedArea';
import { bucketLabel, monthLabel } from './exploreModel';

/**
 * The Forecasts screen's model, FEAT-066: how a forecast becomes a chart and two tables. Pure,
 * and it never turns a range into a point, because nothing it is given has a point to give.
 */

/**
 * A share as a reader says it, to a tenth of a percent: 0.0595 is 6.0%.
 *
 * Rounded half up on the decimal digits themselves, as the route rounds the same share in its
 * sentences. Through a binary float, 0.0595 times a hundred is a hair under 5.95 and the screen
 * would say 5.9% beside a sentence saying 6.0 percent.
 */
export function percentOf(share: string): string {
  const negative = share.startsWith('-');
  const [whole = '0', fraction = ''] = share.replace('-', '').split('.');
  const digits = fraction.padEnd(4, '0');
  const tenths =
    Number(whole) * 1000 + Number(digits.slice(0, 3)) + (Number(digits[3]) >= 5 ? 1 : 0);
  return `${negative ? '-' : ''}${(tenths / 10).toFixed(1)}%`;
}

export interface ForecastChart {
  readonly periods: readonly string[];
  readonly series: readonly TimeSeries[];
  readonly band: ForecastBand;
}

/**
 * This month, cumulative: billed to date as a measured area, then the band.
 *
 * The band is pinned to the billed total on the last billed day, a width of nothing, so it
 * opens from where the measurement stops rather than floating a day to its right.
 */
export function chartOf(forecast: ApiForecast): ForecastChart {
  const billed = forecast.days.map((day) => (day.billed === null ? null : Number(day.billed)));
  const lastBilled = billed.reduce<number>(
    (last, value, index) => (value === null ? last : index),
    -1,
  );
  const shown = forecast.month_end.figure !== null;
  const edge = (value: string | null, index: number): number | null => {
    if (value !== null) return Number(value);
    return shown && index === lastBilled ? (billed[index] ?? null) : null;
  };
  return {
    periods: forecast.days.map((day) => bucketLabel(day.day, 'daily')),
    series: [
      {
        key: 'billed',
        label: 'Effective Cost billed',
        provenance: 'measured',
        values: billed,
      },
    ],
    band: {
      low: forecast.days.map((day, index) => edge(day.low, index)),
      high: forecast.days.map((day, index) => edge(day.high, index)),
    },
  };
}

export interface AheadRow {
  readonly key: string;
  readonly month: string;
  readonly figure: { readonly low: number; readonly high: number } | null;
  readonly withheld: string | null;
  readonly medianMiss: string | null;
  readonly heldOut: number;
}

/** The next three months, each a range or the sentence saying why there is none. */
export function aheadRows(forecast: ApiForecast): readonly AheadRow[] {
  return forecast.ahead.map((month) => ({
    key: month.month,
    month: monthLabel(month.month),
    figure:
      month.figure === null
        ? null
        : { low: Number(month.figure.low), high: Number(month.figure.high) },
    withheld: month.withheld,
    medianMiss: month.median_miss === null ? null : percentOf(month.median_miss),
    heldOut: month.held_out,
  }));
}

export interface TestRow {
  readonly key: string;
  readonly month: string;
  readonly actual: number;
  readonly miss: string;
  readonly range: { readonly low: number; readonly high: number } | null;
  readonly within: boolean | null;
}

/** Each held out month: what it cost, how far off the method was, and whether the band held it. */
export function backtestRows(forecast: ApiForecast): readonly TestRow[] {
  return forecast.backtest.map((test) => ({
    key: test.month,
    month: monthLabel(test.month),
    actual: Number(test.actual),
    miss: percentOf(test.miss),
    range:
      test.low === null || test.high === null
        ? null
        : { low: Number(test.low), high: Number(test.high) },
    within: test.within,
  }));
}
