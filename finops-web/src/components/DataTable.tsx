import { useVirtualizer } from '@tanstack/react-virtual';
import { useEffect, useId, useRef, useState } from 'react';

import { COST_COLUMN_TERMS } from './displayNames';
import { DenseRegion } from './DenseRegion';
import {
  ROW_HEIGHT,
  VIRTUALISE_ABOVE,
  columnTotal,
  nextSort,
  sortRows,
  type Column,
  type Sort,
} from './tableConfig';

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
 * costs has to be built from Figure and cannot be built from strings. A total is
 * drawn by the column's own renderer for the same reason.
 *
 * Since TASK-P8-006 it sorts, by a button in the header so the keyboard and the
 * pointer do the same thing and `aria-sort` says which way; it totals a column
 * only where the figures share a unit and a provenance; and a reader can hide
 * columns. The header stays in view while the rows scroll under it. A row opens
 * its own screen through a link in its name cell, which every table with a
 * detail screen already draws, so the table adds no second link beside it.
 */
export interface DataTableProps<Row> {
  readonly rows: readonly Row[];
  readonly columns: readonly Column<Row>[];
  readonly rowKey: (row: Row) => string;
  readonly caption: string;
  /**
   * The order the rows arrive in, where they arrive ranked. Said in the header
   * from the first render, so the caption names the table and does not claim an
   * order that stops being true the moment a reader sorts another column.
   */
  readonly initialSort?: Sort;
  /**
   * Data attributes on each row: the hooks a screen's own table carried before it moved
   * here, TASK-P8-013, its row's test id and the state a stylesheet or a journey reads off it.
   */
  readonly rowAttributes?: (row: Row) => Readonly<Record<`data-${string}`, string>>;
  /** A test id on the caption, for a screen whose tests read the count the caption states. */
  readonly captionTestId?: string;
}

/** True while the box is smaller than what it holds, watched as either changes size. */
function useScrolls(box: { readonly current: HTMLDivElement | null }): boolean {
  const [scrolls, setScrolls] = useState(false);
  useEffect(() => {
    const element = box.current;
    if (element === null || typeof ResizeObserver === 'undefined') {
      return undefined;
    }
    const check = () => {
      setScrolls(
        element.scrollWidth > element.clientWidth ||
          element.scrollHeight > element.clientHeight,
      );
    };
    check();
    const observer = new ResizeObserver(check);
    observer.observe(element);
    if (element.firstElementChild !== null) {
      observer.observe(element.firstElementChild);
    }
    return () => {
      observer.disconnect();
    };
  }, [box]);
  return scrolls;
}

export function DataTable<Row>({
  rows,
  columns,
  rowKey,
  caption,
  initialSort,
  rowAttributes,
  captionTestId,
}: DataTableProps<Row>) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const captionId = useId();
  const scrolls = useScrolls(scrollRef);
  const [sort, setSort] = useState<Sort | null>(initialSort ?? null);
  const [hidden, setHidden] = useState<ReadonlySet<string>>(() => new Set());
  const shown = columns.filter((column) => !hidden.has(column.key));
  const ordered = sort === null ? rows : sortRows(rows, columns, sort);
  const virtualise = ordered.length > VIRTUALISE_ABOVE;

  // useVirtualizer reads state during render, so the React Compiler skips this
  // component. That costs automatic memoisation here and nothing else. The
  // alternative is hand writing a virtualiser, which ADR-0019 rules out as rung
  // seven: a large amount of subtle work that is not this product's problem.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: ordered.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
    enabled: virtualise,
  });

  const items = virtualizer.getVirtualItems();
  const visible = virtualise
    ? items.map((item) => ({ index: item.index, row: ordered[item.index] }))
    : ordered.map((row, index) => ({ index, row }));

  // Over every row, not the rows the window happens to render.
  const totals = shown.some((column) => column.total !== undefined)
    ? shown.map((column) =>
        column.total === undefined ? null : columnTotal(rows, column.total),
      )
    : null;

  const toggleColumn = (key: string): void => {
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  return (
    <DenseRegion>
      <details data-testid="column-chooser">
        <summary>Columns</summary>
        {columns.map((column) => {
          const showing = !hidden.has(column.key);
          return (
            <label key={column.key}>
              <input
                type="checkbox"
                checked={showing}
                // The last column cannot go: a table of nothing is not a choice anyone made.
                disabled={showing && shown.length === 1}
                onChange={() => {
                  toggleColumn(column.key);
                }}
              />
              {column.header}
            </label>
          );
        })}
      </details>
      <div
        ref={scrollRef}
        data-testid="table-scroll"
        // A box that scrolls is a box a keyboard has to reach, or a wide table's last columns
        // are out of reach without a mouse. Named by the caption it holds, and a stop only
        // when it scrolls, so a table that fits adds nothing to the tab order.
        {...(scrolls ? { tabIndex: 0, role: 'region', 'aria-labelledby': captionId } : {})}
        style={{ overflow: 'auto', maxHeight: '70vh' }}
      >
        <table data-testid="table" data-virtualised={virtualise ? 'true' : 'false'}>
          <caption id={captionId} data-testid={captionTestId}>
            {caption}
          </caption>
          <thead>
            <tr>
              {shown.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  title={COST_COLUMN_TERMS[column.header]}
                  className={column.prose === true ? 'meter-prose' : undefined}
                  aria-sort={
                    column.sortValue === undefined
                      ? undefined
                      : sort?.key === column.key
                        ? sort.direction
                        : 'none'
                  }
                >
                  {column.sortValue === undefined ? (
                    column.header
                  ) : (
                    <button
                      type="button"
                      className="meter-sort"
                      onClick={() => {
                        setSort((current) => nextSort(current, column));
                      }}
                    >
                      {column.header}
                      <span aria-hidden="true">
                        {sort?.key === column.key
                          ? sort.direction === 'ascending'
                            ? ' ↑'
                            : ' ↓'
                          : ''}
                      </span>
                    </button>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map(({ index, row }) => {
              if (row === undefined) {
                return null;
              }
              return (
                <tr key={rowKey(row)} data-row-index={index} {...rowAttributes?.(row)}>
                  {shown.map((column) => {
                    const Cell = column.rowHeader === true ? 'th' : 'td';
                    return (
                      <Cell
                        scope={column.rowHeader === true ? 'row' : undefined}
                        key={column.key}
                        data-testid={column.cellTestId}
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
                      </Cell>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
          {totals === null ? null : (
            <tfoot>
              <tr data-testid="totals-row">
                {shown.map((column, index) => {
                  const total = totals[index] ?? null;
                  return (
                    <td
                      key={column.key}
                      data-testid={`total-${column.key}`}
                      className={column.numeric === true ? 'meter-numeral' : undefined}
                    >
                      {total === null ? (
                        index === 0 ? (
                          'Total'
                        ) : null
                      ) : total.kind === 'sum' ? (
                        column.total?.render(total.sum, total.unit, total.provenance)
                      ) : (
                        <span className="meter-total-none">{total.why}</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </DenseRegion>
  );
}
