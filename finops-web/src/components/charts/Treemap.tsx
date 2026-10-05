import type { Provenance } from '../provenance';
import { ChartTable } from './ChartTable';
import { Hatch } from './Hatch';
import { at, markClass, useChartId } from './marks';
import { squarify } from './treemapLayout';

/**
 * Parts of a whole, as areas. P8 spec section 5.4.
 *
 * Labels are kept out of the cells and in the legend and the table, because text inside a
 * coloured cell has to clear contrast against every series colour, and a small cell has no
 * room for a name anyway.
 */

export interface TreemapItem {
  readonly label: string;
  readonly value: number;
}

export interface TreemapProps {
  readonly items: readonly TreemapItem[];
  readonly provenance: Provenance;
  readonly label: string;
  readonly format: (value: number) => string;
}

const WIDTH = 300;
const HEIGHT = 180;

export function Treemap({ items, provenance, label, format }: TreemapProps) {
  const id = useChartId();
  const total = items.reduce((sum, item) => sum + Math.max(item.value, 0), 0);
  if (total <= 0) {
    return (
      <p data-testid="chart-absent" data-state="never-collected">
        Nothing collected yet.
      </p>
    );
  }
  const placed = squarify(items, { x: 0, y: 0, width: WIDTH, height: HEIGHT });
  const order = new Map(items.map((item, index) => [item, index]));

  return (
    <figure data-testid="treemap" className="meter-chart">
      <svg
        viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`}
        width="100%"
        role="img"
        aria-label={label}
      >
        <Hatch id={id} />
        {placed.map((cell) => {
          const index = order.get(cell.item) ?? 0;
          const box = {
            x: at(cell.x),
            y: at(cell.y),
            width: at(cell.width),
            height: at(cell.height),
          };
          return (
            <g key={cell.item.label}>
              <rect
                data-testid="treemap-cell"
                data-value={((cell.item.value / total) * 100).toFixed(3)}
                {...box}
                className={markClass(provenance, index)}
              >
                <title>{`${cell.item.label}, ${format(cell.item.value)}`}</title>
              </rect>
              {provenance === 'modelled' ? (
                <rect data-testid="hatch-over" {...box} fill={`url(#${id}-hatch)`} />
              ) : null}
            </g>
          );
        })}
      </svg>
      <ul className="meter-legend" aria-hidden="true">
        {items.map((item, index) => (
          <li key={item.label}>
            <svg width="10" height="10">
              <rect width="10" height="10" className={markClass(provenance, index)} />
            </svg>
            {item.label}, {((item.value / total) * 100).toFixed(1)}%
          </li>
        ))}
      </ul>
      <ChartTable
        caption={label}
        rowHeader="Item"
        columns={['Value', 'Share']}
        rows={items.map((item) => ({
          label: item.label,
          cells: [
            { value: item.value, text: format(item.value) },
            { value: null, text: `${((item.value / total) * 100).toFixed(1)}%` },
          ],
        }))}
      />
    </figure>
  );
}
