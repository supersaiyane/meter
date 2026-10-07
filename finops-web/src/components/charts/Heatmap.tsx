import type { Provenance } from '../provenance';
import { ChartTable } from './ChartTable';
import { Hatch } from './Hatch';
import { HEAT_FLOOR, useChartId } from './marks';

/**
 * Two dimensions at once, as shade: hours by weekday, services by day. P8 spec section 5.4.
 *
 * One hue, shaded by value against the largest cell, because the question is where the money
 * gathers and a rainbow would make a reader decode colours before seeing the shape. A cell
 * with no figure is drawn as an outline, never as the faintest shade, which would read as a
 * zero.
 */

export interface HeatmapProps {
  readonly rows: readonly string[];
  readonly columns: readonly string[];
  /** One row per row label, one value per column, null where nothing was collected. */
  readonly values: readonly (readonly (number | null)[])[];
  readonly provenance: Provenance;
  readonly label: string;
  readonly format: (value: number) => string;
  /** What the table says for a cell with no figure: not collected, unless the caller knows. */
  readonly missing?: string;
}

const CELL = 14;
const GAP = 2;
const LEFT = 48;
const TOP = 14;
/** About how wide one character of an axis label is, in the drawing's own units. */
const CHAR = 4.6;
/** Column names longer than this are slanted, so neighbours do not run into each other. */
const UPRIGHT = 3;

export function Heatmap({
  rows,
  columns,
  values,
  provenance,
  label,
  format,
  missing = 'not collected',
}: HeatmapProps) {
  const id = useChartId();
  const largest = Math.max(0, ...values.flat().map((value) => value ?? 0));
  if (rows.length === 0 || columns.length === 0) {
    return (
      <p data-testid="chart-absent" data-state="never-collected">
        Nothing collected yet.
      </p>
    );
  }
  // The gutters grow to the names, so a long account or collector name is drawn whole rather
  // than under the cells, and slanted names get the room above and to the right they rise into.
  const longestRow = Math.max(0, ...rows.map((row) => row.length));
  const longestColumn = Math.max(0, ...columns.map((column) => column.length));
  const left = Math.max(LEFT, Math.ceil(longestRow * CHAR) + 8);
  const slanted = longestColumn > UPRIGHT;
  const rise = slanted ? Math.ceil(longestColumn * CHAR * Math.SQRT1_2) : 0;
  const top = TOP + rise;
  const width = left + columns.length * (CELL + GAP) + rise;
  const height = top + rows.length * (CELL + GAP);
  const shade = (value: number): string =>
    (HEAT_FLOOR + (1 - HEAT_FLOOR) * (largest === 0 ? 0 : value / largest)).toFixed(4);

  return (
    <figure data-testid="heatmap" className="meter-chart">
      <svg
        viewBox={`0 0 ${String(width)} ${String(height)}`}
        width="100%"
        role="img"
        aria-label={label}
      >
        <Hatch id={id} />
        {columns.map((column, c) => {
          const x = left + c * (CELL + GAP) + CELL / 2;
          const y = top - 4;
          return (
            <text
              key={column}
              x={x}
              y={y}
              textAnchor={slanted ? 'start' : 'middle'}
              transform={slanted ? `rotate(-45 ${String(x)} ${String(y)})` : undefined}
              className="meter-axis-label"
            >
              {column}
            </text>
          );
        })}
        {rows.map((row, r) => (
          <g key={row}>
            <text
              x={left - 6}
              y={top + r * (CELL + GAP) + CELL - 3}
              textAnchor="end"
              className="meter-axis-label"
            >
              {row}
            </text>
            {columns.map((column, c) => {
              const value = values[r]?.[c] ?? null;
              const box = {
                x: left + c * (CELL + GAP),
                y: top + r * (CELL + GAP),
                width: CELL,
                height: CELL,
              };
              if (value === null) {
                return <rect key={column} {...box} className="meter-heat-missing" />;
              }
              return (
                <g key={column}>
                  <rect
                    data-testid="heat-cell"
                    data-value={value}
                    {...box}
                    fillOpacity={shade(value)}
                    className={
                      provenance === 'forecast'
                        ? 'meter-heat meter-heat-forecast'
                        : 'meter-heat'
                    }
                  >
                    <title>{`${row}, ${column}: ${format(value)}`}</title>
                  </rect>
                  {provenance === 'modelled' ? (
                    <rect data-testid="hatch-over" {...box} fill={`url(#${id}-hatch)`} />
                  ) : null}
                </g>
              );
            })}
          </g>
        ))}
      </svg>
      <ChartTable
        caption={label}
        rowHeader=""
        columns={columns}
        rows={rows.map((row, r) => ({
          label: row,
          cells: columns.map((_, c) => {
            const value = values[r]?.[c] ?? null;
            return value === null
              ? { value: null, text: missing }
              : { value, text: format(value) };
          }),
        }))}
      />
    </figure>
  );
}
