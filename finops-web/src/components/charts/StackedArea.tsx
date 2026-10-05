import type { Provenance } from '../provenance';
import { ChartTable, type TableRow } from './ChartTable';
import { Hatch } from './Hatch';
import { at, markClass, useChartId } from './marks';

/**
 * Spend over time, stacked by series, with the forecast range and the budget pace on the same
 * scale. P8 spec section 5.4.
 *
 * A period is drawn only when every series has a figure for it, because a missing figure
 * stacked as zero would draw the layers above it lower than they are. From zero, always: a
 * cost chart with a raised floor turns a normal month into a crisis.
 */

export interface TimeSeries {
  readonly key: string;
  readonly label: string;
  readonly provenance: Provenance;
  /** One per period, null where nothing was collected. */
  readonly values: readonly (number | null)[];
}

export interface ForecastBand {
  readonly low: readonly (number | null)[];
  readonly high: readonly (number | null)[];
}

export interface StackedAreaProps {
  readonly periods: readonly string[];
  readonly series: readonly TimeSeries[];
  readonly forecast?: ForecastBand;
  /** What the budget allows by each period, null where there is no budget. */
  readonly pace?: readonly (number | null)[];
  readonly label: string;
  readonly format: (value: number) => string;
  readonly height?: number;
}

const STEP = 20;

function cells(
  values: readonly (number | null)[],
  format: (value: number) => string,
): TableRow['cells'] {
  return values.map((value) =>
    value === null ? { value: null, text: 'not collected' } : { value, text: format(value) },
  );
}

export function StackedArea({
  periods,
  series,
  forecast,
  pace,
  label,
  format,
  height = 160,
}: StackedAreaProps) {
  const id = useChartId();
  const drawn = periods.map(
    (_, index) =>
      series.length > 0 &&
      series.every((one) => one.values[index] !== null && one.values[index] !== undefined),
  );
  const last = drawn.lastIndexOf(true);
  if (series.length === 0 || last < 1) {
    // One period is not a shape, the same refusal BarChart and Sparkline make.
    return (
      <p data-testid="chart-absent" data-state="never-collected">
        {last === 0
          ? 'Seen once. There is no shape until it has been collected twice.'
          : 'Nothing collected yet.'}
      </p>
    );
  }

  const below = (seriesIndex: number, period: number): number =>
    series.slice(0, seriesIndex).reduce((sum, one) => sum + (one.values[period] ?? 0), 0);
  const totals = periods.map((_, index) => (drawn[index] ? below(series.length, index) : 0));
  const top = Math.max(
    1,
    ...totals,
    ...(forecast?.high ?? []).map((value) => value ?? 0),
    ...(pace ?? []).map((value) => value ?? 0),
  );
  const width = Math.max(1, periods.length - 1) * STEP;
  const x = (period: number): number => period * STEP;
  const y = (value: number): number => height - (value / top) * height;
  const span = periods.slice(0, last + 1).map((_, period) => period);

  const layers = series.map((one, index) => {
    const upper = span.map((period) => y(below(index + 1, period)));
    const lower = span.map((period) => y(below(index, period)));
    const edge = span.map(
      (period, n) => `${n === 0 ? 'M' : 'L'}${at(x(period))} ${at(upper[n] ?? 0)}`,
    );
    const back = [...span]
      .reverse()
      .map((period) => `L${at(x(period))} ${at(lower[period] ?? 0)}`);
    return { one, index, d: `${edge.join(' ')} ${back.join(' ')} Z` };
  });

  const forecastAt = periods
    .map((_, period) => period)
    .filter((period) => forecast?.low[period] != null && forecast.high[period] != null);
  const band =
    forecast !== undefined && forecastAt.length > 1
      ? `${forecastAt
          .map(
            (period, n) =>
              `${n === 0 ? 'M' : 'L'}${at(x(period))} ${at(y(forecast.high[period] ?? 0))}`,
          )
          .join(' ')} ${[...forecastAt]
          .reverse()
          .map((period) => `L${at(x(period))} ${at(y(forecast.low[period] ?? 0))}`)
          .join(' ')} Z`
      : null;
  const pacePoints =
    pace === undefined
      ? null
      : periods
          .map((_, period) => period)
          .filter((period) => pace[period] != null)
          .map((period) => `${at(x(period))},${at(y(pace[period] ?? 0))}`)
          .join(' ');

  const rows: TableRow[] = [
    ...series.map((one) => ({ label: one.label, cells: cells(one.values, format) })),
    ...(forecast === undefined
      ? []
      : [
          { label: 'Forecast, low', cells: cells(forecast.low, format) },
          { label: 'Forecast, high', cells: cells(forecast.high, format) },
        ]),
    ...(pace === undefined ? [] : [{ label: 'Budget pace', cells: cells(pace, format) }]),
  ];

  return (
    <figure data-testid="stacked-area" className="meter-chart">
      <ul className="meter-legend" aria-hidden="true">
        {series.map((one, index) => (
          <li key={one.key}>
            <svg width="10" height="10">
              <rect width="10" height="10" className={markClass(one.provenance, index)} />
            </svg>
            {one.label}
          </li>
        ))}
        {band === null ? null : <li>Forecast range, dashed</li>}
        {pacePoints === null || pacePoints === '' ? null : <li>Budget pace, dotted</li>}
      </ul>
      <svg
        viewBox={`0 0 ${String(width)} ${String(height)}`}
        preserveAspectRatio="none"
        width="100%"
        height={height}
        role="img"
        aria-label={label}
        data-top={top}
        data-height={height}
      >
        <Hatch id={id} />
        {layers.map(({ one, index, d }) => (
          <g key={one.key}>
            <path data-testid="area-layer" d={d} className={markClass(one.provenance, index)} />
            {one.provenance === 'modelled' ? (
              <path
                data-testid="hatch-over"
                d={d}
                fill={`url(#${id}-hatch)`}
                aria-hidden="true"
              />
            ) : null}
          </g>
        ))}
        {band === null ? null : (
          <path data-testid="forecast-band" d={band} className={markClass('forecast', 0)} />
        )}
        {pacePoints === null || pacePoints === '' ? null : (
          <polyline data-testid="budget-pace" points={pacePoints} className="meter-pace" />
        )}
      </svg>
      <figcaption>
        <span>{periods[0]}</span>
        <span>highest {format(Math.max(...totals))}</span>
        <span>{periods[periods.length - 1]}</span>
      </figcaption>
      <ChartTable caption={label} rowHeader="Series" columns={periods} rows={rows} />
    </figure>
  );
}
