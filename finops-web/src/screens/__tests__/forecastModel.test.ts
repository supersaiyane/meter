import { describe, expect, it } from 'vitest';

import { aheadRows, backtestRows, chartOf, percentOf } from '../forecastModel';
import { forecastOf } from './fixtures';

/** FEAT-066. The Forecasts screen's rules, without rendering it. */

describe('a share', () => {
  it('is said to a tenth of a percent, rounded half up on its own digits', () => {
    // Through a binary float 0.0595 is a hair under 5.95 percent and would round down.
    expect(percentOf('0.0595')).toBe('6.0%');
    expect(percentOf('0.1533')).toBe('15.3%');
    expect(percentOf('0.15')).toBe('15.0%');
    expect(percentOf('0.05949999')).toBe('5.9%');
    expect(percentOf('1.2')).toBe('120.0%');
    expect(percentOf('-0.08')).toBe('-8.0%');
  });
});

describe('the chart', () => {
  it('draws billed days as a measured area and opens the band from the last of them', () => {
    const chart = chartOf(forecastOf());
    expect(chart.periods).toHaveLength(31);
    expect(chart.periods[0]).toBe('1 Oct');
    expect(chart.series[0]?.provenance).toBe('measured');
    expect(chart.series[0]?.values.slice(0, 5)).toEqual([500, 1000, 1500, 2000, null]);
    expect(chart.band.low[2]).toBeNull();
    // Pinned to what was billed on the last billed day, a band of no width.
    expect([chart.band.low[3], chart.band.high[3]]).toEqual([2000, 2000]);
    expect([chart.band.low[30], chart.band.high[30]]).toEqual([15000, 16000]);
  });

  it('draws no band at all, and pins nothing, when the month end is withheld', () => {
    const shown = forecastOf();
    const chart = chartOf(
      forecastOf({
        month_end: { ...shown.month_end, figure: null, withheld: 'Not tested enough.' },
        days: shown.days.map((day) => ({ ...day, low: null, high: null })),
      }),
    );
    expect(chart.band.low.every((value) => value === null)).toBe(true);
    expect(chart.band.high.every((value) => value === null)).toBe(true);
  });
});

describe('the months ahead', () => {
  it('are each a range or the sentence saying why, never both', () => {
    const rows = aheadRows(forecastOf());
    expect(rows.map((row) => row.month)).toEqual([
      'November 2026',
      'December 2026',
      'January 2027',
    ]);
    expect(rows[0]).toMatchObject({ figure: { low: 15700, high: 16100 }, withheld: null });
    expect(rows[1]?.figure).toBeNull();
    expect(rows[1]?.withheld).toContain('above the 15 percent');
    expect(rows[1]?.medianMiss).toBe('15.3%');
  });
});

describe('the backtest', () => {
  it('carries each month with its range and whether the range held it', () => {
    const rows = backtestRows(forecastOf());
    expect(rows.map((row) => [row.month, row.within])).toEqual([
      ['September 2026', true],
      ['August 2026', false],
      ['July 2026', true],
    ]);
    expect(rows[0]?.range).toEqual({ low: 14900, high: 15900 });
    expect(rows[0]?.miss).toBe('4.0%');
  });

  it('carries no range for a withheld forecast', () => {
    const rows = backtestRows(
      forecastOf({
        backtest: [
          {
            month: '2026-09-01',
            actual: '100.00',
            miss: '0.2',
            low: null,
            high: null,
            within: null,
          },
        ],
      }),
    );
    expect(rows[0]).toMatchObject({ range: null, within: null, miss: '20.0%' });
  });
});
