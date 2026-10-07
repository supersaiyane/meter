import type { Provenance } from '../provenance';
import { ChartTable } from './ChartTable';
import { Hatch } from './Hatch';
import { at, markClass, useChartId } from './marks';

/**
 * A breakdown by dimension, each bar split by series. P8 spec section 5.4.
 *
 * Rows by default, as RankedBars is, because a category is a word and words do not fit under a
 * column. The widest bar is the scale, so a reader compares whole bars by length and the
 * segments inside one by their share of it.
 *
 * Columns where the categories are days or months, which Cost Explorer draws, TASK-P8-007: time
 * reads left to right, and the axis is three labels, the first, the peak and the last, as
 * BarChart draws it, because thirty one labels under thirty one columns is a label nobody reads.
 */

export interface BarSeries {
  readonly key: string;
  readonly label: string;
  readonly provenance: Provenance;
  /** One per category. */
  readonly values: readonly number[];
}

export interface StackedBarProps {
  readonly categories: readonly string[];
  readonly series: readonly BarSeries[];
  readonly label: string;
  readonly format: (value: number) => string;
  /** What the categories are, for the table's first column. */
  readonly categoryName?: string;
  /** Rows for a breakdown by named things, columns for one over time. */
  readonly orientation?: 'rows' | 'columns';
}

const TRACK = 100;
const COLUMN_HEIGHT = 160;

interface Drawing {
  readonly categories: readonly string[];
  readonly series: readonly BarSeries[];
  readonly totals: readonly number[];
  readonly widest: number;
  readonly label: string;
  readonly format: (value: number) => string;
  readonly id: string;
}

interface Box {
  readonly x: string;
  readonly y: string;
  readonly width: string;
  readonly height: string;
}

/** Where each series starts within one bar, the ones before it stacked beneath it. */
function offsetsAt(series: readonly BarSeries[], category: number, scale: number): number[] {
  return series.map((_, index) =>
    series.slice(0, index).reduce((sum, one) => sum + (one.values[category] ?? 0) * scale, 0),
  );
}

function Segment({
  one,
  index,
  value,
  box,
  hatch,
}: {
  readonly one: BarSeries;
  readonly index: number;
  readonly value: number;
  readonly box: Box;
  readonly hatch: string;
}) {
  return (
    <g>
      <rect
        data-testid="bar-segment"
        data-value={value}
        {...box}
        className={markClass(one.provenance, index)}
      />
      {one.provenance === 'modelled' ? (
        <rect data-testid="hatch-over" {...box} fill={`url(#${hatch}-hatch)`} />
      ) : null}
    </g>
  );
}

function Rows({ categories, series, totals, widest, label, format, id }: Drawing) {
  const scale = TRACK / widest;
  return (
    <ol className="meter-stacked-bars" aria-label={label}>
      {categories.map((category, row) => {
        const offsets = offsetsAt(series, row, scale);
        const hatch = `${id}-${String(row)}`;
        return (
          <li key={category}>
            <span>{category}</span>
            <svg
              viewBox={`0 0 ${String(TRACK)} 10`}
              preserveAspectRatio="none"
              width="100%"
              height="14"
              aria-hidden="true"
            >
              <Hatch id={hatch} />
              {series.map((one, index) => {
                const value = one.values[row] ?? 0;
                return (
                  <Segment
                    key={one.key}
                    one={one}
                    index={index}
                    value={value}
                    hatch={hatch}
                    box={{
                      x: at(offsets[index] ?? 0),
                      y: '0',
                      width: at(value * scale),
                      height: '10',
                    }}
                  />
                );
              })}
            </svg>
            <span className="meter-numeral">{format(totals[row] ?? 0)}</span>
          </li>
        );
      })}
    </ol>
  );
}

function Columns({ categories, series, widest, label, format, id }: Drawing) {
  // From zero, as BarChart is, so a quiet day is not drawn as a collapse.
  const scale = (COLUMN_HEIGHT - 2) / widest;
  return (
    <>
      <svg
        data-testid="stacked-columns"
        viewBox={`0 0 ${String(categories.length * 10)} ${String(COLUMN_HEIGHT)}`}
        preserveAspectRatio="none"
        width="100%"
        height={COLUMN_HEIGHT}
        role="img"
        aria-label={label}
      >
        <Hatch id={id} />
        {categories.map((category, column) => {
          const offsets = offsetsAt(series, column, scale);
          return (
            <g key={category}>
              {series.map((one, index) => {
                const value = one.values[column] ?? 0;
                const tall = value * scale;
                return (
                  <Segment
                    key={one.key}
                    one={one}
                    index={index}
                    value={value}
                    hatch={id}
                    box={{
                      x: at(column * 10 + 1.5),
                      y: at(COLUMN_HEIGHT - (offsets[index] ?? 0) - tall),
                      width: '7',
                      height: at(tall),
                    }}
                  />
                );
              })}
            </g>
          );
        })}
      </svg>
      <figcaption data-testid="stacked-columns-axis">
        <span>{categories[0]}</span>
        <span>peak {format(widest)}</span>
        <span>{categories[categories.length - 1]}</span>
      </figcaption>
    </>
  );
}

export function StackedBar({
  categories,
  series,
  label,
  format,
  categoryName = 'Category',
  orientation = 'rows',
}: StackedBarProps) {
  const id = useChartId();
  const totals = categories.map((_, category) =>
    series.reduce((sum, one) => sum + (one.values[category] ?? 0), 0),
  );
  const widest = Math.max(0, ...totals);
  if (categories.length === 0 || widest === 0) {
    return (
      <p data-testid="chart-absent" data-state="never-collected">
        Nothing collected yet.
      </p>
    );
  }
  const drawing = { categories, series, totals, widest, label, format, id };
  return (
    <figure data-testid="stacked-bar" data-orientation={orientation} className="meter-chart">
      <ul className="meter-legend" aria-hidden="true">
        {series.map((one, index) => (
          <li key={one.key}>
            <svg width="10" height="10">
              <rect width="10" height="10" className={markClass(one.provenance, index)} />
            </svg>
            {one.label}
          </li>
        ))}
      </ul>
      {orientation === 'columns' ? <Columns {...drawing} /> : <Rows {...drawing} />}
      <ChartTable
        caption={label}
        rowHeader={categoryName}
        columns={[...series.map((one) => one.label), 'Total']}
        rows={categories.map((category, row) => ({
          label: category,
          cells: [
            ...series.map((one) => {
              const value = one.values[row] ?? 0;
              return { value, text: format(value) };
            }),
            { value: totals[row] ?? 0, text: format(totals[row] ?? 0) },
          ],
        }))}
      />
    </figure>
  );
}
