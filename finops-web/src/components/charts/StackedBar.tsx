import type { Provenance } from '../provenance';
import { ChartTable } from './ChartTable';
import { Hatch } from './Hatch';
import { at, markClass, useChartId } from './marks';

/**
 * A breakdown by dimension, each bar split by series. P8 spec section 5.4.
 *
 * Horizontal, as RankedBars is, because a category is a word and words do not fit under a
 * column. The widest bar is the scale, so a reader compares whole bars by length and the
 * segments inside one by their share of it.
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
}

const TRACK = 100;

export function StackedBar({
  categories,
  series,
  label,
  format,
  categoryName = 'Category',
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
  const scale = TRACK / widest;

  return (
    <figure data-testid="stacked-bar" className="meter-chart">
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
      <ol className="meter-stacked-bars" aria-label={label}>
        {categories.map((category, row) => {
          const offsets = series.map((_, index) =>
            series
              .slice(0, index)
              .reduce((sum, one) => sum + (one.values[row] ?? 0) * scale, 0),
          );
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
                <Hatch id={`${id}-${String(row)}`} />
                {series.map((one, index) => {
                  const value = one.values[row] ?? 0;
                  const box = {
                    x: at(offsets[index] ?? 0),
                    y: '0',
                    width: at(value * scale),
                    height: '10',
                  };
                  return (
                    <g key={one.key}>
                      <rect
                        data-testid="bar-segment"
                        data-value={value}
                        {...box}
                        className={markClass(one.provenance, index)}
                      />
                      {one.provenance === 'modelled' ? (
                        <rect
                          data-testid="hatch-over"
                          {...box}
                          fill={`url(#${id}-${String(row)}-hatch)`}
                        />
                      ) : null}
                    </g>
                  );
                })}
              </svg>
              <span className="meter-numeral">{format(totals[row] ?? 0)}</span>
            </li>
          );
        })}
      </ol>
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
