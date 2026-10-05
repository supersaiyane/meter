import { useVirtualizer } from '@tanstack/react-virtual';
import { COST_COLUMN_TERMS } from './displayNames';
import { useRef } from 'react';

import { DenseRegion } from './DenseRegion';
import { ROW_HEIGHT, VIRTUALISE_ABOVE, type Column } from './tableConfig';

/**
 * The one table. A sub project inventing its own is how a product acquires four
 * table styles, and how three of them end up rendering numbers without
 * provenance.
 *
 * It is built on a headless virtualiser rather than a component library's grid.
 * ADR-0019 rejected the library on evidence rather than taste: the product's
 * central requirement is a bespoke rendering of every number, and a library's
 * table cell is exactly the thing that has to be ours.
 *
 * Cells are given as rendered nodes rather than raw values, which is deliberate.
 * There is no path through this component that formats a number, so a column of
 * costs has to be built from Figure and cannot be built from strings.
 */
export interface DataTableProps<Row> {
  readonly rows: readonly Row[];
  readonly columns: readonly Column<Row>[];
  readonly rowKey: (row: Row) => string;
  readonly caption: string;
}

export function DataTable<Row>({ rows, columns, rowKey, caption }: DataTableProps<Row>) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualise = rows.length > VIRTUALISE_ABOVE;

  // useVirtualizer reads state during render, so the React Compiler skips this
  // component. That costs automatic memoisation here and nothing else. The
  // alternative is hand writing a virtualiser, which ADR-0019 rules out as rung
  // seven: a large amount of subtle work that is not this product's problem.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
    enabled: virtualise,
  });

  const items = virtualizer.getVirtualItems();
  const visible = virtualise
    ? items.map((item) => ({ index: item.index, row: rows[item.index] }))
    : rows.map((row, index) => ({ index, row }));

  return (
    <DenseRegion>
      <div
        ref={scrollRef}
        data-testid="table-scroll"
        style={{ overflow: 'auto', maxHeight: '70vh' }}
      >
        <table data-testid="table" data-virtualised={virtualise ? 'true' : 'false'}>
          <caption>{caption}</caption>
          <thead>
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  title={COST_COLUMN_TERMS[column.header]}
                  className={column.prose === true ? 'meter-prose' : undefined}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map(({ index, row }) =>
              row === undefined ? null : (
                <tr key={rowKey(row)} data-row-index={index}>
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={
                        [
                          column.numeric === true ? 'meter-numeral' : '',
                          column.prose === true ? 'meter-prose' : '',
                        ]
                          .filter(Boolean)
                          .join(' ') || undefined
                      }
                    >
                      {column.render(row)}
                    </td>
                  ))}
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>
    </DenseRegion>
  );
}
